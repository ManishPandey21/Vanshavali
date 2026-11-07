"""Acceptance benchmark for the geography reference data (ADR-0019 §10), on SYNTHETIC national-scale data.

    uv run python -m app.cli.geo_benchmark --database-url postgresql+psycopg://…/vsh_geo_bench \\
        [--villages 650000] [--queries 300]

Generates LGD-layout CSVs with national proportions (36 states, ~780 districts, ~7,000
sub-districts, the largest state holding ~16.5% of the villages, as Uttar Pradesh does), imports
them through the real importer, activates the snapshot, then times cascade-children and name-search
queries through the real service code and reports p50/p95 plus the tables' footprint.

It writes into the database it is given, so it only accepts a database whose name ends in
``_bench`` and refuses one that already has data. Run it on pilot-sized hardware for the
acceptance numbers; anywhere else the numbers are only indicative.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import sys
import tempfile
import time
from pathlib import Path

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import Base, GeoUnit
from app.models.enums import GeoLevel
from app.modules.geo import importer, service

SYLLABLES = [
    "ra",
    "ma",
    "pu",
    "ra",
    "na",
    "ga",
    "ra",
    "ha",
    "ta",
    "pa",
    "ka",
    "la",
    "sa",
    "ri",
    "ya",
    "bha",
    "ga",
    "va",
    "ti",
    "ko",
    "ta",
    "ba",
    "da",
    "li",
    "ja",
    "mau",
    "aim",
]
SUFFIXES = [
    "pur",
    "pura",
    "garh",
    "ganj",
    "nagar",
    "abad",
    "gaon",
    "khera",
    "wala",
    "kalan",
    "khurd",
    "",
    "",
    "",
]


def _name(rng: random.Random) -> str:
    n = "".join(rng.choice(SYLLABLES) for _ in range(rng.randint(1, 3))) + rng.choice(SUFFIXES)
    return n[:1].upper() + n[1:]


def _deva(name: str) -> str:
    return transliterate(name.lower(), sanscript.ITRANS, sanscript.DEVANAGARI)


def _write(path: Path, header: list[str], rows: list[list[str]]) -> tuple[Path, str]:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def generate(
    out: Path, villages: int, seed: int = 7
) -> tuple[list[tuple[Path, str]], dict[str, tuple[Path, str]], str]:
    rng = random.Random(seed)  # noqa: S311 -- synthetic benchmark data, not security
    states = [str(i) for i in range(1, 37)]
    largest = "9"
    # districts and sub-districts roughly proportional to India's
    districts: list[tuple[str, str]] = []
    subs: list[tuple[str, str, str]] = []
    d_code, s_code = 1, 1
    for st in states:
        for _ in range(60 if st == largest else 20):
            districts.append((st, str(d_code)))
            for _ in range(9):
                subs.append((st, str(d_code), str(s_code)))
                s_code += 1
            d_code += 1
    s_rows = [[st, f"State {st}", _deva(f"State {st}")] for st in states]
    d_rows = [[st, d, _name(rng), ""] for st, d in districts]
    sd_rows = [[st, d, s, _name(rng), ""] for st, d, s in subs]
    stage1 = [
        _write(
            out / "states.csv",
            ["State Code", "State Name (In English)", "State Name (In Local language)"],
            s_rows,
        ),
        _write(
            out / "districts.csv",
            [
                "State Code",
                "District Code",
                "District Name (In English)",
                "District Name (In Local language)",
            ],
            d_rows,
        ),
        _write(
            out / "subdistricts.csv",
            [
                "State Code",
                "District Code",
                "Sub-district Code",
                "Sub-district Name (In English)",
                "Sub-district Name (In Local language)",
            ],
            sd_rows,
        ),
    ]
    by_state: dict[str, list[tuple[str, str, str]]] = {}
    for st, d, s in subs:
        by_state.setdefault(st, []).append((st, d, s))
    share = {st: (0.165 if st == largest else 0.835 / (len(states) - 1)) for st in states}
    v_code = 1
    files: dict[str, tuple[Path, str]] = {}
    for st in states:
        rows = []
        for _ in range(int(villages * share[st])):
            _, d, s = rng.choice(by_state[st])
            nm = _name(rng)
            rows.append([st, d, s, str(v_code), nm, _deva(nm)])
            v_code += 1
        files[st] = _write(
            out / f"villages_{st}.csv",
            [
                "State Code",
                "District Code",
                "Sub-District Code",
                "Village Code",
                "Village Name (In English)",
                "Village Name (In Local language)",
            ],
            rows,
        )
    return stage1, files, largest


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1)))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="app.cli.geo_benchmark")
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--villages", type=int, default=650_000)
    ap.add_argument("--queries", type=int, default=300)
    args = ap.parse_args(argv)
    url = make_url(args.database_url)
    if not (url.database or "").endswith("_bench"):
        print("refused: the database name must end in _bench (this writes synthetic data)", file=sys.stderr)
        return 2
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        if db.scalar(select(func.count()).select_from(GeoUnit)):
            print("refused: geo_unit already has rows; use an empty _bench database", file=sys.stderr)
            return 2
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.perf_counter()
        stage1, villages, largest = generate(Path(tmp), args.villages)
        print(f"generated synthetic files in {time.perf_counter() - t0:.1f}s")
        with Session(engine) as db:
            t0 = time.perf_counter()
            importer.import_files(db, stage=1, snapshot="2026-02", files=stage1, operator="benchmark")
            db.commit()
            print(f"stage 1: {time.perf_counter() - t0:.1f}s")
            timings: dict[str, float] = {}
            for st, f in villages.items():
                t0 = time.perf_counter()
                importer.import_files(
                    db, stage=2, snapshot="2026-02", state=st, files=[f], operator="benchmark"
                )
                db.commit()
                timings[st] = time.perf_counter() - t0
            print(
                f"largest state ({largest}): {timings[largest]:.1f}s; all states: {sum(timings.values()):.1f}s"
            )
            importer.activate(db, "2026-02", operator="benchmark")
            db.commit()
        with engine.begin() as c:
            c.execute(text("ANALYZE geo_unit; ANALYZE geo_unit_alias"))
        rng = random.Random(11)  # noqa: S311 -- synthetic benchmark data, not security
        with Session(engine) as db:
            a = service.Active(id="2026-02", newest=True, activated_at=None)
            subs = list(db.scalars(select(GeoUnit.lgd_code).where(GeoUnit.level == GeoLevel.SUB_DISTRICT)))
            names = list(
                db.scalars(select(GeoUnit.name_en).where(GeoUnit.level == GeoLevel.VILLAGE).limit(20_000))
            )
            child_ms, search_ms, scoped_ms = [], [], []
            for _ in range(args.queries):
                t0 = time.perf_counter()
                service.children(db, a, GeoLevel.VILLAGE, rng.choice(subs), GeoLevel.SUB_DISTRICT, 0, 200)
                child_ms.append((time.perf_counter() - t0) * 1000)
                nm = rng.choice(names)
                q = nm[: rng.randint(3, max(3, len(nm)))]
                t0 = time.perf_counter()
                service.search(db, a, q, [GeoLevel.VILLAGE, GeoLevel.URBAN_BODY], None, None, 0, 20)
                search_ms.append((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                service.search(
                    db, a, q, [GeoLevel.VILLAGE, GeoLevel.URBAN_BODY], largest, GeoLevel.STATE, 0, 20
                )
                scoped_ms.append((time.perf_counter() - t0) * 1000)
            size = db.execute(
                text(
                    "SELECT sum(pg_total_relation_size(t))::bigint FROM unnest(ARRAY['geo_snapshot','geo_unit','geo_unit_alias','pincode_office']) t"
                )
            ).scalar()
            rows = db.scalar(select(func.count()).select_from(GeoUnit))
    print(f"rows: {rows}; footprint incl. indexes: {int(size or 0) / 1024 / 1024:.0f} MB")
    for label, xs in (
        ("cascade children", child_ms),
        ("search, all India", search_ms),
        ("search, in a state", scoped_ms),
    ):
        print(f"{label}: p50 {_pct(xs, 50):.1f} ms, p95 {_pct(xs, 95):.1f} ms ({len(xs)} queries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
