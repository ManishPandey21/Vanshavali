"""Backup-bucket and restore-verification tooling for the pilot (docs/operations/backup-restore-runbook.md).

Runs from the backend image (``deploy/pilot/scripts/backup.sh`` and ``restore.sh`` call it), so the VM
needs no AWS CLI. Commands:

    manifest --out FILE           row counts per table, alembic version and primary-bucket object
                                  totals (connect as the schema owner: RLS hides rows from the app role)
    put FILE KEY                  upload a file to the backup bucket
    get KEY FILE                  download from the backup bucket
    ls [PREFIX]                   list the backup bucket
    mirror-to-backup              copy primary-bucket objects missing from backup:objects/ (incremental)
    mirror-from-backup            copy backup:objects/ into the (empty, restored) primary bucket
    check-restore --manifest FILE compare a restored database and bucket with the manifest taken at
                                  backup time, and confirm the audit log is still append-only

Primary bucket: the app's ``VSH_S3_*`` settings. Backup bucket: ``BACKUP_S3_ENDPOINT_URL`` (optional),
``BACKUP_S3_REGION``, ``BACKUP_S3_BUCKET``, ``BACKUP_S3_ACCESS_KEY``, ``BACKUP_S3_SECRET_KEY``. Stored
objects are already encrypted by the app (ADR-0004), so the mirror copies ciphertext; database dumps
are encrypted with age before ``put``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from sqlalchemy import create_engine, func, select, table, text

from app.core.config import get_settings

OBJECTS_PREFIX = "objects/"


def _primary() -> tuple[Any, str]:
    import boto3

    s = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        region_name=s.s3_region,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
    )
    return client, s.s3_bucket


def _backup() -> tuple[Any, str]:
    import boto3

    env = os.environ
    missing = [
        k for k in ("BACKUP_S3_BUCKET", "BACKUP_S3_ACCESS_KEY", "BACKUP_S3_SECRET_KEY") if not env.get(k)
    ]
    if missing:
        raise SystemExit(f"backup bucket not configured: {', '.join(missing)}")
    client = boto3.client(
        "s3",
        endpoint_url=env.get("BACKUP_S3_ENDPOINT_URL") or None,
        region_name=env.get("BACKUP_S3_REGION") or get_settings().s3_region,
        aws_access_key_id=env["BACKUP_S3_ACCESS_KEY"],
        aws_secret_access_key=env["BACKUP_S3_SECRET_KEY"],
    )
    return client, env["BACKUP_S3_BUCKET"]


def _objects(client: Any, bucket: str, prefix: str = "") -> dict[str, int]:
    out: dict[str, int] = {}
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            out[o["Key"]] = o["Size"]
    return out


def _counts(url: str) -> tuple[dict[str, int], str | None]:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            tables = [
                r[0]
                for r in c.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
                    )
                )
            ]
            # table() quotes the identifier; names come from information_schema, not user input
            counts = {
                t: int(c.execute(select(func.count()).select_from(table(t))).scalar_one()) for t in tables
            }
            version = c.execute(text("SELECT string_agg(version_num, ',') FROM alembic_version")).scalar()
        return counts, version
    finally:
        eng.dispose()


def manifest(out: str, previous: str | None = None) -> int:
    """Write the manifest. With ``previous`` (a manifest taken just before ``pg_dump``), the counts
    taken now are the upper bound and the previous ones the lower bound: the dump's snapshot lies in
    between, so a restore is checked against that range while the site keeps taking writes."""
    counts, version = _counts(get_settings().database_url)
    client, bucket = _primary()
    objs = _objects(client, bucket)
    data = {
        "taken_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "alembic_version": version,
        "row_counts": counts,
        "objects": {"count": len(objs), "bytes": sum(objs.values())},
    }
    if previous:
        with open(previous, encoding="utf-8") as f:
            before = json.load(f)
        data["row_counts_before"] = before["row_counts"]
        data["objects_before"] = before["objects"]
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    print(f"manifest: {len(counts)} tables, {sum(counts.values())} rows, {len(objs)} objects -> {out}")
    return 0


def mirror(to_backup: bool) -> int:
    (src, src_bucket), (dst, dst_bucket) = (_primary(), _backup()) if to_backup else (_backup(), _primary())
    src_prefix, dst_prefix = ("", OBJECTS_PREFIX) if to_backup else (OBJECTS_PREFIX, "")
    t0 = time.perf_counter()
    have = {k[len(dst_prefix) :]: v for k, v in _objects(dst, dst_bucket, dst_prefix).items()}
    copied = skipped = nbytes = 0
    for key, size in _objects(src, src_bucket, src_prefix).items():
        rel = key[len(src_prefix) :]
        if have.get(rel) == size:  # objects are write-once (ADR-0004): same key + size = same object
            skipped += 1
            continue
        body = src.get_object(Bucket=src_bucket, Key=key)["Body"].read()
        dst.put_object(
            Bucket=dst_bucket, Key=dst_prefix + rel, Body=body, ContentType="application/octet-stream"
        )
        copied += 1
        nbytes += len(body)
    print(
        f"mirror {'primary -> backup' if to_backup else 'backup -> primary'}: copied {copied} "
        f"({nbytes} bytes), already present {skipped}, {time.perf_counter() - t0:.1f}s"
    )
    return 0


def _audit_append_only(url: str) -> dict[str, str]:
    eng = create_engine(url)
    out: dict[str, str] = {}
    try:
        for verb, sql in (
            (
                "update",
                "UPDATE audit_event SET action = action WHERE id = (SELECT id FROM audit_event LIMIT 1)",
            ),
            ("delete", "DELETE FROM audit_event WHERE id = (SELECT id FROM audit_event LIMIT 1)"),
        ):
            with eng.connect() as c:
                if not c.execute(text("SELECT count(*) FROM audit_event")).scalar_one():
                    out[verb] = "no rows to test"
                    continue
                try:
                    c.execute(text(sql))
                    out[verb] = "ALLOWED (trigger missing)"
                except Exception as exc:  # expected: the append-only trigger raises
                    out[verb] = (
                        "rejected"
                        if "append-only" in str(exc)
                        else f"failed differently: {type(exc).__name__}"
                    )
                finally:
                    c.rollback()
    finally:
        eng.dispose()
    return out


def check_restore(manifest_path: str) -> int:
    with open(manifest_path, encoding="utf-8") as f:
        expected = json.load(f)
    url = get_settings().database_url
    counts, version = _counts(url)
    problems: list[str] = []
    if version != expected["alembic_version"]:
        # newer migrations applied after the restore are fine only if the manifest version is an ancestor;
        # report it so the operator decides
        problems.append(f"alembic_version {version} != manifest {expected['alembic_version']}")
    before = expected.get("row_counts_before", expected["row_counts"])
    for t, n in expected["row_counts"].items():
        lo, hi = sorted((before.get(t, n), n))
        got = counts.get(t)
        if got is None or not lo <= got <= hi:
            problems.append(f"{t}: restored {got} rows, manifest {lo}..{hi}")
    client, bucket = _primary()
    objs = _objects(client, bucket)
    if len(objs) < expected.get("objects_before", expected["objects"])["count"]:
        problems.append(f"objects: {len(objs)} in the bucket, manifest {expected['objects']['count']}")
    audit = _audit_append_only(url)
    if audit.get("update") != "rejected" or audit.get("delete") != "rejected":
        problems.append(f"audit_event is not append-only: {audit}")
    print(
        f"restored: {len(counts)} tables, {sum(counts.values())} rows (manifest {sum(expected['row_counts'].values())}), "
        f"{len(objs)} objects (manifest {expected['objects']['count']}), audit append-only: {audit}"
    )
    for p in problems:
        print(f"[FAIL] {p}")
    print("[PASS] restore matches the manifest" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--out", required=True)
    m.add_argument("--previous", help="manifest taken just before pg_dump (lower bounds)")
    p = sub.add_parser("put")
    p.add_argument("file")
    p.add_argument("key")
    g = sub.add_parser("get")
    g.add_argument("key")
    g.add_argument("file")
    sub.add_parser("ls").add_argument("prefix", nargs="?", default="")
    sub.add_parser("mirror-to-backup")
    sub.add_parser("mirror-from-backup")
    sub.add_parser("check-restore").add_argument("--manifest", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "manifest":
        return manifest(args.out, args.previous)
    if args.cmd == "put":
        client, bucket = _backup()
        client.upload_file(args.file, bucket, args.key)
        print(f"uploaded {args.file} -> s3://{bucket}/{args.key}")
        return 0
    if args.cmd == "get":
        client, bucket = _backup()
        client.download_file(bucket, args.key, args.file)
        print(f"downloaded s3://{bucket}/{args.key} -> {args.file}")
        return 0
    if args.cmd == "ls":
        client, bucket = _backup()
        for key, size in sorted(_objects(client, bucket, args.prefix).items()):
            print(f"{size:>12}  {key}")
        return 0
    if args.cmd in ("mirror-to-backup", "mirror-from-backup"):
        return mirror(args.cmd == "mirror-to-backup")
    return check_restore(args.manifest)


if __name__ == "__main__":
    sys.exit(main())
