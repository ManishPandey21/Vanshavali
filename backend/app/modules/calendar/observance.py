"""Which civil day a lunar date falls on, at a place, under a convention (ADR-0022 §3, §5).

Rules (each is part of the convention and is decided by the golden tables, not by this code):

* **The month.** The anchor is converted to the amanta month it falls in. An anchor in an
  ordinary month is observed in the ordinary (*nija*) month of that name; an anchor in an adhik
  month is observed in that year's adhik month of the same name when there is one, otherwise in
  the nija month.
* **The tithi.** Each tithi occurs once in a lunar month; its real start and end are computed.
* **The day, ``sunrise`` rule** (*udaya tithi*): the day whose local sunrise falls inside the
  tithi. Two such days (*vriddhi*): the first. None (*kshaya*): the day on which the tithi starts.
* **The day, ``aparahna`` rule**: the day whose afternoon (the fourth fifth of daylight) the
  tithi covers most. A tie: the earlier day. No overlap at all: the day of the tithi's midpoint.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
from dataclasses import dataclass

from app.core.lunar import LunarDate, masa_number, tithi_index, to_amanta_masa
from app.modules.calendar import engine
from app.modules.calendar.conventions import Convention, DayRule


@dataclass(frozen=True)
class Observance:
    day: dt.date
    tithi_start: dt.datetime
    tithi_end: dt.datetime
    masa: int  # amanta
    is_adhik: bool
    rule: DayRule
    engine_version: str = engine.ENGINE_VERSION


def _choose_month(
    months: list[engine.LunarMonth], anchor: LunarDate, amanta_masa: int
) -> list[engine.LunarMonth]:
    chosen = []
    for i, m in enumerate(months):
        if m.masa != amanta_masa or m.is_adhik:
            continue
        prev = months[i - 1] if i > 0 else None
        if anchor.is_adhik and prev is not None and prev.is_adhik and prev.masa == amanta_masa:
            chosen.append(prev)
        else:
            chosen.append(m)
    return chosen


def _day_for(span: engine.TithiSpan, place: engine.Place, rule: DayRule) -> dt.date:
    first = engine.local_date(span.start, place.timezone) - dt.timedelta(days=1)
    last = engine.local_date(span.end, place.timezone) + dt.timedelta(days=1)
    candidates = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
    if rule == "sunrise":
        hits = [d for d in candidates if span.start <= engine.sun_times(place, d)[0] < span.end]
        return hits[0] if hits else engine.local_date(span.start, place.timezone)
    best: tuple[float, dt.date] | None = None
    for d in candidates:
        rise, sets = engine.sun_times(place, d)
        part = (sets - rise) / 5
        a0, a1 = rise + 3 * part, rise + 4 * part
        overlap = (min(a1, span.end) - max(a0, span.start)).total_seconds()
        if overlap > 0 and (best is None or overlap > best[0]):
            best = (overlap, d)
    if best is not None:
        return best[1]
    return engine.local_date(span.start + (span.end - span.start) / 2, place.timezone)


def occurrences(
    anchor: LunarDate,
    convention: Convention,
    kind: str,
    place: engine.Place,
    start: dt.date,
    end: dt.date,
) -> list[Observance]:
    """Every observance of ``anchor`` whose civil day falls in [start, end]."""
    rule = convention.rule_for(kind)
    amanta = to_amanta_masa(masa_number(anchor.masa), anchor.paksha, anchor.month_convention)
    k = tithi_index(anchor.paksha, anchor.tithi)
    utc = dt.UTC
    w0 = dt.datetime.combine(start - dt.timedelta(days=40), dt.time(), tzinfo=utc)
    w1 = dt.datetime.combine(end + dt.timedelta(days=40), dt.time(), tzinfo=utc)
    months = engine.lunar_months(w0, w1)
    out = []
    for m in _choose_month(months, anchor, amanta):
        spans = [
            s
            for s in engine.tithi_spans(m.start, m.end)
            if s.index == k and s.start < m.end and s.end > m.start
        ]
        if not spans:
            continue
        span = max(spans, key=lambda s: min(s.end, m.end) - max(s.start, m.start))
        day = _day_for(span, place, rule)
        if start <= day <= end:
            out.append(Observance(day, span.start, span.end, m.masa, m.is_adhik, rule))
    return sorted(out, key=lambda o: o.day)


def next_occurrence(
    anchor: LunarDate, convention: Convention, kind: str, place: engine.Place, today: dt.date
) -> Observance | None:
    found = occurrences(anchor, convention, kind, place, today, today + dt.timedelta(days=400))
    return found[0] if found else None


def suggest_gregorian(anchor: LunarDate, convention: Convention, place: engine.Place) -> Observance | None:
    """The probable Gregorian day of a lunar date with a known samvat year (a suggestion only)."""
    if anchor.year is None or anchor.samvat is None:
        return None
    offset = -57 if anchor.samvat.value == "vikram" else 78
    # a samvat year spans two Gregorian years (it starts in Chaitra, or Kartika in some regions)
    greg = anchor.year + offset
    found = occurrences(anchor, convention, "default", place, dt.date(greg, 1, 1), dt.date(greg + 1, 12, 31))
    return found[0] if found else None


def cached_days(
    anchor: LunarDate, convention_key: str, kind: str, city: str, start: dt.date, end: dt.date
) -> list[dt.date]:
    """Observance days for reminders and the calendar, memoised per process (the inputs are small)."""
    return list(_cached(anchor.model_dump_json(), convention_key, kind, city, start, end))


@functools.lru_cache(maxsize=2048)
def _cached(
    anchor_json: str, convention_key: str, kind: str, city: str, start: dt.date, end: dt.date
) -> tuple[dt.date, ...]:
    from app.modules.calendar.conventions import all_conventions, cities

    anchor = LunarDate.model_validate(json.loads(anchor_json))
    found = occurrences(anchor, all_conventions()[convention_key], kind, cities()[city].place(), start, end)
    return tuple(o.day for o in found)
