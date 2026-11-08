"""Calendar engine, lunar dates, observance rules and the golden-table gate (ADR-0022 §1-§3, §8-§9).

These tests check structure, rules and the gate. Accuracy against published panchangs is the
golden tables' job (``app/modules/calendar/golden``), and offering a convention needs signed
approvals in ``data/approvals.json``; none is recorded, so nothing is offered.
"""

from __future__ import annotations

import copy
import datetime as dt
import importlib.metadata
import itertools
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.dates import DatePrecision, GenealogicalDate
from app.core.lunar import LunarDate, MonthConvention, Paksha, tithi_index, to_amanta_masa
from app.modules.calendar import conventions, engine, ephemeris, golden_check, observance, transcribe_rp

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
    # an accepted conversion says where it came from, and that note is redacted with the day
    derived = GenealogicalDate.model_validate(
        full.model_dump()
        | {
            "derived": {
                "source": "lunar",
                "convention": "purnimanta",
                "city": "varanasi",
                "engine_version": "x",
            }
        }
    )
    assert derived.derived is not None and derived.derived.city == "varanasi"
    assert derived.year_only().derived is None
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


# ---------------------------------------------------------------- the gate (§8, owner decisions)
EVERY = [(k, c) for k in conventions.all_conventions() for c in conventions.cities()]


def test_nothing_is_offered_by_default_or_without_signed_approvals(monkeypatch):
    assert get_settings().lunar_calendar_enabled is False
    assert not any(conventions.offered(k, c) for k, c in EVERY)
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", True)
    # switched on, but nothing is signed off: still nothing
    assert not any(conventions.offered(k, c) for k, c in EVERY)
    assert conventions.offered("no_such_convention", "delhi") is False
    assert conventions.offered("amanta", None) is False


def test_shipped_approvals_are_current_and_point_at_passing_tables():
    """An approval in the repo must still match what it was given for, or the suite fails."""
    recorded = conventions.approvals()
    if recorded.get("licence"):
        assert conventions.licence_problem() is None, conventions.licence_problem()
    for rec in recorded.get("accuracy") or []:
        key, city = rec["convention"], rec["city"]
        assert not conventions.accuracy_problems(key, city), (
            key,
            city,
            conventions.accuracy_problems(key, city),
        )
        report = golden_check.check(conventions.golden_table(key) or {}, key, city)
        assert report.passed, (key, city, report.coverage_gaps, report.mismatches[:5])
    for act in recorded.get("activation") or []:
        assert conventions.verified(act["convention"], act["city"]), (
            f"activated without a current sign-off: {act}"
        )


def _approve(monkeypatch, key: str = "amanta", city: str = "mumbai") -> dict:
    data = {
        "licence": {
            "reviewer": "A licensing reviewer",
            "role": "counsel",
            "signed_on": "2026-11-08",
            "record": "test",
            "engine_version": engine.ENGINE_VERSION,
            "ephemeris_sha256": ephemeris.SHA256,
        },
        "accuracy": [
            {
                "convention": key,
                "city": city,
                **conventions.identity(key, city),
                "prepared_by": "A developer",
                "reviewer": "An independent panchang reviewer",
                "reviewed_on": "2026-11-08",
                "record": "test",
            }
        ],
        "activation": [
            {"convention": key, "city": city, "approved_by": "Product owner", "approved_on": "2026-11-08"}
        ],
    }
    monkeypatch.setattr(conventions, "approvals", lambda: data)
    return data


def test_every_gate_is_needed_and_approvals_are_bound_to_what_was_checked(monkeypatch, ready):
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", True)
    # a golden table on its own enables nothing
    assert conventions.golden_table("amanta") is not None
    assert not conventions.offered("amanta", "mumbai")
    data = _approve(monkeypatch)
    assert conventions.offered("amanta", "mumbai")
    # only the approved convention at the approved city
    assert not conventions.offered("amanta", "delhi") and not conventions.offered("purnimanta", "mumbai")
    breakers = {
        "no licence sign-off": lambda d: d.update(licence=None),
        "licence for another engine": lambda d: d["licence"].update(engine_version="skyfield-0.1/x"),
        "licence for another ephemeris": lambda d: d["licence"].update(ephemeris_sha256="0" * 64),
        "no activation": lambda d: d.update(activation=[]),
        "the table changed": lambda d: d["accuracy"][0].update(golden_sha256="0" * 64),
        "the convention's rules changed": lambda d: d["accuracy"][0].update(convention_sha256="0" * 64),
        "the engine changed": lambda d: d["accuracy"][0].update(engine_version="skyfield-0.1/x"),
        "the ephemeris changed": lambda d: d["accuracy"][0].update(ephemeris_sha256="0" * 64),
        "the calculation code changed": lambda d: d["accuracy"][0].update(code_sha256="0" * 64),
        "the city's coordinates changed": lambda d: d["accuracy"][0].update(city_sha256="0" * 64),
        "approved for another city": lambda d: d["accuracy"][0].update(city="delhi"),
        "reviewer not independent": lambda d: d["accuracy"][0].update(reviewer="a developer"),
        "no reviewer": lambda d: d["accuracy"][0].update(reviewer=""),
    }
    for why, breaks in breakers.items():
        broken = copy.deepcopy(data)
        breaks(broken)
        monkeypatch.setattr(conventions, "approvals", lambda b=broken: b)
        assert not conventions.offered("amanta", "mumbai"), why
    monkeypatch.setattr(conventions, "approvals", lambda: data)
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", False)
    assert not conventions.offered("amanta", "mumbai")


def test_a_calculation_change_withdraws_approvals_even_without_a_version_bump(monkeypatch, tmp_path, ready):
    """Regression: METHOD_VERSION is a hand-kept label; an edit to the calculation that forgets to
    bump it must still make every approval stale (owner decision 3: revalidate after a material change)."""
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", True)
    _approve(monkeypatch)
    assert conventions.offered("amanta", "mumbai")
    version = engine.ENGINE_VERSION
    # the same files, one with a changed ayanamsa constant and nothing else
    originals = conventions.CALCULATION_SOURCES
    copies = []
    for path in originals:
        copy_path = tmp_path / path.name
        text = path.read_text(encoding="utf-8")
        if path.name == "engine.py":
            assert "_LAHIRI_J2000 = 23.857092" in text
            text = text.replace("_LAHIRI_J2000 = 23.857092", "_LAHIRI_J2000 = 23.85")
        copy_path.write_text(text, encoding="utf-8")
        copies.append(copy_path)
    monkeypatch.setattr(conventions, "CALCULATION_SOURCES", tuple(copies))
    assert version == engine.ENGINE_VERSION and engine.METHOD_VERSION in version  # the label did not move
    assert not conventions.offered("amanta", "mumbai")
    assert any("code_sha256" in p for p in conventions.accuracy_problems("amanta", "mumbai"))
    # the binding is to the content: restoring the original bytes makes the approval current again
    for original, copy_path in zip(originals, copies, strict=True):
        copy_path.write_bytes(original.read_bytes())
    assert conventions.offered("amanta", "mumbai")


def test_moving_an_approved_city_withdraws_its_approval(monkeypatch, tmp_path, ready):
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", True)
    _approve(monkeypatch)
    assert conventions.offered("amanta", "mumbai")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("conventions.json", "approvals.json"):
        (data_dir / name).write_bytes((conventions.DATA / name).read_bytes())
    cities = json.loads((conventions.DATA / "cities.json").read_text(encoding="utf-8"))
    for c in cities["cities"]:
        if c["key"] == "mumbai":
            c["lat"] = 19.2
    (data_dir / "cities.json").write_text(json.dumps(cities), encoding="utf-8")
    monkeypatch.setattr(conventions, "DATA", data_dir)
    assert not conventions.offered("amanta", "mumbai")
    assert any("city_sha256" in p for p in conventions.accuracy_problems("amanta", "mumbai"))


def test_the_engine_version_names_what_an_approval_is_bound_to():
    assert engine.ENGINE_VERSION.startswith(
        f"skyfield-{importlib.metadata.version('skyfield')}/jplephem-{importlib.metadata.version('jplephem')}/de440s/"
    )
    ids = {k: conventions.identity(k, "mumbai") for k in conventions.all_conventions()}
    assert ids["amanta"]["convention_sha256"] != ids["purnimanta"]["convention_sha256"]
    assert ids["amanta"]["golden_sha256"] and ids["purnimanta"]["golden_sha256"] is None


def test_conventions_and_cities_are_well_formed():
    convs = conventions.all_conventions()
    assert set(convs) == {"purnimanta", "amanta"}
    for c in convs.values():
        assert c.rule_for("memorial") == "aparahna" and c.rule_for("birthday") == "sunrise"
        assert set(c.labels) >= {"en", "hi"}
    cs = conventions.cities()
    assert set(cs) >= set(transcribe_rp.METROS)  # the Rashtriya Panchang publishes their sunrise
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
def _amanta() -> dict:
    table = conventions.golden_table("amanta")
    assert table is not None
    return table


def test_the_amanta_table_is_transcribed_from_the_rashtriya_panchang_not_generated():
    t = _amanta()
    src = t["sources"]["rashtriya-panchang-1948-online"]
    assert src["publisher"].startswith("India Meteorological Department")
    assert "NOT yet verified" in src["usage"]  # permission to reproduce is a human sign-off
    assert {"kartika.html", "tables.html"} <= set(src["pages"])
    assert all(len(v) == 64 for v in src["pages"].values())
    assert "no approval" in t["status"]
    # each ending keeps the text as printed, so a reviewer can check it against the page
    row = next(r for r in t["tithi_ends"] if r["ist"] == "2026-10-23T14:36")
    assert row["printed"] == "(Asvina Sukla) Dvadasi h. 14-36"
    assert (row["masa"], row["paksha"], row["tithi"], row["adhik"]) == ("ashvin", "shukla", 12, False)
    assert any(r["adhik"] and r["masa"] == "jyeshtha" for r in t["tithi_ends"])  # Mala Jyaishtha 2026


def test_golden_checker_on_the_official_table(ready):
    t = _amanta()
    small = {
        **t,
        "tithi_ends": [r for r in t["tithi_ends"] if "2026-10-20" <= r["ist"] < "2026-12-12"],
        "sunrises": [r for r in t["sunrises"] if "2026-10-21" <= r["date"] < "2026-12-10"],
    }
    report = golden_check.check(small, "amanta", "mumbai")
    # the one documented divergence keeps counting until a named reviewer accepts it
    assert len(report.mismatches) == 1 and "pending review" in report.mismatches[0]
    assert report.compared["civil_days"] > 40 and not report.passed
    assert any("3 years" in g for g in report.coverage_gaps)
    accepted = copy.deepcopy(small)
    accepted["divergences"][0]["accepted_by"] = "An independent panchang reviewer"
    assert golden_check.check(accepted, "amanta", "mumbai").mismatches == []
    # a wrong ending, a wrong month and a wrong sunrise are all caught
    bad = copy.deepcopy(small)
    first = bad["tithi_ends"][0]
    first["ist"] = (dt.datetime.fromisoformat(first["ist"]) + dt.timedelta(minutes=10)).isoformat(
        timespec="minutes"
    )
    bad["tithi_ends"][1]["masa"] = "pausha"
    next(r for r in bad["sunrises"] if r["city"] == "mumbai")["ist"] = "07:30"
    found = golden_check.check(bad, "amanta", "mumbai").mismatches
    assert any("±2 min" in m for m in found) and any("pausha" in m for m in found)
    assert any("engine sunrise" in m for m in found)
    assert any(
        "names no published source" in g
        for g in golden_check.check({**small, "sources": {}}, "amanta", "mumbai").coverage_gaps
    )


def test_every_golden_table_cites_its_sources():
    """Rows come from published panchangs: every shipped table names them, with checksums."""
    for path in Path(conventions.GOLDEN).glob("*.json"):
        table = conventions.golden_table(path.stem)
        assert table and table.get("format") == 2, path.name
        assert golden_check._sources_gaps(table) == [], (path.name, golden_check._sources_gaps(table))


# ---------------------------------------------------------------- transcribing printed editions
# Synthetic lines in the printed layout: they test the parser's refusals, not any golden value.
def _sunrise_row(nat: int, ni: int, greg: int, times: str) -> str:
    return f" {nat:>2}   {ni:>2}   {greg:>2}   {times}"


FULL = " ".join(["6 05 18 20 8 11 21 27"] * 4)


def test_national_month_starts_follow_the_editions_rule():
    starts = transcribe_rp.national_month_starts(1948)
    assert starts[0] == dt.date(2026, 3, 22) and starts[7] == dt.date(2026, 10, 23)
    assert starts[12] == dt.date(2027, 3, 22) and len(starts) == 13
    leap = transcribe_rp.national_month_starts(1946)  # 2024 is a leap year: Chaitra 1 is 21 March, 31 days
    assert leap[0] == dt.date(2024, 3, 21) and leap[1] == dt.date(2024, 4, 21)


def test_printed_spellings_are_read_and_unknown_ones_refused():
    items = transcribe_rp._tithi_items(
        transcribe_rp._normalise(
            "( Mala Sravana Krishna) Amavasya h. 8-24 then (Suddha Sravana Sukla)Pratipad h. 28-31"
        )
    )
    assert [(i["masa"], i["adhik"], i["paksha"], i["tithi"]) for i in items] == [
        ("shravana", True, "krishna", 15),
        ("shravana", False, "shukla", 1),
    ]
    assert transcribe_rp._tithi_items("(Kartika Sukla) Chaturti h. 6-40")[0]["tithi"] == 4
    with pytest.raises(transcribe_rp.TranscriptionError):
        transcribe_rp._tithi_items("(Kartika Sukla) Chaturtee h. 6-40")
    with pytest.raises(transcribe_rp.TranscriptionError):
        transcribe_rp._tithi_items("(Kartika Krishna) Purnima h. 6-40")  # Purnima ends a sukla paksha


def test_sunrise_rows_are_skipped_or_refused_never_guessed():
    head = transcribe_rp.SUNRISE_HEADER + "\n 1948  5126  2026  Sun Moon\n"
    split_digits = "6 0 5 1 8 2 0 1 8 37 -- 6 10 18 39 19 03 - - 5 29 17 52 18 11 -- 6 3 2 1 8 5 3 1 9 13 --"
    lines = [
        _sunrise_row(1, 8, 22, FULL),
        _sunrise_row(2, 9, 23, split_digits),
        _sunrise_row(3, 10, 24, FULL),
    ]
    rows, skipped = transcribe_rp.pdf_sunrise_rows(head + "\n".join(lines), "s", "p", 1948, {"mumbai"})
    assert [(r["date"], r["ist"]) for r in rows] == [("2026-03-22", "06:05"), ("2026-03-24", "06:05")]
    assert skipped == ["2026-03-23: malformed times"]
    # a 31st day in a 30-day month (the 1947 SE edition's repeated row) is an anomaly, not data
    month = [_sunrise_row(n, n + 7, (21 + n - 1) % 31 + 1, FULL) for n in range(1, 31)]
    extra = _sunrise_row(31, 8, 20, FULL)
    rows, skipped = transcribe_rp.pdf_sunrise_rows(
        head + "\n".join([*month, extra]), "s", "p", 1948, {"mumbai"}
    )
    assert len(rows) == 30 and skipped[-1].startswith("ANOMALY after 2026-04-20")
    # a row out of sequence stops the transcription
    with pytest.raises(transcribe_rp.TranscriptionError):
        transcribe_rp.pdf_sunrise_rows(head + "\n".join([lines[0], lines[2]]), "s", "p", 1948, {"mumbai"})
