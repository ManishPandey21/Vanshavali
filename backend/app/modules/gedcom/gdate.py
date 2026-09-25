"""GEDCOM DATE / TIME ↔ GenealogicalDate / GenealogicalTime.

Import never invents a day or month: whatever the payload does not state stays empty, and the
verbatim payload (or its PHRASE) is kept in ``original_text``. Export follows the GEDCOM 7 grammar
(``ABT/CAL/EST``, ``BEF``, ``AFT``, ``BET … AND …``, ``FROM … TO …``, ``JULIAN`` calendar escape);
calendars GEDCOM cannot express (Vikram Samvat, Shaka, Hijri, other) are exported as an empty DATE
with a ``PHRASE`` carrying the original text.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from pydantic import ValidationError

from app.core.dates import DateCalendar, DatePrecision, GenealogicalDate, GenealogicalTime, TimePrecision

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_MONTH_NUM = {m: i + 1 for i, m in enumerate(MONTHS)}
# tolerate full English month names seen in hand-written files
_MONTH_NUM.update(
    {
        n: i + 1
        for i, n in enumerate(
            [
                "JANUARY",
                "FEBRUARY",
                "MARCH",
                "APRIL",
                "MAY",
                "JUNE",
                "JULY",
                "AUGUST",
                "SEPTEMBER",
                "OCTOBER",
                "NOVEMBER",
                "DECEMBER",
            ]
        )
    }
)
_CAL_V7 = {"GREGORIAN": DateCalendar.GREGORIAN, "JULIAN": DateCalendar.JULIAN}
_CAL_V5 = {
    "@#DGREGORIAN@": DateCalendar.GREGORIAN,
    "@#DJULIAN@": DateCalendar.JULIAN,
}
_UNSUPPORTED_CALS = ("HEBREW", "FRENCH_R", "@#DHEBREW@", "@#DFRENCH R@", "@#DROMAN@", "@#DUNKNOWN@")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(Z)?$", re.IGNORECASE)


class _Simple:
    def __init__(self, calendar: DateCalendar, year: int, month: int | None, day: int | None) -> None:
        self.calendar, self.year, self.month, self.day = calendar, year, month, day


def _parse_simple(tokens: list[str], warnings: list[str]) -> _Simple | None:
    """[calendar] [[day] month] year [epoch]"""
    cal = DateCalendar.GREGORIAN
    toks = list(tokens)
    if toks and (toks[0] in _CAL_V7 or toks[0] in _CAL_V5):
        cal = _CAL_V7.get(toks[0]) or _CAL_V5[toks[0]]
        toks = toks[1:]
    elif toks and (toks[0] in _UNSUPPORTED_CALS or toks[0].startswith("_") or toks[0].startswith("@#D")):
        warnings.append(f"calendar {toks[0]} is not supported; kept as text")
        return None
    if toks and toks[-1] in ("BCE", "BC", "B.C."):
        warnings.append("dates before the common era are kept as text")
        return None
    if not toks or len(toks) > 3:
        return None
    ytok = toks[-1]
    m = re.match(r"^(\d{1,4})(?:/(\d{1,2}))?$", ytok)
    if not m:
        return None
    if m.group(2):
        warnings.append(f"dual year {ytok} recorded as {m.group(1)}")
    year = int(m.group(1))
    if year < 1:
        return None
    month = day = None
    if len(toks) >= 2:
        month = _MONTH_NUM.get(toks[-2])
        if month is None:
            return None
    if len(toks) == 3:
        if not toks[0].isdigit():
            return None
        day = int(toks[0])
        if not 1 <= day <= 31:
            return None
    return _Simple(cal, year, month, day)


def _base_precision(s: _Simple) -> DatePrecision:
    if s.month and s.day:
        return DatePrecision.EXACT
    if s.month:
        return DatePrecision.DAY_UNKNOWN
    return DatePrecision.YEAR_ONLY


def _build(data: dict[str, Any], warnings: list[str]) -> dict[str, Any] | None:
    try:
        return GenealogicalDate.model_validate(data).model_dump(mode="json", exclude_none=True)
    except ValidationError:
        # e.g. 31 FEB: drop the impossible day rather than guessing
        if data.get("day") is not None:
            warnings.append("impossible calendar day dropped")
            data = {**data, "day": None, "end_day": None}
            if data.get("precision") == DatePrecision.EXACT.value:
                data["precision"] = DatePrecision.DAY_UNKNOWN.value
            try:
                return GenealogicalDate.model_validate(data).model_dump(mode="json", exclude_none=True)
            except ValidationError:
                return None
        return None


def parse_date(payload: str | None, phrase: str | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    """GEDCOM DATE payload (+ optional PHRASE) → GenealogicalDate JSON, plus warnings."""
    warnings: list[str] = []
    raw = (payload or "").strip()
    original = (phrase or "").strip() or raw
    original = original[:500] if original else ""
    if not raw:
        if original:
            return {"precision": "unknown", "calendar": "gregorian", "original_text": original}, warnings
        return None, warnings
    text = raw.upper()
    # 5.5.1 "INT <date> (phrase)" and bare "(phrase)"
    m = re.match(r"^INT\s+(.*?)\s*\((.*)\)\s*$", text)
    if m:
        text = m.group(1)
        if not phrase:
            original = raw
    elif text.startswith("(") and text.endswith(")"):
        return {"precision": "unknown", "original_text": raw.strip("() ")[:500] or raw}, warnings
    tokens = text.replace(",", " ").split()

    def fail() -> tuple[dict[str, Any], list[str]]:
        warnings.append(f"date {raw!r} could not be interpreted; kept as text")
        return {"precision": "unknown", "original_text": original or raw}, warnings

    def simple_to(prec: DatePrecision | None, s: _Simple) -> dict[str, Any]:
        return {
            "calendar": s.calendar.value,
            "precision": (prec or _base_precision(s)).value,
            "year": s.year,
            "month": s.month,
            "day": s.day,
            "original_text": original,
        }

    if not tokens:
        return fail()
    q = tokens[0]
    result: dict[str, Any] | None = None
    if q in ("ABT", "CAL", "EST", "ABOUT", "CIRCA", "C."):
        s = _parse_simple(tokens[1:], warnings)
        if s:
            result = simple_to(DatePrecision.CIRCA, s)
    elif q in ("BEF", "BEFORE", "TO"):
        s = _parse_simple(tokens[1:], warnings)
        if s:
            result = simple_to(DatePrecision.BEFORE, s)
    elif q in ("AFT", "AFTER"):
        s = _parse_simple(tokens[1:], warnings)
        if s:
            result = simple_to(DatePrecision.AFTER, s)
    elif q in ("BET", "FROM"):
        sep = "AND" if q == "BET" else "TO"
        if sep in tokens:
            i = tokens.index(sep)
            a = _parse_simple(tokens[1:i], warnings)
            b = _parse_simple(tokens[i + 1 :], warnings)
            if a and b:
                if b.calendar != a.calendar:
                    warnings.append("range endpoints use different calendars; kept as text")
                else:
                    result = {
                        "calendar": a.calendar.value,
                        "precision": DatePrecision.RANGE.value,
                        "year": a.year,
                        "month": a.month,
                        "day": a.day if a.month else None,
                        "end_year": b.year,
                        "end_month": b.month,
                        "end_day": b.day if b.month else None,
                        "original_text": original,
                    }
        elif q == "FROM":
            s = _parse_simple(tokens[1:], warnings)
            if s:
                result = simple_to(DatePrecision.AFTER, s)
    else:
        s = _parse_simple(tokens, warnings)
        if s:
            result = simple_to(None, s)
    if result is None:
        return fail()
    built = _build({k: v for k, v in result.items() if v is not None and v != ""}, warnings)
    if built is None:
        return fail()
    return built, warnings


def parse_time(payload: str | None) -> tuple[dict[str, Any] | None, bool, list[str]]:
    """TIME payload → (GenealogicalTime JSON with UNKNOWN precision, is_utc, warnings)."""
    if not payload:
        return None, False, []
    m = _TIME_RE.match(payload.strip())
    if not m:
        return None, False, [f"time {payload!r} could not be interpreted"]
    h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if h > 23 or mi > 59 or se > 59:
        return None, False, [f"time {payload!r} is out of range"]
    t = GenealogicalTime(value=dt.time(h, mi, se), original_text=payload.strip()[:200])
    return t.model_dump(mode="json", exclude_none=True), bool(m.group(4)), []


# --------------------------------------------------------------------------- export
def _simple_text(cal: DateCalendar, year: int | None, month: int | None, day: int | None) -> str:
    parts: list[str] = []
    if cal == DateCalendar.JULIAN:
        parts.append("JULIAN")
    if month:
        if day:
            parts.append(str(day))
        parts.append(MONTHS[month - 1])
    parts.append(str(year))
    return " ".join(parts)


def format_date(raw: dict[str, Any] | None) -> tuple[str | None, str | None] | None:
    """GenealogicalDate JSON → (DATE payload, PHRASE). None = emit no DATE at all."""
    if not raw:
        return None
    d = GenealogicalDate.model_validate(raw)
    original = (d.original_text or "").strip() or None
    if d.calendar not in (DateCalendar.GREGORIAN, DateCalendar.JULIAN):
        return "", original or d.display()
    if d.precision == DatePrecision.UNKNOWN or d.year is None:
        return ("", original) if original else None
    month = d.month
    day = d.day if month else None  # GEDCOM cannot express a day without a month
    core = _simple_text(d.calendar, d.year, month, day)
    ot = (original or "").upper()
    p = d.precision
    if p == DatePrecision.CIRCA:
        q = "ABT"
        if ot.startswith("CAL"):
            q = "CAL"
        elif ot.startswith("EST"):
            q = "EST"
        payload = f"{q} {core}"
    elif p == DatePrecision.BEFORE:
        payload = f"TO {core}" if ot.startswith("TO ") else f"BEF {core}"
    elif p == DatePrecision.AFTER:
        payload = f"FROM {core}" if ot.startswith("FROM ") and " TO " not in ot else f"AFT {core}"
    elif p == DatePrecision.RANGE:
        end_month = d.end_month
        end = _simple_text(d.calendar, d.end_year, end_month, d.end_day if end_month else None)
        if ot.startswith("FROM ") and " TO " in ot:
            payload = f"FROM {core} TO {end}"
        else:
            payload = f"BET {core} AND {end}"
    else:
        payload = core
    if d.redacted:
        return payload, None
    phrase = original if original and original.upper() != payload else None
    return payload, phrase


def format_time(raw: dict[str, Any] | None, utc: bool = False) -> str | None:
    if not raw:
        return None
    t = GenealogicalTime.model_validate(raw)
    if t.value is None:
        return None
    v = t.value
    text = f"{v.hour:02d}:{v.minute:02d}" + (f":{v.second:02d}" if v.second else "")
    return text + ("Z" if utc else "")


def time_precision_valid(precision: str, source: str) -> bool:
    try:
        GenealogicalTime(value=dt.time(0, 0), precision=TimePrecision(precision), source=source)  # type: ignore[arg-type]
    except (ValidationError, ValueError):
        return False
    return True
