"""Scheduled maintenance (run daily from cron / a Kubernetes CronJob / a scheduler of your choice).

    python -m app.cli.maintenance purge-deleted-documents [--older-than-days N]
    python -m app.cli.maintenance sweep-orphans [--delete] [--min-age-hours 24]

Both commands are idempotent and safe to run as the restricted application role (they bind each
tree for row-level security). ``sweep-orphans`` is a dry run unless ``--delete`` is given.
"""

from __future__ import annotations

import argparse
import logging

from app.modules.documents.retention import purge_deleted_documents, sweep_orphaned_objects


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("purge-deleted-documents", help="permanently remove expired soft-deleted documents")
    p.add_argument("--older-than-days", type=int, default=None)
    s = sub.add_parser("sweep-orphans", help="report (or delete) stored objects no row references")
    s.add_argument("--delete", action="store_true")
    s.add_argument("--min-age-hours", type=int, default=24)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    if args.cmd == "purge-deleted-documents":
        n = purge_deleted_documents(older_than_days=args.older_than_days)
        print(f"purged {n} document(s)")
        return 0
    res = sweep_orphaned_objects(delete_objects=args.delete, min_age_hours=args.min_age_hours)
    print(
        f"scanned {res.scanned} object(s); orphaned {len(res.orphaned)}; "
        f"skipped {res.too_recent} too recent; deleted {res.deleted}"
    )
    for key in res.orphaned:
        print(f"  orphan: {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
