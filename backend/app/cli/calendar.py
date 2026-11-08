"""Family calendar operations (ADR-0022).

    uv run python -m app.cli.calendar fetch-ephemeris            # download + verify DE440s
    uv run python -m app.cli.calendar compute --city varanasi --year 2027
    uv run python -m app.cli.calendar check-golden --convention amanta --city mumbai
    uv run python -m app.cli.calendar approval-template --convention amanta --city mumbai
    uv run python -m app.cli.calendar transcribe-rp --pages <saved pages> --out <golden table>

``compute`` writes ``panchang_day`` rows (global reference data; run as the schema owner).
``check-golden`` compares the engine with a convention's golden table and prints the report; a
pass is evidence for a reviewer, never an approval. ``approval-template`` prints the digests a
signed accuracy approval must carry (see docs/operations/family-calendar-approvals.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import PanchangDay
from app.modules.calendar import conventions, engine, ephemeris, golden_check, transcribe_rp


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
    gold.add_argument("--city", default=None, help="also check sunrise, civil days and coverage here")
    tmpl = sub.add_parser("approval-template", help="print the digests an accuracy approval must carry")
    tmpl.add_argument("--convention", required=True)
    tmpl.add_argument("--city", required=True)
    rp = sub.add_parser("transcribe-rp", help="transcribe saved Rashtriya Panchang pages into a golden table")
    rp.add_argument("--pages", required=True, help="directory with the saved pages, SHA256SUMS and RETRIEVED")
    rp.add_argument("--out", required=True)
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
    if args.cmd == "transcribe-rp":
        known = set(conventions.cities())
        table = transcribe_rp.transcribe(Path(args.pages), known)
        out = Path(args.out)
        if out.is_file():  # keep what reviewers added by hand
            previous = json.loads(out.read_text(encoding="utf-8"))
            for key in ("divergences", "observances"):
                table[key] = previous.get(key) or table.get(key) or []
        Path(args.out).write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(table['tithi_ends'])} tithi endings, {len(table['sunrises'])} sunrises -> {args.out}")
        return 0
    if args.cmd == "approval-template":
        # the values a reviewer's record must carry; the people, dates and record are theirs to fill in
        template = {
            "convention": args.convention,
            "city": args.city,
            **conventions.identity(args.convention),
            "prepared_by": "",
            "reviewer": "",
            "reviewed_on": "",
            "record": "",
        }
        print(json.dumps(template, indent=2))
        return 0
    golden = conventions.golden_table(args.convention)
    if golden is None:
        print(f"no golden table for {args.convention!r} (see app/modules/calendar/golden/README.md)")
        return 1
    report = golden_check.check(golden, args.convention, args.city)
    for line in report.coverage_gaps:
        print(f"coverage: {line}")
    for line in report.mismatches:
        print(f"mismatch: {line}")
    print(
        f"compared {report.compared}; undecidable civil days {report.undecidable}; "
        f"largest differences: tithi end {report.max_end_delta_s:.0f} s, sunrise {report.max_sunrise_delta_s:.0f} s"
    )
    print(
        "PASSED (still needs an independent review and a signed approval)" if report.passed else "NOT PASSED"
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
