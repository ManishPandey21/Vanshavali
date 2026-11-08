"""Calendar engine, lunar dates, observance rules and the golden-table gate (ADR-0022 §1-§3, §8-§9).

These tests check structure and rules. Accuracy against published panchangs is the golden tables'
job (``app/modules/calendar/golden``); none ships yet, so no convention is offered.
"""

from __future__ import annotations

import datetime as dt
import itertools
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.dates import DatePrecision, GenealogicalDate
from app.core.lunar import LunarDate, MonthConvention, Paksha, tithi_index, to_amanta_masa
from app.modules.calendar import conventions, engine, ephemeris, golden_check, observance

UTC = dt.UTC


@pytest.fixture(scope="module")
def ready() -> None:
    if engine.available():
        return
    if os.environ.get("VSH_REQUIRE_EPHEMERIS"):
        pytest.fail("the ephemeris is required here (run `python -m app.cli.calendar fetch-ephemeris`)")
    pytest.skip("ephemeris not installed")


# ---------------------------------------------------------------- lunar dates (no engine)
def test_a_lunar_date_stands_on_its_own_and_is_dropped_when_the_date_is_redacted():
    d = GenealogicalDate(
        precision=DatePrecision.UNKNOWN,
        lunar={"masa": "bhadrapada", "paksha": "krishna", "tithi": 8, "month_convention": "purnimanta"},
    )
    assert d.lunar is not None and d.year is None
    assert d.display() == "Bhadrapada Krishna Ashtami"
    assert d.lunar.label("hi") == "भाद्रपद कृष्ण अष्टमी"
    full = GenealogicalDate(
        year=1988,
        month=9,
        day=3,
        lunar={
            "masa": "bhadrapada",
            "paksha": "krishna",
            "tithi": 8,
            "month_convention": "purnimanta",
            "samvat": "vikram",
            "year": 2045,
        },
    )
    assert "Vikram Samvat 2045" in full.display()
    # a redacted (year-only) date never carries the tithi: it would reveal the day
    assert full.year_only().lunar is None
    for bad in (
        {"masa": "chaitra", "paksha": "shukla", "tithi": 16, "month_convention": "amanta"},
        {"masa": "sawan", "paksha": "shukla", "tithi": 1, "month_convention": "amanta"},
        {"masa": "chaitra", "paksha": "shukla", "tithi": 1, "month_convention": "amanta", "extra": 1},
    ):
        with pytest.raises(ValidationError):
            GenealogicalDate(precision=DatePrecision.UNKNOWN, lunar=bad)


def test_purnimanta_krishna_paksha_is_the_previous_amanta_month():
    assert to_amanta_masa(6, Paksha.KRISHNA, MonthConvention.PURNIMANTA) == 5  # Bhadrapada → Shravana
    assert to_amanta_masa(1, Paksha.KRISHNA, MonthConvention.PURNIMANTA) == 12  # Chaitra → Phalguna
    assert to_amanta_masa(6, Paksha.SHUKLA, MonthConvention.PURNIMANTA) == 6
    assert to_amanta_masa(6, Paksha.KRISHNA, MonthConvention.AMANTA) == 6
    assert tithi_index(Paksha.SHUKLA, 15) == 14 and tithi_index(Paksha.KRISHNA, 15) == 29


def test_ephemeris_is_accepted_only_with_its_checksum(tmp_path):
    fake = tmp_path / "de440s.bsp"
    fake.write_bytes(b"not an ephemeris")
    with pytest.raises(ephemeris.EphemerisError, match="checksum"):
        ephemeris.verify(fake)
    with pytest.raises(ephemeris.EphemerisError, match="not found"):
        ephemeris.verify(tmp_path / "missing.bsp")


# ---------------------------------------------------------------- the gate (§8)
def test_nothing_is_offered_by_default_or_without_a_verified_convention(monkeypatch):
    assert get_settings().lunar_calendar_enabled is False
    assert not any(conventions.offered(k) for k in conventions.all_conventions())
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", True)
    # switched on, but no convention has passed its golden table yet
    assert not any(conventions.offered(k) for k in conventions.all_conventions())
    assert conventions.offered("no_such_convention") is False


def test_a_convention_is_verified_only_with_a_passing_golden_table():
    for key, conv in conventions.all_conventions().items():
        if conv.golden_verified:
            table = conventions.golden_table(key)
            assert table is not None, f"{key} is marked verified without a golden table"
            report = golden_check.check(table)
            assert report.passed, (key, report.coverage_gaps, report.mismatches[:5])


def test_conventions_and_cities_are_well_formed():
    convs = conventions.all_conventions()
    assert set(convs) == {"purnimanta", "amanta"}
    for c in convs.values():
        assert c.rule_for("memorial") == "aparahna" and c.rule_for("birthday") == "sunrise"
        assert set(c.labels) >= {"en", "hi"}
    cs = conventions.cities()
    assert set(cs) >= golden_check.REQUIRED_CITIES
    for c in cs.values():
        assert -90 <= c.lat <= 90 and -180 <= c.lon <= 180
        dt.datetime.now(tz=__import__("zoneinfo").ZoneInfo(c.tz))


# ---------------------------------------------------------------- the engine (structure)
def test_lunar_months_are_contiguous_and_named(ready):
    months = engine.lunar_months(dt.datetime(2022, 1, 1, tzinfo=UTC), dt.datetime(2028, 1, 1, tzinfo=UTC))
    for a, b in itertools.pairwise(months):
        assert a.end == b.start
        assert dt.timedelta(days=29) < a.end - a.start < dt.timedelta(days=30, hours=12)
        if not b.is_adhik:
            assert b.masa == a.masa % 12 + 1 or a.is_adhik
    adhik = [(m.start.year, m.masa) for m in months if m.is_adhik]
    # sanity, not the golden table: the widely published adhik months of 2023 and 2026
    assert (2023, 5) in adhik and (2026, 3) in adhik
    assert all(adhik_month_followed_by_its_nija(months, i) for i, m in enumerate(months) if m.is_adhik)


def adhik_month_followed_by_its_nija(months: list[engine.LunarMonth], i: int) -> bool:
    return i + 1 < len(months) and months[i + 1].masa == months[i].masa and not months[i + 1].is_adhik


def test_tithis_follow_each_other(ready):
    spans = engine.tithi_spans(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 3, 1, tzinfo=UTC))
    for a, b in itertools.pairwise(spans):
        assert a.end == b.start and b.index == (a.index + 1) % 30
        assert dt.timedelta(hours=18) < a.end - a.start < dt.timedelta(hours=27)


def test_sunrise_is_local_and_place_keys_are_coarse(ready):
    v = conventions.cities()["varanasi"].place()
    rise, sets = engine.sun_times(v, dt.date(2026, 11, 8))
    assert rise < sets and engine.local_date(rise, v.timezone) == dt.date(2026, 11, 8)
    assert 5 <= rise.astimezone(__import__("zoneinfo").ZoneInfo(v.timezone)).hour <= 7
    assert v.key == "25.3,83.0,Asia/Kolkata"  # ~11 km: never a family's precise location


# ---------------------------------------------------------------- observance rules (§3)
def _anchor(**kw):
    base = {"masa": "bhadrapada", "paksha": "krishna", "tithi": 8, "month_convention": "purnimanta"}
    return LunarDate.model_validate(base | kw)


def test_day_rules_pick_a_day_the_tithi_covers(ready):
    conv = conventions.all_conventions()["purnimanta"]
    place = conventions.cities()["varanasi"].place()
    k = tithi_index(Paksha.KRISHNA, 8)
    for kind in ("birthday", "memorial"):
        found = observance.occurrences(
            _anchor(), conv, kind, place, dt.date(2025, 1, 1), dt.date(2028, 12, 31)
        )
        assert len(found) == 4  # once a year
        for o in found:
            rise, sets = engine.sun_times(place, o.day)
            if o.rule == "sunrise" and o.tithi_start <= rise < o.tithi_end:
                assert engine.tithi_at(rise) == k
            if o.rule == "aparahna":
                part = (sets - rise) / 5
                covers = min(rise + 4 * part, o.tithi_end) > max(rise + 3 * part, o.tithi_start)
                assert (
                    covers
                    or engine.local_date(o.tithi_start + (o.tithi_end - o.tithi_start) / 2, place.timezone)
                    == o.day
                )


def test_the_same_day_written_in_either_month_system(ready):
    place = conventions.cities()["pune"].place()
    p = observance.occurrences(
        _anchor(),
        conventions.all_conventions()["purnimanta"],
        "memorial",
        place,
        dt.date(2026, 1, 1),
        dt.date(2026, 12, 31),
    )
    a = observance.occurrences(
        _anchor(masa="shravana", month_convention="amanta"),
        conventions.all_conventions()["amanta"],
        "memorial",
        place,
        dt.date(2026, 1, 1),
        dt.date(2026, 12, 31),
    )
    assert [o.day for o in p] == [o.day for o in a]


def test_an_adhik_anchor_uses_the_adhik_month_only_in_years_that_have_one(ready):
    conv = conventions.all_conventions()["amanta"]
    place = conventions.cities()["delhi"].place()
    anchor = _anchor(masa="jyeshtha", paksha="shukla", tithi=5, month_convention="amanta", is_adhik=True)
    found = observance.occurrences(
        anchor, conv, "memorial", place, dt.date(2026, 1, 1), dt.date(2027, 12, 31)
    )
    assert [o.is_adhik for o in found] == [True, False]
    nija = observance.occurrences(
        _anchor(masa="jyeshtha", paksha="shukla", tithi=5, month_convention="amanta"),
        conv,
        "memorial",
        place,
        dt.date(2026, 1, 1),
        dt.date(2026, 12, 31),
    )
    assert [o.is_adhik for o in nija] == [False] and nija[0].day > found[0].day


def test_overseas_days_are_computed_where_they_are_observed(ready):
    conv = conventions.all_conventions()["purnimanta"]
    days = {
        city: observance.occurrences(
            _anchor(),
            conv,
            "birthday",
            conventions.cities()[city].place(),
            dt.date(2026, 1, 1),
            dt.date(2026, 12, 31),
        )[0].day
        for city in ("varanasi", "san_francisco")
    }
    assert abs((days["varanasi"] - days["san_francisco"]).days) <= 1


# ---------------------------------------------------------------- the golden checker itself
def test_golden_checker_reports_gaps_and_mismatches(ready):
    place = conventions.cities()["varanasi"].place()
    day = dt.date(2026, 11, 8)
    s = engine.day_summary(place, day)
    paksha, tithi = (
        ("shukla", s["tithi_at_sunrise"] + 1)
        if s["tithi_at_sunrise"] < 15
        else ("krishna", s["tithi_at_sunrise"] - 14)
    )
    good = {
        "city": "varanasi",
        "date": day.isoformat(),
        "tithi_at_sunrise": {"paksha": paksha, "tithi": tithi},
    }
    wrong = good | {"tithi_at_sunrise": {"paksha": paksha, "tithi": tithi % 15 + 1}}
    report = golden_check.check({"source": {"panchang": "checker self-test"}, "rows": [good]})
    assert report.mismatches == [] and not report.passed  # too little coverage to verify anything
    assert any("missing cities" in g for g in report.coverage_gaps)
    assert golden_check.check({"rows": [wrong]}).mismatches
    assert any("source" in g for g in golden_check.check({"rows": [good]}).coverage_gaps)


def test_no_golden_table_is_generated_by_the_engine():
    """Rows must come from a published panchang: every shipped table names its source per row set."""
    for path in Path(conventions.GOLDEN).glob("*.json"):
        table = conventions.golden_table(path.stem)
        assert table and table.get("source", {}).get("panchang"), path.name
