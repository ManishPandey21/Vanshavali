"""Family calendar, calendar feed, lunar reminders and conversion (ADR-0022 §4-§8, §10).

Threats T49 (the feed) and T50 (lunar dates, observance places, the calendar). Lunar computation
runs only behind the gate; tests that need it switch the flag on and mark a convention verified
for the test only (no golden table ships, so nothing is offered in a real deployment).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AuditEvent, CalendarFeed
from app.modules.calendar import conventions, engine, ephemeris
from tests.conftest import new_tree, owner_session
from tests.helpers import create_person

LUNAR = {"masa": "bhadrapada", "paksha": "krishna", "tithi": 8, "month_convention": "purnimanta"}


def today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def day_in(days: int) -> dt.date:
    return today() + dt.timedelta(days=days)


def exact(d: dt.date, year: int) -> dict[str, Any]:
    return {"precision": "exact", "year": year, "month": d.month, "day": d.day}


def window(client: Any, t: str, start: dt.date | None = None, end: dt.date | None = None) -> dict[str, Any]:
    start = start or today()
    end = end or start + dt.timedelta(days=365)
    r = client.get(f"/trees/{t}/calendar", params={"from": start.isoformat(), "to": end.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def lunar_on(monkeypatch):
    """Switch tithi dates on: engine present, flag on, purnimanta signed off at Varanasi and London."""
    if not engine.available():
        if os.environ.get("VSH_REQUIRE_EPHEMERIS"):
            pytest.fail("the ephemeris is required here")
        pytest.skip("ephemeris not installed")
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", True)
    # purnimanta has no golden table yet: stand in a digest for one, and nothing else
    real_digest = conventions.golden_digest
    monkeypatch.setattr(
        conventions, "golden_digest", lambda k: "test-table" if k == "purnimanta" else real_digest(k)
    )
    places = ("varanasi", "london")
    signed = {"reviewed_on": "2026-11-08", "record": "test"}
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
                "convention": "purnimanta",
                "city": c,
                **conventions.identity("purnimanta"),
                "prepared_by": "A developer",
                "reviewer": "An independent panchang reviewer",
                **signed,
            }
            for c in places
        ],
        "activation": [
            {
                "convention": "purnimanta",
                "city": c,
                "approved_by": "Product owner",
                "approved_on": "2026-11-08",
            }
            for c in places
        ],
    }
    monkeypatch.setattr(conventions, "approvals", lambda: data)


# ---------------------------------------------------------------- settings
def test_settings_are_chosen_by_an_admin_never_inferred(owner, tree, member_factory):
    t = tree["id"]
    s = owner.get(f"/trees/{t}/calendar-settings").json()
    assert (s["convention"], s["observance_city"], s["lunar_enabled"]) == (None, None, False)
    assert {c["key"]: c["offered"] for c in s["conventions"]} == {"purnimanta": False, "amanta": False}
    assert {"varanasi", "london", "san_francisco"} <= {c["key"] for c in s["cities"]}
    viewer = member_factory(["VIEWER"])
    assert viewer.get(f"/trees/{t}/calendar-settings").status_code == 200
    assert viewer.put(f"/trees/{t}/calendar-settings", json={"convention": "amanta"}).status_code == 403
    r = owner.put(
        f"/trees/{t}/calendar-settings", json={"convention": "purnimanta", "observance_city": "varanasi"}
    )
    assert r.status_code == 200 and (r.json()["convention"], r.json()["observance_city"]) == (
        "purnimanta",
        "varanasi",
    )
    for bad in ({"convention": "tamil_solar"}, {"observance_city": "atlantis"}):
        assert owner.put(f"/trees/{t}/calendar-settings", json=bad).status_code == 422
    other = new_tree(viewer, "Viewer's family")
    assert viewer.put(f"/trees/{t}/calendar-settings", json={"convention": "amanta"}).status_code == 403
    assert owner.get(f"/trees/{other['id']}/calendar-settings").status_code == 404


# ---------------------------------------------------------------- the calendar (T50)
def test_calendar_shows_only_dates_the_reader_may_see_in_full(owner, tree, member_factory):
    t = tree["id"]
    occ = day_in(10)
    create_person(
        owner, t, "Kamla", birth={"date": exact(occ, 1940)}, death={"date": exact(day_in(20), 2001)}
    )
    create_person(owner, t, "Nita", status="living", birth={"date": exact(day_in(12), 1995)})
    cal = window(owner, t)
    labels = {(e["label"], e["kind"]) for e in cal["entries"]}
    assert ("Kamla Iyer's birthday", "birthday") in labels and (
        "Remembering Kamla Iyer",
        "memorial",
    ) in labels
    assert ("Nita Iyer's birthday", "birthday") in labels  # the owner may see her full birth date
    kamla = next(e for e in cal["entries"] if e["label"] == "Kamla Iyer's birthday")
    assert (
        kamla["day"] == occ.isoformat()
        and kamla["anniversary"] == occ.year - 1940
        and kamla["basis"] == "solar"
    )
    assert cal["lunar_unavailable"] == "disabled"
    viewer = member_factory(["VIEWER"])
    seen = {e["label"] for e in window(viewer, t)["entries"]}
    assert "Kamla Iyer's birthday" in seen and "Nita Iyer's birthday" not in seen  # living: year only
    r = owner.get(f"/trees/{t}/calendar", params={"from": "2026-01-01", "to": "2027-06-01"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "range_too_long"
    stranger = new_tree(viewer, "Elsewhere")
    assert (
        viewer.get(f"/trees/{t}/calendar", params={"from": "2026-01-01", "to": "2026-02-01"}).status_code
        == 200
    )
    assert (
        owner.get(
            f"/trees/{stranger['id']}/calendar", params={"from": "2026-01-01", "to": "2026-02-01"}
        ).status_code
        == 404
    )


def test_tithi_dates_follow_the_same_privacy_and_appear_only_when_offered(
    owner, tree, member_factory, lunar_on
):
    t = tree["id"]
    owner.put(
        f"/trees/{t}/calendar-settings", json={"convention": "purnimanta", "observance_city": "varanasi"}
    )
    create_person(owner, t, "Dadaji", death={"date": {"precision": "unknown", "lunar": LUNAR}})
    living = {
        "precision": "exact",
        "year": 1990,
        "month": 3,
        "day": 4,
        "lunar": LUNAR | {"paksha": "shukla", "tithi": 5},
    }
    create_person(owner, t, "Asha", status="living", birth={"date": living})
    cal = window(owner, t)
    lunar = [e for e in cal["entries"] if e["basis"] == "lunar"]
    assert cal["lunar_unavailable"] is None
    dadaji = next(e for e in lunar if e["label"] == "Remembering Dadaji Iyer")
    assert (dadaji["lunar_label"], dadaji["convention"], dadaji["rule"], dadaji["city"]) == (
        "Bhadrapada Krishna Ashtami",
        "purnimanta",
        "aparahna",
        "varanasi",
    )
    assert any(e["label"] == "Asha Iyer's birthday" for e in lunar)
    # a viewer sees the deceased ancestor's tithi, never a living person's (her date is year-only)
    viewer = member_factory(["VIEWER"])
    seen = {e["label"] for e in window(viewer, t)["entries"] if e["basis"] == "lunar"}
    assert seen == {"Remembering Dadaji Iyer"}
    # the amanta convention has not passed its golden table: no tithi dates for it
    owner.put(f"/trees/{t}/calendar-settings", json={"convention": "amanta"})
    assert window(owner, t)["lunar_unavailable"] == "convention_not_offered"


# ---------------------------------------------------------------- conversion (a suggestion)
def test_conversion_is_a_suggestion_behind_the_gate(owner, tree, monkeypatch):
    t = tree["id"]
    owner.put(
        f"/trees/{t}/calendar-settings", json={"convention": "purnimanta", "observance_city": "varanasi"}
    )
    body = {"lunar": LUNAR | {"samvat": "vikram", "year": 2045}}
    r = owner.post(f"/trees/{t}/calendar/convert", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "lunar_not_available"


def test_conversion_suggests_and_stores_nothing(owner, tree, lunar_on):
    t = tree["id"]
    owner.put(
        f"/trees/{t}/calendar-settings", json={"convention": "purnimanta", "observance_city": "varanasi"}
    )
    p = create_person(
        owner,
        t,
        "Ramesh",
        death={"date": {"precision": "unknown", "lunar": LUNAR | {"samvat": "vikram", "year": 2045}}},
    )
    r = owner.post(f"/trees/{t}/calendar/convert", json={"lunar": LUNAR | {"samvat": "vikram", "year": 2045}})
    assert r.status_code == 200, r.text
    out = r.json()
    day = dt.date.fromisoformat(out["suggestion"])
    assert day.year in (1988, 1989) and out["engine_version"] == engine.ENGINE_VERSION
    assert (out["convention"], out["city"]) == ("purnimanta", "varanasi")
    # nothing was written into the record
    death = owner.get(f"/trees/{t}/people/{p['id']}").json()["death"]["date"]
    assert death.get("year") is None and death["lunar"]["tithi"] == 8
    r = owner.post(f"/trees/{t}/calendar/convert", json={"lunar": LUNAR})
    assert r.status_code == 422 and r.json()["error"]["code"] == "year_required"


# ---------------------------------------------------------------- lunar reminders
def _death_event(client: Any, t: str, pid: str) -> str:
    return client.get(f"/trees/{t}/people/{pid}").json()["death"]["event_id"]


def test_lunar_reminders_are_refused_until_offered(owner, tree):
    t = tree["id"]
    owner.put(
        f"/trees/{t}/calendar-settings", json={"convention": "purnimanta", "observance_city": "varanasi"}
    )
    p = create_person(owner, t, "Dadaji", death={"date": {"precision": "unknown", "lunar": LUNAR}})
    r = owner.post(
        f"/trees/{t}/reminders", json={"event_id": _death_event(owner, t, p["id"]), "date_rule": "lunar"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "lunar_not_available"


def test_a_lunar_reminder_follows_the_tithi_at_its_city(owner, tree, member_factory, lunar_on):
    t = tree["id"]
    p = create_person(owner, t, "Dadaji", death={"date": {"precision": "unknown", "lunar": LUNAR}})
    eid = _death_event(owner, t, p["id"])
    r = owner.post(f"/trees/{t}/reminders", json={"event_id": eid, "date_rule": "lunar"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "convention_required"
    owner.put(f"/trees/{t}/calendar-settings", json={"convention": "purnimanta"})
    r = owner.post(f"/trees/{t}/reminders", json={"event_id": eid, "date_rule": "lunar"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "observance_place_required"
    owner.put(f"/trees/{t}/calendar-settings", json={"observance_city": "varanasi"})
    r = owner.post(f"/trees/{t}/reminders", json={"event_id": eid, "date_rule": "lunar"})
    assert r.status_code == 201, r.text
    rem = r.json()
    assert (rem["date_rule"], rem["convention"], rem["observance_city"], rem["kind"]) == (
        "lunar",
        "purnimanta",
        "varanasi",
        "memorial",
    )
    nxt = dt.date.fromisoformat(rem["next_occurrence"])
    cal = window(owner, t)
    assert any(e["basis"] == "lunar" and e["day"] == nxt.isoformat() for e in cal["entries"])
    # a member in London observes the same tithi on London's day
    member = member_factory(["CONTRIBUTOR"], name="Cousin abroad")
    r = member.post(
        f"/trees/{t}/reminders", json={"event_id": eid, "date_rule": "lunar", "observance_city": "london"}
    )
    assert r.status_code == 201 and r.json()["observance_city"] == "london"
    assert abs((dt.date.fromisoformat(r.json()["next_occurrence"]) - nxt).days) <= 1
    # a solar reminder needs a Gregorian day, which this event does not have
    r = member.post(f"/trees/{t}/reminders", json={"event_id": eid})
    assert r.status_code in (409, 422)


def test_a_lunar_reminder_stops_when_the_convention_is_no_longer_offered(owner, tree, monkeypatch, lunar_on):
    t = tree["id"]
    owner.put(
        f"/trees/{t}/calendar-settings", json={"convention": "purnimanta", "observance_city": "varanasi"}
    )
    p = create_person(owner, t, "Dadaji", death={"date": {"precision": "unknown", "lunar": LUNAR}})
    rem = owner.post(
        f"/trees/{t}/reminders", json={"event_id": _death_event(owner, t, p["id"]), "date_rule": "lunar"}
    ).json()
    monkeypatch.setattr(get_settings(), "lunar_calendar_enabled", False)
    got = owner.get(f"/trees/{t}/reminders").json()
    assert [(x["id"], x["deliverable"]) for x in got] == [(rem["id"], False)]


def test_tithi_dates_are_offered_only_at_signed_off_cities(owner, tree, lunar_on):
    """Approval is per convention and city (owner decision 3): Delhi is not signed off here."""
    t = tree["id"]
    owner.put(f"/trees/{t}/calendar-settings", json={"convention": "purnimanta", "observance_city": "delhi"})
    settings = owner.get(f"/trees/{t}/calendar-settings").json()
    purnimanta = next(c for c in settings["conventions"] if c["key"] == "purnimanta")
    assert (purnimanta["offered"], purnimanta["golden_verified"]) == (False, False)
    assert window(owner, t)["lunar_unavailable"] == "convention_not_offered"
    r = owner.post(f"/trees/{t}/calendar/convert", json={"lunar": LUNAR | {"samvat": "vikram", "year": 2045}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "lunar_not_available"
    p = create_person(owner, t, "Dadaji", death={"date": {"precision": "unknown", "lunar": LUNAR}})
    eid = _death_event(owner, t, p["id"])
    r = owner.post(f"/trees/{t}/reminders", json={"event_id": eid, "date_rule": "lunar"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "lunar_not_available"
    # the same tithi at a signed-off city is offered
    r = owner.post(
        f"/trees/{t}/reminders", json={"event_id": eid, "date_rule": "lunar", "observance_city": "varanasi"}
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------- the feed (T49)
def _feed(client: Any, url: str) -> Any:
    path = url.split("/api/v1", 1)[1]
    return client.get(path)


def test_feed_is_private_minimal_revocable_and_follows_access(owner, tree, member_factory, make_client):
    t = tree["id"]
    create_person(owner, t, "Kamla", birth={"date": exact(day_in(10), 1940)})
    assert owner.get(f"/trees/{t}/calendar-feed").json() == {
        "active": False,
        "include_names": False,
        "created_at": None,
        "last_used_at": None,
        "url": None,
    }
    created = owner.post(f"/trees/{t}/calendar-feed", json={}).json()
    url = created["url"]
    assert created["active"] and url.endswith(".ics") and created["include_names"] is False
    token = url.rsplit("/", 1)[1][:-4]
    assert len(token) >= 43
    assert owner.get(f"/trees/{t}/calendar-feed").json()["url"] is None  # shown once
    with owner_session() as db:
        stored = db.scalars(select(CalendarFeed)).one()
        assert stored.token_hash != token and token not in stored.token_hash
        assert token not in str([e.details for e in db.scalars(select(AuditEvent))])

    anon = make_client()
    r = _feed(anon, url)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert r.headers["cache-control"] == "no-store"
    body = r.text
    assert "BEGIN:VCALENDAR" in body and "SUMMARY:Birthday" in body
    assert "Kamla" not in body  # minimal by default: no names to a third-party calendar
    assert _feed(anon, url.replace(token, "x" * 43)).status_code == 404

    # names only by explicit choice; replacing the feed kills the old URL
    url2 = owner.post(f"/trees/{t}/calendar-feed", json={"include_names": True}).json()["url"]
    assert _feed(anon, url).status_code == 404
    assert "Kamla Iyer" in _feed(anon, url2).text
    # revoke
    assert owner.delete(f"/trees/{t}/calendar-feed").status_code == 200
    assert _feed(anon, url2).status_code == 404
    assert owner.delete(f"/trees/{t}/calendar-feed").status_code == 404


def test_a_removed_member_gets_an_empty_feed(owner, tree, member_factory, make_client):
    t = tree["id"]
    create_person(owner, t, "Kamla", birth={"date": exact(day_in(10), 1940)})
    member = member_factory(["VIEWER"], name="Leaving cousin")
    url = member.post(f"/trees/{t}/calendar-feed", json={"include_names": True}).json()["url"]
    anon = make_client()
    assert "Kamla Iyer" in _feed(anon, url).text
    mid = next(
        m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["display_name"] == "Leaving cousin"
    )
    assert owner.delete(f"/trees/{t}/members/{mid}").status_code == 200
    r = _feed(anon, url)
    assert r.status_code == 200 and "VEVENT" not in r.text  # nothing about the family any more
    # each member manages only their own feed
    other = member_factory(["VIEWER"], name="Another")
    assert other.delete(f"/trees/{t}/calendar-feed").status_code == 404


def test_feed_rate_limit_and_token_shape(owner, tree, make_client, monkeypatch):
    t = tree["id"]
    url = owner.post(f"/trees/{t}/calendar-feed", json={}).json()["url"]
    anon = make_client()
    assert anon.get("/calendar-feeds/short.ics").status_code == 422
    assert anon.get("/calendar-feeds/" + "a" * 43 + "%2F..ics").status_code in (404, 422)
    from app.modules.calendar import service

    monkeypatch.setattr(service, "FEEDS_PER_MINUTE", 2)
    codes = [_feed(anon, url).status_code for _ in range(3)]
    assert codes[:2] == [200, 200] and codes[2] == 429


def test_the_feed_token_is_never_logged(owner, tree, make_client, caplog):
    url = owner.post(f"/trees/{tree['id']}/calendar-feed", json={}).json()["url"]
    token = url.rsplit("/", 1)[1][:-4]
    with caplog.at_level(logging.DEBUG):
        assert _feed(make_client(), url).status_code == 200
    access = [r for r in caplog.records if r.name == "app.access"]
    assert access and access[-1].route.endswith("/calendar-feeds/{token}.ics")  # type: ignore[attr-defined]
    server = [r for r in caplog.records if r.name != "httpx"]  # httpx is the test client itself
    leaks = [(r.name, r.getMessage()[:200]) for r in server if token in (r.getMessage() + str(r.__dict__))]
    assert leaks == []
