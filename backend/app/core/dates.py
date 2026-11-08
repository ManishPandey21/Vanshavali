"""Genealogical dates and times (PRS §8, §9, §52; ADR-0003).

Incomplete dates are stored as given: we never invent a day or month. ``sort_range`` derives a
[from, to] Gregorian range used only for ordering and range queries.
"""

from __future__ import annotations

import calendar as _cal
import datetime as dt
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.lunar import LunarDate


class DateCalendar(StrEnum):
    GREGORIAN = "gregorian"
    JULIAN = "julian"
    VIKRAM_SAMVAT = "vikram_samvat"
    SHAKA = "shaka"
    HIJRI = "hijri"
    OTHER = "other"


class DatePrecision(StrEnum):
    EXACT = "exact"
    DAY_UNKNOWN = "day_unknown"  # month + year known
    MONTH_UNKNOWN = "month_unknown"  # year (+ maybe day) known, month not
    YEAR_ONLY = "year_only"
    CIRCA = "circa"
    BEFORE = "before"
    AFTER = "after"
    RANGE = "range"
    UNKNOWN = "unknown"


class TimePrecision(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    FAMILY_RECOLLECTION = "family_recollection"
    DOCUMENT_RECORDED = "document_recorded"
    UNKNOWN = "unknown"


class TimeSource(StrEnum):
    BIRTH_CERTIFICATE = "birth_certificate"
    HOSPITAL_RECORD = "hospital_record"
    KUNDLI = "kundli"
    FAMILY_RECORDED = "family_recorded"
    VERBAL = "verbal"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


# Year offsets used ONLY to place non-Gregorian years on the sort axis (approximate by design).
_YEAR_OFFSETS = {DateCalendar.VIKRAM_SAMVAT: -57, DateCalendar.SHAKA: 78}


class DateDerivation(BaseModel):
    """How a Gregorian date was computed from the tithi, when a person accepted the suggestion
    (ADR-0022 §2): the provenance of a calculated value, never set without that acceptance."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["lunar"] = "lunar"
    convention: str = Field(max_length=40)
    city: str = Field(max_length=60)
    engine_version: str = Field(max_length=80)


class GenealogicalDate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calendar: DateCalendar = DateCalendar.GREGORIAN
    precision: DatePrecision = DatePrecision.EXACT
    year: int | None = Field(default=None, ge=1, le=9999)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    end_year: int | None = Field(default=None, ge=1, le=9999)
    end_month: int | None = Field(default=None, ge=1, le=12)
    end_day: int | None = Field(default=None, ge=1, le=31)
    original_text: str | None = Field(default=None, max_length=500)
    # a tithi date as the family gives it (ADR-0022 §2); never derived from the Gregorian fields
    lunar: LunarDate | None = None
    derived: DateDerivation | None = None
    redacted: bool = False

    @model_validator(mode="after")
    def _check(self) -> GenealogicalDate:
        p = self.precision
        if p == DatePrecision.UNKNOWN:
            return self
        if self.year is None:
            raise ValueError("year is required unless precision is 'unknown'")
        if p == DatePrecision.EXACT and (self.month is None or self.day is None):
            raise ValueError("exact dates need year, month and day; use a less precise precision instead")
        if p == DatePrecision.DAY_UNKNOWN and (self.month is None or self.day is not None):
            raise ValueError("day_unknown dates need year and month but no day")
        if p == DatePrecision.YEAR_ONLY and (self.month is not None or self.day is not None):
            raise ValueError("year_only dates must not carry month/day")
        if p == DatePrecision.MONTH_UNKNOWN and self.month is not None:
            raise ValueError("month_unknown dates must not carry a month")
        if p == DatePrecision.RANGE and self.end_year is None:
            raise ValueError("range dates need end_year")
        if self.calendar == DateCalendar.GREGORIAN and self.month and self.day:
            try:
                dt.date(self.year, self.month, self.day)
            except ValueError as exc:
                raise ValueError(f"invalid calendar date: {exc}") from exc
        return self

    # ---- derived ----
    def _greg_year(self, year: int) -> int:
        return max(1, year + _YEAR_OFFSETS.get(self.calendar, 0))

    def sort_range(self) -> tuple[dt.date | None, dt.date | None]:
        if self.precision == DatePrecision.UNKNOWN or self.year is None:
            return None, None
        y = self._greg_year(self.year)
        approx_calendar = self.calendar not in (DateCalendar.GREGORIAN, DateCalendar.JULIAN)

        def span(year: int, month: int | None, day: int | None) -> tuple[dt.date, dt.date]:
            if approx_calendar:
                # lunisolar/other calendars: month/day do not map 1:1; widen to the civil years overlapped
                return dt.date(year, 1, 1), dt.date(min(year + 1, 9999), 12, 31)
            if month and day:
                try:
                    d = dt.date(year, month, day)
                    return d, d
                except ValueError:
                    pass
            if month:
                return dt.date(year, month, 1), dt.date(year, month, _cal.monthrange(year, month)[1])
            return dt.date(year, 1, 1), dt.date(year, 12, 31)

        lo, hi = span(y, self.month, self.day)
        p = self.precision
        if p == DatePrecision.CIRCA:
            lo, hi = dt.date(max(1, lo.year - 5), 1, 1), dt.date(min(9999, hi.year + 5), 12, 31)
        elif p == DatePrecision.BEFORE:
            lo = None  # type: ignore[assignment]
        elif p == DatePrecision.AFTER:
            hi = None  # type: ignore[assignment]
        elif p == DatePrecision.RANGE and self.end_year is not None:
            _, hi = span(self._greg_year(self.end_year), self.end_month, self.end_day)
        return lo, hi

    def sort_key(self) -> dt.date | None:
        lo, hi = self.sort_range()
        return lo or hi

    def display(self) -> str:
        """Human readable; always shows qualifiers so approximations never look exact."""
        if self.precision == DatePrecision.UNKNOWN or self.year is None:
            return self.lunar.label() if self.lunar else "unknown"
        parts = [str(self.year)]
        if self.month:
            parts.append(f"{self.month:02d}")
            if self.day:
                parts.append(f"{self.day:02d}")
        base = "-".join(parts)
        cal = "" if self.calendar == DateCalendar.GREGORIAN else f" ({self.calendar.value})"
        prefix = {
            DatePrecision.CIRCA: "c. ",
            DatePrecision.BEFORE: "before ",
            DatePrecision.AFTER: "after ",
        }.get(self.precision, "")
        if self.precision == DatePrecision.RANGE:
            end = "-".join(
                str(x) if i == 0 else f"{x:02d}"
                for i, x in enumerate(
                    [v for v in (self.end_year, self.end_month, self.end_day) if v is not None]
                )
            )
            return f"between {base} and {end}{cal}"
        lunar = f" ({self.lunar.label()})" if self.lunar else ""
        return f"{prefix}{base}{cal}{lunar}"

    def year_only(self) -> GenealogicalDate:
        """Redacted form used for protected living-person dates (PRS §6)."""
        if self.year is None:
            return GenealogicalDate(precision=DatePrecision.UNKNOWN, redacted=True)
        return GenealogicalDate(
            calendar=self.calendar, precision=DatePrecision.YEAR_ONLY, year=self.year, redacted=True
        )


class GenealogicalTime(BaseModel):
    """A time of day with explicit precision; approximate values are never presented as exact."""

    model_config = ConfigDict(extra="forbid")

    value: dt.time | None = None
    precision: TimePrecision = TimePrecision.UNKNOWN
    source: TimeSource = TimeSource.UNKNOWN
    original_text: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> GenealogicalTime:
        if self.value is None and self.precision not in (TimePrecision.UNKNOWN,):
            raise ValueError("a time value is required unless precision is 'unknown'")
        if self.precision == TimePrecision.EXACT and self.source in (
            TimeSource.VERBAL,
            TimeSource.APPROXIMATE,
            TimeSource.UNKNOWN,
        ):
            raise ValueError("a verbally recalled/approximate/unknown-source time cannot be marked exact")
        return self

    @property
    def is_exact(self) -> bool:
        return self.precision == TimePrecision.EXACT


def date_to_json(d: GenealogicalDate | None) -> dict | None:
    return d.model_dump(mode="json", exclude_none=True) if d is not None else None


def date_from_json(raw: dict | None) -> GenealogicalDate | None:
    return GenealogicalDate.model_validate(raw) if raw else None
