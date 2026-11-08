"""Load master-data vocabulary packs (ADR-0018) and curate families' offered entries (ADR-0026 §4).

    uv run python -m app.cli.masterdata load [--dry-run]
    uv run python -m app.cli.masterdata offers list [--vocabulary KEY]
    uv run python -m app.cli.masterdata offers accept ID [ID...] --code CODE [--en LABEL --hi LABEL]
    uv run python -m app.cli.masterdata offers decline ID [ID...]

``load`` is idempotent; run it after ``alembic upgrade head`` (pilot migrate service, e2e reset, CI).
``offers accept`` writes the term into the pack JSON: commit that change for code review, then
``load`` makes it a shared term. Several ids merge duplicate offers into one term.
"""

from __future__ import annotations

import argparse
import sys
import uuid

from app.core.db import get_sessionmaker
from app.modules.masterdata import curation
from app.modules.masterdata.loader import PackError, load_packs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli.masterdata")
    sub = parser.add_subparsers(dest="cmd", required=True)
    load = sub.add_parser("load", help="load the JSON packs into the vocabulary tables")
    load.add_argument("--dry-run", action="store_true", help="report changes without writing")
    offers = sub.add_parser("offers", help="review entries families offered to the common lists")
    osub = offers.add_subparsers(dest="action", required=True)
    olist = osub.add_parser("list", help="pending offers, with likely duplicates")
    olist.add_argument("--vocabulary")
    oacc = osub.add_parser("accept", help="write the offer(s) into the pack as one reviewed term")
    oacc.add_argument("ids", nargs="+", type=uuid.UUID)
    oacc.add_argument("--code", required=True, help="new or existing term code")
    oacc.add_argument("--en", help="English label (new term)")
    oacc.add_argument("--hi", help="Hindi label (new term)")
    odec = osub.add_parser("decline", help="decline the offer(s)")
    odec.add_argument("ids", nargs="+", type=uuid.UUID)
    args = parser.parse_args(argv)

    if args.cmd == "offers":
        return _offers(args)
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


def _offers(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as db:
        try:
            if args.action == "list":
                items = curation.pending(db, args.vocabulary)
                for p in items:
                    print(curation.describe(p))
                print(f"{len(items)} pending offer(s)")
                return 0
            if args.action == "accept":
                term = curation.accept(db, args.ids, code=args.code, en=args.en, hi=args.hi)
                db.commit()
                print(f"accepted {len(args.ids)} offer(s) as {args.code}: {term['labels']}")
                print("commit the pack change for review, then run `load`")
                return 0
            n = curation.decline(db, args.ids)
            db.commit()
            print(f"declined {n} offer(s)")
            return 0
        except PackError as e:
            db.rollback()
            print(f"error: {e}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    sys.exit(main())
