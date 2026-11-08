"""Load Indian geography reference data (ADR-0019 §3). Run as the schema owner, never by the app.

    uv run python -m app.cli.geo import --stage 1 --snapshot 2026-02 \\
        --file states.csv --sha256 <hex> --file districts.csv --sha256 <hex> ... \\
        [--state CODE] [--successors changes.csv --successors-sha256 <hex>] \\
        [--source-url URL] [--downloaded YYYY-MM-DD] [--report-dir DIR] [--operator NAME]
    uv run python -m app.cli.geo activate SNAPSHOT [--accept-large-change] [--operator NAME]
    uv run python -m app.cli.geo discard SNAPSHOT [--operator NAME]
    uv run python -m app.cli.geo status
    uv run python -m app.cli.geo load-test-fixture   # SYNTHETIC data, tests and E2E only

The app never downloads anything: the operator downloads LGD's and India Post's files, records
their checksums, and imports them into a *staged* snapshot. Review the change report, then
``activate``. ``activate PREVIOUS`` is the rollback. Exit codes: 0 done, 1 refused, 2 usage.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models import GeoSnapshot
from app.modules.geo import importer


def _operator(name: str | None) -> str:
    if name:
        return name
    try:
        return getpass.getuser()
    except Exception:
        return "operator"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli.geo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="stage LGD or India Post files into a snapshot")
    imp.add_argument("--stage", type=int, choices=(1, 2, 3), required=True)
    imp.add_argument("--snapshot", required=True, help="YYYY-MM")
    imp.add_argument("--file", action="append", required=True, type=Path)
    imp.add_argument("--sha256", action="append", required=True, help="one per --file, in order")
    imp.add_argument("--state", help="LGD state code (stage 2 only)")
    imp.add_argument("--successors", type=Path, help="merges and splits: level, lgd_code, successor_codes")
    imp.add_argument("--successors-sha256")
    imp.add_argument("--source-url")
    imp.add_argument("--downloaded", help="download date, YYYY-MM-DD")
    imp.add_argument("--report-dir", type=Path, default=Path("geo-reports"))
    imp.add_argument("--operator")
    act = sub.add_parser("activate", help="make a reviewed snapshot active (or roll back to an earlier one)")
    act.add_argument("snapshot")
    act.add_argument("--accept-large-change", action="store_true")
    act.add_argument("--operator")
    dis = sub.add_parser("discard", help="delete the newest snapshot that is not active")
    dis.add_argument("snapshot")
    dis.add_argument("--operator")
    sub.add_parser("status", help="list snapshots")
    fx = sub.add_parser(
        "load-test-fixture", help="load the SYNTHETIC fixture (tests/E2E; refused in production)"
    )
    fx.add_argument("--until", default="2026-05")
    args = parser.parse_args(argv)

    with get_sessionmaker()() as db:
        try:
            if args.cmd == "import":
                if len(args.file) != len(args.sha256):
                    parser.error("give one --sha256 per --file")
                if bool(args.successors) != bool(args.successors_sha256):
                    parser.error("--successors needs --successors-sha256")
                result = importer.import_files(
                    db,
                    stage=args.stage,
                    snapshot=args.snapshot,
                    files=list(zip(args.file, args.sha256, strict=True)),
                    state=args.state,
                    successors_file=(args.successors, args.successors_sha256) if args.successors else None,
                    source_url=args.source_url,
                    downloaded_on=args.downloaded,
                    report_dir=args.report_dir,
                    operator=_operator(args.operator),
                )
                db.commit()
                print(f"staged into snapshot {result.snapshot}")
                for scope, counts in result.summary.items():
                    print(f"  {scope}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
                if result.report_path:
                    print(f"change report: {result.report_path}")
                print("review the report, then: python -m app.cli.geo activate " + result.snapshot)
            elif args.cmd == "activate":
                msg = importer.activate(
                    db,
                    args.snapshot,
                    operator=_operator(args.operator),
                    accept_large_change=args.accept_large_change,
                )
                db.commit()
                print(msg)
            elif args.cmd == "discard":
                msg = importer.discard(db, args.snapshot, operator=_operator(args.operator))
                db.commit()
                print(msg)
            elif args.cmd == "load-test-fixture":
                from app.modules.geo import fixture

                fixture.load(db, until=args.until)
                db.commit()
                print(f"synthetic geography fixture loaded up to {args.until}")
            else:
                for s in db.scalars(select(GeoSnapshot).order_by(GeoSnapshot.id)):
                    scopes = [sc for imp_ in s.imports for sc in imp_.get("scopes", [])]
                    print(f"{s.id}  {s.status.value:8}  {json.dumps(scopes)}")
        except importer.ImportRefused as exc:
            db.rollback()
            print(f"refused: {exc}", file=sys.stderr)
            for line, msg in exc.problems:
                print(f"  line {line}: {msg}" if line else f"  {msg}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
