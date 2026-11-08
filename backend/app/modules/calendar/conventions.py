"""Calendar conventions, observance cities and the gate in front of every computed lunar date.

A convention (ADR-0022 §3) is a code-reviewed setting: its month system, which civil day a tithi
falls on for each kind of day, and how adhik months are handled. A convention is **offered** for
conversion and lunar reminders only when all three hold (§8):

1. ``VSH_LUNAR_CALENDAR_ENABLED`` is true (set only after the engine licence review is signed off);
2. the engine's ephemeris is present and matches its checksum;
3. the convention is marked ``golden_verified``, which the test suite allows only when its golden
   panchang table (``golden/<key>.json``) exists and passes.

No convention is ever inferred from a surname, a place or a community.
"""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.core.config import get_settings
from app.core.lunar import MonthConvention
from app.modules.calendar import engine

DATA = Path(__file__).parent / "data"
GOLDEN = Path(__file__).parent / "golden"
DayRule = Literal["sunrise", "aparahna"]


@dataclass(frozen=True)
class Convention:
    key: str
    labels: dict[str, str]
    month_convention: MonthConvention
    day_rule: dict[str, DayRule]
    adhik_rule: Literal["nija"]
    regions: tuple[str, ...]
    golden_verified: bool

    def rule_for(self, kind: str) -> DayRule:
        return self.day_rule.get(kind) or self.day_rule["default"]


@dataclass(frozen=True)
class City:
    key: str
    en: str
    hi: str
    lat: float
    lon: float
    tz: str

    def place(self) -> engine.Place:
        return engine.Place(self.lat, self.lon, self.tz)


@functools.cache
def all_conventions() -> dict[str, Convention]:
    raw = json.loads((DATA / "conventions.json").read_text(encoding="utf-8"))
    out = {}
    for c in raw["conventions"]:
        out[c["key"]] = Convention(
            key=c["key"],
            labels=c["labels"],
            month_convention=MonthConvention(c["month_convention"]),
            day_rule=c["day_rule"],
            adhik_rule=c["adhik_rule"],
            regions=tuple(c["regions"]),
            golden_verified=bool(c["golden_verified"]),
        )
    return out


@functools.cache
def cities() -> dict[str, City]:
    raw = json.loads((DATA / "cities.json").read_text(encoding="utf-8"))
    return {c["key"]: City(**c) for c in raw["cities"]}


def golden_table(key: str) -> dict[str, Any] | None:
    path = GOLDEN / f"{key}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def lunar_enabled() -> bool:
    return bool(get_settings().lunar_calendar_enabled)


def offered(key: str | None) -> bool:
    """Whether computed lunar dates may be shown for this convention now."""
    c = all_conventions().get(key or "")
    return bool(c and c.golden_verified and lunar_enabled() and engine.available())


def status() -> dict[str, Any]:
    """For the settings screen: what is and is not switched on, and why."""
    return {
        "lunar_enabled": lunar_enabled(),
        "engine_available": engine.available() if lunar_enabled() else None,
        "conventions": {
            k: {"golden_verified": c.golden_verified, "offered": offered(k)}
            for k, c in all_conventions().items()
        },
    }
