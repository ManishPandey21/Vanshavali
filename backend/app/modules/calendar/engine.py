"""Astronomical calendar engine (ADR-0022 §1): sunrise, tithi and lunar months, nothing more.

Skyfield (MIT) with JPL's DE440s ephemeris. No horoscopes, no charts (Q9).

* **Tithi**: the Moon–Sun elongation in 12° steps (0-29). It does not depend on the ayanamsa.
* **Lunar months** (amanta): new moon to new moon, named from the sidereal solar sign the Sun
  enters during the month (entering Mesha → Chaitra, … Meena → Phalguna). A month without a
  sankranti is *adhik* and takes the next month's name; a month with two is *kshaya*.
* **Sidereal positions** use the Lahiri (Chitrapaksha) ayanamsa, approximated as its J2000 value
  plus general precession (IAU 2006); the error over 1900-2150 is a few arcseconds, i.e. well
  under a minute of sankranti time. Golden tables (§9) are the arbiter.

Accuracy is established only by the golden tables; until a convention passes them, nothing
computed here is offered to families (``conventions.offered``).
"""

from __future__ import annotations

import datetime as dt
import functools
import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.modules.calendar import ephemeris

ENGINE_VERSION = f"skyfield-1.55/{ephemeris.NAME}/lahiri-iau2006/1"
_LAHIRI_J2000 = 23.857092  # degrees


class EngineUnavailable(RuntimeError):
    """The ephemeris is missing or does not match its checksum."""


@dataclass(frozen=True)
class Place:
    latitude: float
    longitude: float
    timezone: str

    @property
    def key(self) -> str:
        """Coarse key for cached days: 0.1° (~11 km) changes sunrise by well under a minute, and keeps
        the cache from holding a family's precise location."""
        return f"{self.latitude:.1f},{self.longitude:.1f},{self.timezone}"


@dataclass(frozen=True)
class TithiSpan:
    index: int  # 0-29
    start: dt.datetime  # UTC
    end: dt.datetime  # UTC


@dataclass(frozen=True)
class LunarMonth:
    start: dt.datetime  # new moon, UTC
    end: dt.datetime  # next new moon, UTC
    masa: int  # 1 = Chaitra … 12 = Phalguna (amanta)
    is_adhik: bool
    is_kshaya: bool


# ---------------------------------------------------------------- loading
@functools.cache
def _load() -> tuple[Any, Any]:
    from skyfield.api import load as sf_load

    path = Path(get_settings().ephemeris_path)
    try:
        ephemeris.verify(path)
    except ephemeris.EphemerisError as exc:
        raise EngineUnavailable(str(exc)) from exc
    ts = sf_load.timescale(builtin=True)
    eph = sf_load(str(path))
    return ts, eph


def available() -> bool:
    try:
        _load()
        return True
    except EngineUnavailable:
        return False


def _t(when: dt.datetime) -> Any:
    ts, _ = _load()
    return ts.from_datetime(when.astimezone(dt.UTC))


def _utc(t: Any) -> dt.datetime:
    return t.utc_datetime().replace(microsecond=0)


# ---------------------------------------------------------------- positions
def _longitudes(t: Any) -> tuple[Any, Any]:
    _, eph = _load()
    earth = eph["earth"].at(t)
    _, slon, _ = earth.observe(eph["sun"]).apparent().ecliptic_latlon(epoch="date")
    _, mlon, _ = earth.observe(eph["moon"]).apparent().ecliptic_latlon(epoch="date")
    return slon.degrees, mlon.degrees


def lahiri_ayanamsa(t: Any) -> Any:
    big_t = (t.tt - 2451545.0) / 36525.0
    return _LAHIRI_J2000 + (5028.796195 * big_t + 1.1054348 * big_t**2) / 3600.0


def elongation(t: Any) -> Any:
    slon, mlon = _longitudes(t)
    return (mlon - slon) % 360.0


def tithi_at(when: dt.datetime) -> int:
    return int(elongation(_t(when)) // 12.0)


def _sidereal_sun(t: Any) -> Any:
    slon, _ = _longitudes(t)
    return (slon - lahiri_ayanamsa(t)) % 360.0


# ---------------------------------------------------------------- events
def _find(func: Any, start: dt.datetime, end: dt.datetime, step_days: float) -> list[tuple[dt.datetime, int]]:
    from skyfield.searchlib import find_discrete

    func.step_days = step_days
    times, values = find_discrete(_t(start), _t(end), func)
    return [(_utc(t), int(v)) for t, v in zip(times, values, strict=True)]


def tithi_spans(start: dt.datetime, end: dt.datetime) -> list[TithiSpan]:
    """Every tithi touching [start, end), with its real start and end."""
    pad = dt.timedelta(days=2)

    def f(t: Any) -> Any:
        return (elongation(t) // 12.0).astype(int)

    changes = _find(f, start - pad, end + pad, 0.4)
    spans = []
    for (t0, idx), (t1, _) in itertools.pairwise(changes):
        if t1 > start and t0 < end:
            spans.append(TithiSpan(idx, t0, t1))
    return spans


def new_moons(start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    def f(t: Any) -> Any:
        return (elongation(t) >= 180.0).astype(int)

    return [when for when, v in _find(f, start, end, 7.0) if v == 0]


def sankrantis(start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, int]]:
    """(time, rashi entered: 0 = Mesha … 11 = Meena)."""

    def f(t: Any) -> Any:
        return (_sidereal_sun(t) // 30.0).astype(int)

    return _find(f, start, end, 20.0)


def lunar_months(start: dt.datetime, end: dt.datetime) -> list[LunarMonth]:
    """Amanta months overlapping [start, end)."""
    pad = dt.timedelta(days=35)
    moons = new_moons(start - pad, end + pad)
    sk = sankrantis(moons[0], moons[-1]) if len(moons) > 1 else []
    raw: list[tuple[dt.datetime, dt.datetime, list[int]]] = []
    for a, b in itertools.pairwise(moons):
        raw.append((a, b, [r for when, r in sk if a <= when < b]))
    out: list[LunarMonth] = []
    for i, (a, b, entered) in enumerate(raw):
        if entered:
            masa, adhik = entered[0] + 1, False
        else:
            # no sankranti: adhik, named after the month that follows
            nxt = next((e for _, _, e in raw[i + 1 :] if e), None)
            if nxt is None:
                continue
            masa, adhik = nxt[0] + 1, True
        if b > start and a < end:
            out.append(LunarMonth(a, b, masa, adhik, len(entered) > 1))
    return out


# ---------------------------------------------------------------- the day at a place
def _local_midnight(day: dt.date, tz: str) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(), tzinfo=ZoneInfo(tz))


@functools.lru_cache(maxsize=4096)
def sun_times(place: Place, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """(sunrise, sunset) on the local civil ``day`` at ``place``, UTC."""
    from skyfield import almanac
    from skyfield.api import wgs84

    _, eph = _load()
    start = _local_midnight(day, place.timezone)
    f = almanac.sunrise_sunset(eph, wgs84.latlon(place.latitude, place.longitude))
    times, ups = almanac.find_discrete(_t(start), _t(start + dt.timedelta(days=1)), f)
    rise = next((_utc(t) for t, up in zip(times, ups, strict=True) if up), None)
    sets = next((_utc(t) for t, up in zip(times, ups, strict=True) if not up), None)
    if rise is None or sets is None:
        raise ValueError("no sunrise or sunset on this day at this place")
    return rise, sets


def local_date(when: dt.datetime, tz: str) -> dt.date:
    return when.astimezone(ZoneInfo(tz)).date()


def day_summary(place: Place, day: dt.date) -> dict[str, Any]:
    """What ``panchang_day`` caches for one day at one place."""
    rise, sets = sun_times(place, day)
    start = _local_midnight(day, place.timezone)
    spans = tithi_spans(start, start + dt.timedelta(days=1))
    at_rise = next(s.index for s in spans if s.start <= rise < s.end)
    month = next(m for m in lunar_months(rise, rise + dt.timedelta(seconds=1)) if m.start <= rise < m.end)
    return {
        "sunrise": rise,
        "sunset": sets,
        "tithi_at_sunrise": at_rise,
        "tithis": [{"index": s.index, "start": s.start.isoformat(), "end": s.end.isoformat()} for s in spans],
        "amanta_masa": month.masa,
        "is_adhik": month.is_adhik,
        "engine_version": ENGINE_VERSION,
    }


def days(start: dt.date, count: int) -> Sequence[dt.date]:
    return [start + dt.timedelta(days=i) for i in range(count)]
