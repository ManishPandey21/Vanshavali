"""Family calendar operations (ADR-0022).

    uv run python -m app.cli.calendar fetch-ephemeris            # download + verify DE440s
    uv run python -m app.cli.calendar compute --city varanasi --year 2027
    uv run python -m app.cli.calendar check-golden --convention purnimanta

``compute`` writes ``panchang_day`` rows (global reference data; run as the schema owner).
``check-golden`` compares the engine with a convention's golden table and prints the report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import PanchangDay
from app.modules.calendar import conventions, engine, ephemeris, golden_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli.calendar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fetch = sub.add_parser("fetch-ephemeris", help="download the pinned ephemeris and verify it")
    fetch.add_argument("--dest", default=None)
    comp = sub.add_parser("compute", help="cache calendar days for a city and year")
    comp.add_argument("--city", required=True)
    comp.add_argument("--year", type=int, required=True)
    gold = sub.add_parser("check-golden", help="compare the engine with a convention's golden table")
    gold.add_argument("--convention", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "fetch-ephemeris":
        print(ephemeris.fetch(Path(args.dest or get_settings().ephemeris_path)))
        return 0
    if args.cmd == "compute":
        city = conventions.cities().get(args.city)
        if city is None:
            print(f"unknown city {args.city!r}", file=sys.stderr)
            return 2
        place = city.place()
        start = dt.date(args.year, 1, 1)
        n = (dt.date(args.year + 1, 1, 1) - start).days
        with get_sessionmaker()() as db:
            for day in engine.days(start, n):
                values = engine.day_summary(place, day)
                stmt = insert(PanchangDay).values(place_key=place.key, day=day, **values)
                db.execute(stmt.on_conflict_do_update(index_elements=["place_key", "day"], set_=values))
            db.commit()
        print(f"{n} days cached for {args.city} ({place.key}) in {args.year}")
        return 0
    table = conventions.golden_table(args.convention)
    if table is None:
        print(f"no golden table for {args.convention!r} (see app/modules/calendar/golden/README.md)")
        return 1
    report = golden_check.check(table)
    for line in report.coverage_gaps + report.mismatches:
        print(line)
    print(f"{report.rows} rows: {'PASSED' if report.passed else 'FAILED'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
