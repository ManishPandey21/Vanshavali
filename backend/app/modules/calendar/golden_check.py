"""Compare the engine with a convention's golden panchang table (ADR-0022 §9).

The table holds **facts transcribed from published panchangs**, each row naming its source; this
module only compares the engine with them and reports coverage. It never marks anything verified:
an accuracy approval is a separate, signed record in ``data/approvals.json`` (see
``conventions.accuracy_problems``), bound to this table's digest.

Format 2 (``golden/README.md``):

- ``tithi_ends``: the ending moment of each tithi in IST, with the lunar month the source names.
  Tithi endings are geocentric, so they hold for every city (Rashtriya Panchang, "Explanation").
- ``sunrises``: a city's sunrise in IST as the source gives it (to the minute).
- ``observances`` (optional): the civil day a source gives for a lunar date under a day rule.
- ``divergences``: where a source contradicts itself or another source. Both readings are kept;
  the source row is never edited. A divergence stops counting as a mismatch only when a named
  reviewer has accepted it (``accepted_by``).

The **civil-day check** derives, from the source alone, which tithi is current at the city's
sunrise (the first tithi to end after it) and compares it with the engine. Days where a tithi ends
within the source's precision of sunrise cannot be decided from the source and are counted, not
compared.
"""

from __future__ import annotations

import bisect
import datetime as dt
import itertools
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from app.core.lunar import MASAS, LunarDate, Paksha, tithi_index
from app.modules.calendar import engine, observance
from app.modules.calendar.conventions import all_conventions, cities

IST = ZoneInfo("Asia/Kolkata")
MIN_YEARS = 3
END_TOLERANCE = dt.timedelta(minutes=2)
# the source gives whole minutes (±30 s), and may define sunrise slightly differently (≤ 1 min)
SUNRISE_TOLERANCE = dt.timedelta(seconds=90)
UNDECIDABLE = dt.timedelta(minutes=1)


@dataclass
class Report:
    convention: str
    city: str | None
    compared: dict[str, int] = field(default_factory=dict)
    undecidable: int = 0
    mismatches: list[str] = field(default_factory=list)
    accepted_divergences: list[str] = field(default_factory=list)
    coverage_gaps: list[str] = field(default_factory=list)
    max_end_delta_s: float = 0.0
    max_sunrise_delta_s: float = 0.0

    @property
    def rows(self) -> int:
        return sum(self.compared.values())

    @property
    def passed(self) -> bool:
        """The table matches and covers the scope. Still not an approval (see module docstring)."""
        return self.rows > 0 and not self.mismatches and not self.coverage_gaps


def _ist(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp).replace(tzinfo=IST)


def _row_index(row: dict[str, Any]) -> int:
    return tithi_index(Paksha(row["paksha"]), int(row["tithi"]))


def _sources_gaps(table: dict[str, Any]) -> list[str]:
    gaps = []
    sources = table.get("sources") or {}
    if not sources:
        gaps.append("the table names no published source")
    for key, src in sources.items():
        for need in ("publisher", "title", "edition", "retrieved", "usage"):
            if not src.get(need):
                gaps.append(f"source {key!r} does not record its {need}")
        if not (src.get("pages") or src.get("pages_cited")):
            gaps.append(f"source {key!r} lists no pages with their checksums or page numbers")
    for kind in ("tithi_ends", "sunrises", "observances"):
        for row in table.get(kind) or []:
            if row.get("source") not in sources:
                gaps.append(f"a {kind} row cites an unknown source {row.get('source')!r}")
                break
    return gaps


def coverage_gaps(table: dict[str, Any], convention: str, city: str) -> list[str]:
    gaps = _sources_gaps(table)
    ends = table.get("tithi_ends") or []
    rises = [r for r in table.get("sunrises") or [] if r.get("city") == city]
    covered = _covered_days(ends)
    if covered < MIN_YEARS * 365:
        gaps.append(f"tithi endings cover {covered} days; at least {MIN_YEARS} years are needed")
    if not any(r.get("adhik") for r in ends):
        gaps.append("no tithi in an adhik month")
    if not rises:
        gaps.append(f"no published sunrise for {city}")
    else:
        days = _days_by_ends(ends, rises)
        if not any(n == 0 for n in days.values()):
            gaps.append(f"no day at {city} on which no tithi ends (vriddhi)")
        if not any(n >= 2 for n in days.values()):
            gaps.append(f"no day at {city} on which two tithis end (kshaya)")
    conv = all_conventions().get(convention)
    if conv is None:
        gaps.append(f"unknown convention {convention!r}")
    elif not any(r.get("month_convention") == conv.month_convention.value for r in ends):
        gaps.append(f"no source names months the {conv.month_convention.value} way")
    kinds = {o.get("kind") for o in table.get("observances") or [] if o.get("city") == city}
    if conv is not None:
        for kind in ("memorial", "birthday"):
            if kind not in kinds:
                gaps.append(
                    f"the {conv.rule_for(kind)} rule for {kind} days is not checked against a published "
                    f"observance at {city}"
                )
    return gaps


def _covered_days(ends: list[dict[str, Any]]) -> int:
    """Days covered without a break (consecutive endings at most 2 days apart): a missing edition
    between two others is not counted as covered."""
    moments = sorted({_ist(r["ist"]) for r in ends})
    total = sum(
        ((b - a) for a, b in itertools.pairwise(moments) if b - a <= dt.timedelta(days=2)),
        dt.timedelta(),
    )
    return total.days


def _days_by_ends(ends: list[dict[str, Any]], rises: list[dict[str, Any]]) -> dict[str, int]:
    """For each sourced sunrise-to-sunrise day at a city: how many tithis end in it."""
    starts = sorted(_ist(f"{r['date']}T{r['ist']}") for r in rises)
    moments = sorted(_ist(r["ist"]) for r in ends)
    out = {}
    for a, b in itertools.pairwise(starts):
        if (b - a) > dt.timedelta(hours=26):
            continue  # a gap in the sunrise table
        if not moments or a < moments[0] or b > moments[-1]:
            continue  # outside the period the endings cover
        out[a.date().isoformat()] = bisect.bisect_left(moments, b) - bisect.bisect_left(moments, a)
    return out


def _month_name_ok(
    row: dict[str, Any], span: engine.TithiSpan, months: list[engine.LunarMonth]
) -> str | None:
    mid = span.start + (span.end - span.start) / 2
    month = next((m for m in months if m.start <= mid < m.end), None)
    if month is None:
        return "no engine month"
    want = row["masa"]
    if row.get("month_convention", "amanta") != "amanta":
        return None  # compared by the purnimanta mapping in observance tests, not here
    got = MASAS[month.masa - 1]
    if got != want or bool(month.is_adhik) != bool(row.get("adhik")):
        return f"month {('adhik ' if month.is_adhik else '') + got} != {('adhik ' if row.get('adhik') else '') + want}"
    return None


def _divergence(table: dict[str, Any], row: dict[str, Any], field_name: str) -> dict[str, Any] | None:
    return next(
        (
            d
            for d in table.get("divergences") or []
            if d.get("field") == field_name
            and all(d.get("row", {}).get(k) == row.get(k) for k in ("ist", "paksha", "tithi"))
        ),
        None,
    )


def _mismatch(report: Report, table: dict[str, Any], row: dict[str, Any], field_name: str, text: str) -> None:
    """A documented divergence stops counting only once a named reviewer has accepted it."""
    d = _divergence(table, row, field_name)
    if d and isinstance(d.get("accepted_by"), str) and d["accepted_by"].strip():
        report.accepted_divergences.append(f"{text} (accepted by {d['accepted_by']})")
        return
    report.mismatches.append(f"{text} (documented divergence, pending review)" if d else text)


def check(table: dict[str, Any], convention: str, city: str | None = None) -> Report:
    """Compare every row (tithi endings always; sunrise, civil days and observances for ``city``)."""
    report = Report(convention=convention, city=city)
    ends = sorted(table.get("tithi_ends") or [], key=lambda r: r["ist"])
    if ends:
        lo = _ist(ends[0]["ist"]).astimezone(dt.UTC) - dt.timedelta(days=2)
        hi = _ist(ends[-1]["ist"]).astimezone(dt.UTC) + dt.timedelta(days=2)
        spans = engine.tithi_spans(lo, hi)
        months = engine.lunar_months(lo, hi)
        span_ends = [s.end for s in spans]
        for row in ends:
            want = _ist(row["ist"]).astimezone(dt.UTC)
            i = bisect.bisect_left(span_ends, want)
            near = [s for s in spans[max(0, i - 1) : i + 1] if s.index == _row_index(row)]
            where = f"{row['ist']} {row['paksha']} {row['tithi']}"
            if not near:
                report.mismatches.append(f"{where}: the engine has no such tithi ending near this moment")
                continue
            span = min(near, key=lambda s: abs(s.end - want))
            delta = abs(span.end - want)
            report.max_end_delta_s = max(report.max_end_delta_s, delta.total_seconds())
            if delta > END_TOLERANCE:
                got = span.end.astimezone(IST)
                report.mismatches.append(f"{where}: engine ends {got:%Y-%m-%d %H:%M:%S} IST (±2 min)")
            problem = _month_name_ok(row, span, months)
            if problem:
                _mismatch(report, table, row, "masa", f"{where}: {problem}")
        report.compared["tithi_ends"] = len(ends)
    if city is None:
        return report
    report.coverage_gaps = coverage_gaps(table, convention, city)
    c = cities().get(city)
    if c is None:
        report.mismatches.append(f"unknown city {city!r}")
        return report
    place = c.place()
    rises = [r for r in table.get("sunrises") or [] if r.get("city") == city]
    end_moments = sorted(_ist(r["ist"]) for r in ends)
    by_moment = {_ist(r["ist"]): r for r in ends}
    civil = 0
    for row in rises:
        day = dt.date.fromisoformat(row["date"])
        want = _ist(f"{row['date']}T{row['ist']}")
        rise, _ = engine.sun_times(place, day)
        delta = abs(rise - want)
        report.max_sunrise_delta_s = max(report.max_sunrise_delta_s, delta.total_seconds())
        if delta > SUNRISE_TOLERANCE:
            report.mismatches.append(
                f"{city} {row['date']}: engine sunrise {rise.astimezone(IST):%H:%M:%S} IST"
            )
        # the tithi current at the published sunrise, from the source alone
        j = bisect.bisect_right(end_moments, want)
        if j == 0 or j >= len(end_moments):
            continue  # outside the period the endings cover
        nxt = end_moments[j]
        if abs(nxt - want) <= UNDECIDABLE or abs(want - end_moments[j - 1]) <= UNDECIDABLE:
            report.undecidable += 1
            continue
        civil += 1
        source_index = _row_index(by_moment[nxt])
        if engine.tithi_at(rise) != source_index:
            report.mismatches.append(
                f"{city} {row['date']}: tithi at sunrise {engine.tithi_at(rise)} != {source_index} (from the source)"
            )
    report.compared["sunrises"] = len(rises)
    report.compared["civil_days"] = civil
    conv = all_conventions().get(convention)
    for row in table.get("observances") or []:
        if row.get("city") != city or conv is None:
            continue
        day = dt.date.fromisoformat(row["date"])
        lunar = LunarDate.model_validate(row["lunar"])
        window = (day - dt.timedelta(days=40), day + dt.timedelta(days=40))
        found = observance.occurrences(lunar, conv, row["kind"], place, *window)
        if day not in [o.day for o in found]:
            report.mismatches.append(
                f"{city} {row['date']}: engine observes {[o.day.isoformat() for o in found]}"
            )
        report.compared["observances"] = report.compared.get("observances", 0) + 1
    return report
