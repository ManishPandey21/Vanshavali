"""Verify a restored Vanshavali database + object store against its source (restore drill, PRS §55).

Checks, in this order (row counts first, because the API checks below write audit rows):
  1. row counts per table in schema `public` match between source and restore, and so does
     `alembic_version`;
  2. a known user can log in over the API (FastAPI TestClient bound to the *restored* database and
     *restored* storage directory);
  3. one STANDARD and one VAULT document download through the signed-URL flow and their sha256
     equals `document.checksum_sha256` (this proves both data keys decrypt the restored objects);
  4. the `audit_event` append-only trigger still rejects UPDATE (and DELETE).

    cd backend && uv run python ../ops/backup/verify.py \
        --source-url postgresql+psycopg://…/vsh_drill_src --restored-url postgresql+psycopg://…/vsh_drill_dst \
        --storage /path/to/restored/storage --manifest manifest.json [--report verify.json]

Exit status 0 only when every check passes. Data keys come from VSH_STANDARD_DATA_KEY /
VSH_VAULT_DATA_KEY exactly as for the app; they must be the keys the source used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy import create_engine, func, select, table, text

TABLES_SQL = text(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
)


def row_counts(url: str) -> tuple[dict[str, int], str | None]:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            tables = [r[0] for r in c.execute(TABLES_SQL)]
            # table() quotes the identifier; names come from information_schema, not user input
            counts: dict[str, int] = {
                t: c.execute(select(func.count()).select_from(table(t))).scalar_one() for t in tables
            }
            version = c.execute(text("SELECT string_agg(version_num, ',') FROM alembic_version")).scalar()
        return counts, version
    finally:
        eng.dispose()


def check_counts(source_url: str, restored_url: str) -> dict[str, Any]:
    src, src_v = row_counts(source_url)
    dst, dst_v = row_counts(restored_url)
    mismatches = {
        t: {"source": src.get(t), "restored": dst.get(t)}
        for t in sorted(set(src) | set(dst))
        if src.get(t) != dst.get(t)
    }
    return {
        "ok": not mismatches and src_v == dst_v,
        "tables": len(src),
        "rows": sum(src.values()),
        "alembic_version": {"source": src_v, "restored": dst_v},
        "mismatches": mismatches,
        "largest": dict(sorted(src.items(), key=lambda kv: -kv[1])[:8]),
    }


def check_api(api_url: str, owner_url: str, storage: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """The app runs on ``api_url``; stored checksums are read via ``owner_url`` (not subject to RLS)."""
    # settings are read from the environment on first use, so set them before importing the app
    os.environ["VSH_DATABASE_URL"] = api_url
    os.environ["VSH_STORAGE_BACKEND"] = "local"
    os.environ["VSH_STORAGE_LOCAL_PATH"] = storage
    os.environ.setdefault("VSH_JOB_MODE", "sync")
    from fastapi.testclient import TestClient

    from app.main import create_app

    out: dict[str, Any] = {"login": False, "documents": []}
    # a decryption failure (wrong data key, corrupt object) must be reported as FAIL, not crash the drill
    client = TestClient(create_app(), raise_server_exceptions=False)
    r = client.post("/api/v1/auth/login", json={"email": manifest["email"], "password": manifest["password"]})
    out["login"] = r.status_code == 200
    out["login_status"] = r.status_code
    if not out["login"]:
        out["ok"] = False
        return out
    client.headers["X-CSRF-Token"] = client.cookies.get("vsh_csrf") or ""
    tree = manifest["tree_id"]
    eng = create_engine(owner_url)
    seen_classes = set()
    for d in manifest["documents"]:
        with eng.connect() as c:
            row = c.execute(
                text("SELECT checksum_sha256, storage_class FROM document WHERE id = :id"), {"id": d["id"]}
            ).one()
        res: dict[str, Any] = {"id": d["id"], "storage_class": row.storage_class}
        u = client.post(f"/api/v1/trees/{tree}/documents/{d['id']}/download-url")
        res["url_status"] = u.status_code
        if u.status_code == 200:
            f = client.get(u.json()["url"])
            res["download_status"] = f.status_code
            got = hashlib.sha256(f.content).hexdigest() if f.status_code == 200 else None
            res["sha256_ok"] = got == row.checksum_sha256
            res["bytes"] = len(f.content)
        else:
            res["sha256_ok"] = False
        if res["sha256_ok"]:
            seen_classes.add(str(row.storage_class).upper())
        out["documents"].append(res)
    eng.dispose()
    out["ok"] = out["login"] and {"STANDARD", "VAULT"} <= seen_classes
    return out


def check_audit_trigger(restored_url: str) -> dict[str, Any]:
    eng = create_engine(restored_url)
    out: dict[str, Any] = {}
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
                    out[verb] = "ALLOWED (trigger missing!)"
                except Exception as exc:  # expected: the trigger raises
                    out[verb] = (
                        "rejected" if "append-only" in str(exc) else f"failed differently: {exc!s:.200}"
                    )
                finally:
                    c.rollback()
    finally:
        eng.dispose()
    out["ok"] = out.get("update") == "rejected" and out.get("delete") == "rejected"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--restored-url", required=True)
    ap.add_argument(
        "--api-url",
        help="database URL the API check uses (the non-owner app role when RLS is on); default --restored-url",
    )
    ap.add_argument("--storage", required=True, help="restored local object-store directory")
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())

    t0 = time.perf_counter()
    report: dict[str, Any] = {"row_counts": check_counts(args.source_url, args.restored_url)}
    report["api"] = check_api(args.api_url or args.restored_url, args.restored_url, args.storage, manifest)
    report["audit_trigger"] = check_audit_trigger(args.restored_url)
    report["ok"] = all(report[k]["ok"] for k in ("row_counts", "api", "audit_trigger"))
    report["seconds"] = round(time.perf_counter() - t0, 2)

    rc = report["row_counts"]
    print(
        f"[{'PASS' if rc['ok'] else 'FAIL'}] row counts: {rc['tables']} tables, {rc['rows']} rows, "
        f"alembic {rc['alembic_version']['restored']}"
        + (f", mismatches {rc['mismatches']}" if rc["mismatches"] else "")
    )
    api = report["api"]
    print(
        f"[{'PASS' if api['login'] else 'FAIL'}] login as {manifest['email']} (HTTP {api.get('login_status')})"
    )
    for d in api["documents"]:
        print(
            f"[{'PASS' if d['sha256_ok'] else 'FAIL'}] download {d['storage_class']} document {d['id']}: "
            f"url {d['url_status']}, file {d.get('download_status')}, {d.get('bytes')} bytes, sha256 match {d['sha256_ok']}"
        )
    at = report["audit_trigger"]
    print(
        f"[{'PASS' if at['ok'] else 'FAIL'}] audit_event append-only: UPDATE {at.get('update')}, DELETE {at.get('delete')}"
    )
    print(f"verify: {'OK' if report['ok'] else 'FAILED'} in {report['seconds']} s")
    if args.report:
        args.report.write_text(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
