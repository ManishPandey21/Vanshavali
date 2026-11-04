"""Load master-data vocabulary packs (ADR-0018).

    uv run python -m app.cli.masterdata load [--dry-run]

Idempotent; run after ``alembic upgrade head`` (pilot migrate service, e2e reset, CI).
"""

from __future__ import annotations

import argparse
import sys

from app.core.db import get_sessionmaker
from app.modules.masterdata.loader import load_packs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli.masterdata")
    sub = parser.add_subparsers(dest="cmd", required=True)
    load = sub.add_parser("load", help="load the JSON packs into the vocabulary tables")
    load.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args(argv)
    with get_sessionmaker()() as db:
        report = load_packs(db, dry_run=args.dry_run)
    for line in report.changes:
        print(line)
    print(
        f"{'(dry run) ' if args.dry_run else ''}{report.vocabularies} vocabularies: "
        f"{report.inserted} inserted, {report.updated} updated, {report.retired} retired, "
        f"{report.unchanged} unchanged"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
