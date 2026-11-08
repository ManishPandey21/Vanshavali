"""Calendar conventions, observance cities and the gate in front of every computed lunar date.

A convention (ADR-0022 §3) is a code-reviewed setting: its month system, which civil day a tithi
falls on for each kind of day, and how adhik months are handled. Computed lunar dates (calendar
entries, conversion suggestions, tithi reminders) are **offered** for a convention *at a city*
only when every gate holds (ADR-0022 §8 and the owner decisions of 8 Nov 2026):

1. ``VSH_LUNAR_CALENDAR_ENABLED`` is true (the operator's switch);
2. the engine's ephemeris is present and matches its checksum;
3. a **licence sign-off** in ``data/approvals.json`` names a qualified reviewer and is bound to the
   current engine (library versions) and ephemeris checksum;
4. an **accuracy approval** for that convention and city names an independent panchang reviewer and
   is bound, by digests, to the engine (library versions), the ephemeris, the calculation source
   code, the convention's definition, the city's coordinates and the golden table. Changing any of
   them makes the approval stale until it is revalidated;
5. the **product owner's activation** for that convention and city.

A golden table on its own enables nothing. No convention is ever inferred from a surname, a place
or a community.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.core.config import get_settings
from app.core.lunar import MonthConvention
from app.modules.calendar import engine, ephemeris

DATA = Path(__file__).parent / "data"
APPROVALS = DATA / "approvals.json"
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


# ---------------------------------------------------------------- what an approval is bound to
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def convention_digest(key: str) -> str | None:
    """The convention's rules (not its labels), so a rule change needs revalidation."""
    raw = json.loads((DATA / "conventions.json").read_text(encoding="utf-8"))
    entry = next((c for c in raw["conventions"] if c["key"] == key), None)
    if entry is None:
        return None
    rules = {k: entry[k] for k in ("key", "month_convention", "day_rule", "adhik_rule")}
    return _sha256(json.dumps(rules, sort_keys=True, separators=(",", ":")).encode())


def golden_digest(key: str) -> str | None:
    path = GOLDEN / f"{key}.json"
    return _sha256(path.read_bytes()) if path.is_file() else None


# The code that computes a tithi day. An approval is bound to the exact bytes of these files, so any
# edit (even to a comment) needs a fresh review: METHOD_VERSION alone is a hand-kept label and could
# be forgotten. Raw bytes rather than an AST or token digest, which differ between Python versions.
CALCULATION_SOURCES = (
    Path(__file__).parent / "engine.py",
    Path(__file__).parent / "observance.py",
    Path(__file__).parents[2] / "core" / "lunar.py",
)


def code_digest() -> str:
    h = hashlib.sha256()
    for path in CALCULATION_SOURCES:
        h.update(path.name.encode() + b"\0")
        h.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def city_digest(city: str) -> str | None:
    """The city's coordinates and time zone, which decide its sunrise and civil day."""
    raw = json.loads((DATA / "cities.json").read_text(encoding="utf-8"))
    entry = next((c for c in raw["cities"] if c["key"] == city), None)
    if entry is None:
        return None
    place = {k: entry[k] for k in ("key", "lat", "lon", "tz")}
    return _sha256(json.dumps(place, sort_keys=True, separators=(",", ":")).encode())


def identity(key: str, city: str) -> dict[str, str | None]:
    """The values an accuracy approval for ``key`` at ``city`` must carry to be current."""
    return {
        "engine_version": engine.ENGINE_VERSION,
        "ephemeris_sha256": ephemeris.SHA256,
        "code_sha256": code_digest(),
        "convention_sha256": convention_digest(key),
        "city_sha256": city_digest(city),
        "golden_sha256": golden_digest(key),
    }


def approvals() -> dict[str, Any]:
    if not APPROVALS.is_file():
        return {"licence": None, "accuracy": [], "activation": []}
    return dict(json.loads(APPROVALS.read_text(encoding="utf-8")))


def _named(rec: dict[str, Any], *fields: str) -> bool:
    return all(isinstance(rec.get(f), str) and rec[f].strip() for f in fields)


def licence_problem() -> str | None:
    """Why the licence gate is closed, or None when a current sign-off is recorded."""
    rec = approvals().get("licence")
    if not rec:
        return "no licence sign-off recorded"
    if not _named(rec, "reviewer", "role", "signed_on", "record"):
        return "the licence sign-off does not name its reviewer, role, date and record"
    if rec.get("engine_version") != engine.ENGINE_VERSION:
        return f"the licence sign-off covers {rec.get('engine_version')}, not {engine.ENGINE_VERSION}"
    if rec.get("ephemeris_sha256") != ephemeris.SHA256:
        return "the licence sign-off covers a different ephemeris file"
    return None


def accuracy_problems(key: str, city: str) -> list[str]:
    """Why no current accuracy approval covers ``key`` at ``city`` (empty when one does)."""
    recs = [
        a for a in approvals().get("accuracy") or [] if a.get("convention") == key and a.get("city") == city
    ]
    if not recs:
        return [f"no accuracy approval for {key} at {city}"]
    want = identity(key, city)
    problems: list[str] = []
    for rec in recs:
        if not _named(rec, "prepared_by", "reviewer", "reviewed_on", "record"):
            problems.append(
                "an approval does not name who prepared it, its reviewer, the date and the record"
            )
            continue
        if rec["prepared_by"].strip().casefold() == rec["reviewer"].strip().casefold():
            problems.append("the reviewer must be independent of whoever prepared the table")
            continue
        stale = [k for k, v in want.items() if v is None or rec.get(k) != v]
        if stale:
            problems.append(f"stale approval ({', '.join(stale)} changed): revalidate")
            continue
        return []
    return problems


def activated(key: str, city: str) -> bool:
    return any(
        a.get("convention") == key and a.get("city") == city and _named(a, "approved_by", "approved_on")
        for a in approvals().get("activation") or []
    )


def verified(key: str, city: str) -> bool:
    return licence_problem() is None and not accuracy_problems(key, city)


def offered(key: str | None, city: str | None) -> bool:
    """Whether computed lunar dates may be shown for this convention at this city now."""
    if not key or not city or key not in all_conventions() or city not in cities():
        return False
    return bool(lunar_enabled() and engine.available() and verified(key, city) and activated(key, city))


def offered_cities(key: str) -> list[str]:
    return [c for c in cities() if offered(key, c)]


def status() -> dict[str, Any]:
    """For operators: what is and is not switched on, and why."""
    return {
        "lunar_enabled": lunar_enabled(),
        "engine_available": engine.available(),
        "engine_version": engine.ENGINE_VERSION,
        "licence": licence_problem() or "signed off",
        "conventions": {k: {"offered_cities": offered_cities(k)} for k in all_conventions()},
    }
