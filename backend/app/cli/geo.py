"""Geography snapshots (ADR-0019): stage, list, activate (operator), and synthetic test data.

    uv run python -m app.cli.geo stage --source lgd --label 2026-10 --file units.csv \\
        --licence "GODL-India" --attribution "Local Government Directory, MoPR, Govt of India" \\
        [--source-url https://…] [--downloaded-on 2026-10-15] [--operator "Name"]
    uv run python -m app.cli.geo list
    uv run python -m app.cli.geo activate --snapshot <id> --reason "…" --operator "Name"
    uv run python -m app.cli.geo synth --villages 650000 --out units.csv [--offices-out post.csv]

``stage`` never makes data visible: an admin reviews and approves the snapshot in the console, and a
second admin (or, for the single-admin pilot, an operator with ``activate``) activates it.
``synth`` writes clearly fictional data for tests and benchmarks; it never resembles official codes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.errors import ApiError
from app.models import GeoSnapshot
from app.models.enums import GeoSource
from app.modules.geo.admin import activate_by_operator
from app.modules.geo.importer import LGD_HEADER, POST_HEADER, GeoImportError, stage


def _stage(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as db:
        try:
            snap = stage(
                db,
                source=GeoSource(args.source),
                label=args.label,
                path=Path(args.file),
                licence=args.licence,
                attribution=args.attribution,
                source_url=args.source_url,
                downloaded_on=dt.date.fromisoformat(args.downloaded_on) if args.downloaded_on else None,
                staged_by=args.operator,
            )
        except GeoImportError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        r = snap.report
        print(f"{snap.source.value} {snap.label}: {snap.status.value} (id {snap.id})")
        print(f"rows: {r['counts']}  errors: {r['error_count']}  warnings: {r['warning_count']}")
        for e in r["errors"][:20]:
            print(f"  error   {e}")
        for w in r["warnings"][:10]:
            print(f"  warning {w}")
        if r.get("diff"):
            print(
                f"diff against {r['diff'].get('previous')}: { {k: v for k, v in r['diff'].items() if k != 'samples'} }"
            )
        return 1 if snap.status.value == "failed" else 0


def _list(_: argparse.Namespace) -> int:
    with get_sessionmaker()() as db:
        for s in db.scalars(select(GeoSnapshot).order_by(GeoSnapshot.source, GeoSnapshot.created_at)):
            print(f"{s.id}  {s.source.value:10} {s.label:12} {s.status.value:10} {s.report.get('counts')}")
    return 0


def _activate(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as db:
        try:
            s = activate_by_operator(db, uuid.UUID(args.snapshot), args.reason, args.operator)
        except ApiError as exc:
            print(f"refused: {exc.message}", file=sys.stderr)
            return 1
        print(f"{s.source.value} {s.label} is now active")
    return 0


def _synth(args: argparse.Namespace) -> int:
    """Fictional hierarchy: 1 country, 10 states, ~5 districts each, ~6 sub-districts each, villages
    spread evenly; codes start with 9 so they never collide with or resemble official LGD codes."""
    villages = args.villages
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(LGD_HEADER)
        w.writerow(["country", "IN", "", "", "India", "भारत", "Deva", "", "", "", "", "", "", ""])
        subs: list[str] = []
        for s in range(10):
            sc = f"9{s:02d}"
            w.writerow(
                [
                    "state",
                    sc,
                    "country",
                    "IN",
                    f"Synth State {s}",
                    f"कृत्रिम राज्य {s}",
                    "Deva",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            for d in range(5):
                dc = f"9{s:02d}{d:02d}"
                w.writerow(
                    [
                        "district",
                        dc,
                        "state",
                        sc,
                        f"Synth District {s}-{d}",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
                for t in range(6):
                    tc = f"9{s:02d}{d:02d}{t:02d}"
                    subs.append(tc)
                    w.writerow(
                        [
                            "subdistrict",
                            tc,
                            "district",
                            dc,
                            f"Synth Tehsil {s}-{d}-{t}",
                            "",
                            "",
                            "Tehsil",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                        ]
                    )
        for v in range(villages):
            parent = subs[v % len(subs)]
            w.writerow(
                [
                    "village",
                    f"9{v:08d}",
                    "subdistrict",
                    parent,
                    f"Synth Gaon {v}",
                    f"गाँव {v}",
                    "Deva",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    if args.offices_out:
        with open(args.offices_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(POST_HEADER)
            for i in range(max(1, villages // 40)):
                units = "|".join(f"village:9{v:08d}" for v in range(i * 40, min(villages, i * 40 + 3)))
                w.writerow([f"9{i:05d}"[:6], f"Synth Office {i}", "B.O.", "Delivery", "", "", units])
    print(f"wrote {villages} villages to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli.geo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("stage", help="validate and stage a snapshot (not visible until activated)")
    st.add_argument("--source", choices=[s.value for s in GeoSource], required=True)
    st.add_argument("--label", required=True, help="e.g. 2026-10")
    st.add_argument("--file", required=True)
    st.add_argument("--licence", required=True)
    st.add_argument("--attribution", required=True)
    st.add_argument("--source-url")
    st.add_argument("--downloaded-on", help="YYYY-MM-DD")
    st.add_argument("--operator", help="who staged it (recorded on the snapshot)")
    st.set_defaults(fn=_stage)
    sub.add_parser("list", help="list snapshots").set_defaults(fn=_list)
    ac = sub.add_parser("activate", help="operator activation of an admin-approved snapshot")
    ac.add_argument("--snapshot", required=True)
    ac.add_argument("--reason", required=True)
    ac.add_argument("--operator", required=True)
    ac.set_defaults(fn=_activate)
    sy = sub.add_parser("synth", help="write fictional test data")
    sy.add_argument("--villages", type=int, default=1000)
    sy.add_argument("--out", required=True)
    sy.add_argument("--offices-out")
    sy.set_defaults(fn=_synth)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
