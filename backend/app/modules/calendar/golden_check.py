"""Compare the engine with a convention's golden panchang table (ADR-0022 §9).

The table's rows come from published panchangs, entered by a reviewer; this module only compares.
A convention may be marked ``golden_verified`` only when its table meets the coverage below and
every row matches.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from app.core.lunar import MASAS, Paksha, tithi_index
from app.modules.calendar import engine
from app.modules.calendar.conventions import cities

REQUIRED_CITIES = frozenset({"varanasi", "delhi", "pune", "bengaluru", "london", "san_francisco"})
MIN_YEARS = 3
END_TOLERANCE = dt.timedelta(minutes=2)


@dataclass
class Report:
    rows: int = 0
    mismatches: list[str] = field(default_factory=list)
    coverage_gaps: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.rows > 0 and not self.mismatches and not self.coverage_gaps


def coverage_gaps(table: dict[str, Any]) -> list[str]:
    rows = table.get("rows") or []
    gaps = []
    if not (table.get("source") or {}).get("panchang"):
        gaps.append("the table does not name its published source")
    seen_cities = {r.get("city") for r in rows}
    missing = sorted(REQUIRED_CITIES - seen_cities)
    if missing:
        gaps.append(f"missing cities: {', '.join(missing)}")
    years = {str(r.get("date", ""))[:4] for r in rows}
    if len(years) < MIN_YEARS:
        gaps.append(f"needs at least {MIN_YEARS} years, has {len(years)}")
    if not any(r.get("is_adhik") for r in rows):
        gaps.append("no row in an adhik month")
    return gaps


def check(table: dict[str, Any]) -> Report:
    report = Report(coverage_gaps=coverage_gaps(table))
    for row in table.get("rows") or []:
        report.rows += 1
        city = cities().get(row.get("city", ""))
        if city is None:
            report.mismatches.append(f"{row.get('date')}: unknown city {row.get('city')!r}")
            continue
        day = dt.date.fromisoformat(row["date"])
        got = engine.day_summary(city.place(), day)
        where = f"{row['city']} {row['date']}"
        want = row["tithi_at_sunrise"]
        want_index = tithi_index(Paksha(want["paksha"]), int(want["tithi"]))
        if got["tithi_at_sunrise"] != want_index:
            report.mismatches.append(f"{where}: tithi at sunrise {got['tithi_at_sunrise']} != {want_index}")
        if "amanta_masa" in row and MASAS[got["amanta_masa"] - 1] != row["amanta_masa"]:
            report.mismatches.append(
                f"{where}: month {MASAS[got['amanta_masa'] - 1]} != {row['amanta_masa']}"
            )
        if "is_adhik" in row and bool(got["is_adhik"]) != bool(row["is_adhik"]):
            report.mismatches.append(f"{where}: adhik {got['is_adhik']} != {row['is_adhik']}")
        if row.get("tithi_end_local"):
            span = next(
                (s for s in got["tithis"] if s["index"] == got["tithi_at_sunrise"]),
                None,
            )
            if span is not None:
                hh, mm = (int(x) for x in row["tithi_end_local"].split(":"))
                end = dt.datetime.fromisoformat(span["end"])
                local_end = end.astimezone(ZoneInfo(city.tz))
                want_end = local_end.replace(hour=hh, minute=mm, second=0)
                if abs(local_end - want_end) > END_TOLERANCE:
                    report.mismatches.append(
                        f"{where}: tithi ends {local_end:%H:%M} != {row['tithi_end_local']} (±2 min)"
                    )
    return report
