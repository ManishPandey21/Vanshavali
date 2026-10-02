"""Reminder date arithmetic (pure functions; docs/architecture/event-reminder-model.md §3).

* An annual reminder needs a Gregorian month and day. 29 February falls on 28 February in common
  years.
* A one-time reminder needs a full Gregorian date.
* A fire time is ``send_hour:00`` local time on ``occurrence - lead_days``, converted to UTC with the
  recipient's IANA time zone (so DST zones are handled by ``zoneinfo``).
"""

from __future__ import annotations

import calendar
import datetime as dt
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from app.core.dates import DateCalendar, DatePrecision
from app.models.enums import ReminderRecurrence


class NotSchedulable(ValueError):
    """The event's (visible) date cannot drive this reminder."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Anchor:
    month: int
    day: int
    year: int | None  # known for one-time reminders and for "Nth anniversary" wording


@dataclass(frozen=True)
class Fire:
    occurrence: dt.date
    lead_days: int
    at: dt.datetime  # UTC


def anchor_from_date(raw: dict[str, Any] | None, recurrence: ReminderRecurrence) -> Anchor:
    if not raw:
        raise NotSchedulable("date_unknown", "This event has no date to remind about")
    cal = raw.get("calendar") or DateCalendar.GREGORIAN.value
    if cal != DateCalendar.GREGORIAN.value:
        raise NotSchedulable(
            "calendar_not_supported",
            "Reminders follow the Gregorian calendar; lunar (tithi) anniversaries are not supported yet",
        )
    if raw.get("redacted"):
        raise NotSchedulable("date_hidden", "You cannot see this event's full date")
    month, day, year = raw.get("month"), raw.get("day"), raw.get("year")
    precision = raw.get("precision")
    if month is None or day is None or precision not in (DatePrecision.EXACT.value, None):
        raise NotSchedulable("date_incomplete", "A reminder needs the event's day and month")
    if recurrence == ReminderRecurrence.NONE and year is None:
        raise NotSchedulable("date_incomplete", "A one-time reminder needs the full date")
    return Anchor(month=int(month), day=int(day), year=int(year) if year else None)


def occurrence_in(anchor: Anchor, year: int) -> dt.date:
    day = anchor.day
    if anchor.month == 2 and day == 29 and not calendar.isleap(year):
        day = 28
    return dt.date(year, anchor.month, min(day, calendar.monthrange(year, anchor.month)[1]))


def fire_time(occurrence: dt.date, lead_days: int, send_hour: int, tz: str) -> dt.datetime:
    local_day = occurrence - dt.timedelta(days=lead_days)
    local = dt.datetime.combine(local_day, dt.time(hour=send_hour), tzinfo=ZoneInfo(tz))
    return local.astimezone(dt.UTC)


def fires(
    anchor: Anchor,
    recurrence: ReminderRecurrence,
    lead_days: Iterable[int],
    send_hour: int,
    tz: str,
    around: dt.datetime,
) -> Iterator[Fire]:
    """Every fire within about a year either side of ``around`` (sorted)."""
    if recurrence == ReminderRecurrence.ANNUAL:
        years = range(around.year - 1, around.year + 2)
        # never before the event itself (no "birthday" before someone was born)
        occurrences = [occurrence_in(anchor, y) for y in years if anchor.year is None or y >= anchor.year]
    elif anchor.year is not None:
        occurrences = [occurrence_in(anchor, anchor.year)]
    else:
        return
    out = [
        Fire(occ, lead, fire_time(occ, lead, send_hour, tz))
        for occ in occurrences
        for lead in sorted(set(lead_days))
    ]
    yield from sorted(out, key=lambda f: f.at)


def next_fire(
    anchor: Anchor,
    recurrence: ReminderRecurrence,
    lead_days: Iterable[int],
    send_hour: int,
    tz: str,
    after: dt.datetime,
) -> dt.datetime | None:
    for f in fires(anchor, recurrence, list(lead_days), send_hour, tz, after):
        if f.at > after:
            return f.at
    return None


def due_fires(
    anchor: Anchor,
    recurrence: ReminderRecurrence,
    lead_days: Iterable[int],
    send_hour: int,
    tz: str,
    window_start: dt.datetime,
    now: dt.datetime,
) -> list[Fire]:
    return [
        f
        for f in fires(anchor, recurrence, list(lead_days), send_hour, tz, now)
        if window_start < f.at <= now
    ]


def next_occurrence(anchor: Anchor, recurrence: ReminderRecurrence, today: dt.date) -> dt.date | None:
    if recurrence == ReminderRecurrence.ANNUAL:
        occ = occurrence_in(anchor, today.year)
        return occ if occ >= today else occurrence_in(anchor, today.year + 1)
    if anchor.year is None:
        return None
    occ = occurrence_in(anchor, anchor.year)
    return occ if occ >= today else None
