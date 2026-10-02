"""Event reminders and notification delivery (ADR-0016)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import NotificationContact, NotificationDelivery
from app.models.enums import ReminderRecurrence
from app.modules.notifications import schedule
from app.modules.notifications.service import tick
from tests.conftest import owner_session
from tests.helpers import create_person
from tests.mail import all_mail

TZ = "Asia/Kolkata"


def day_in(days: int) -> dt.date:
    return dt.datetime.now(dt.UTC).date() + dt.timedelta(days=days)


def birth_on(d: dt.date, year: int = 1950) -> dict[str, Any]:
    return {"birth": {"date": {"precision": "exact", "year": year, "month": d.month, "day": d.day}}}


def fire_at(occ: dt.date, lead: int = 0, hour: int = 8) -> dt.datetime:
    return schedule.fire_time(occ, lead, hour, TZ)


def birth_event_id(client: Any, tid: str, pid: str) -> str:
    return client.get(f"/trees/{tid}/people/{pid}").json()["birth"]["event_id"]


def remind(client: Any, tid: str, event_id: str, **body: Any) -> Any:
    return client.post(f"/trees/{tid}/reminders", json={"event_id": event_id, **body})


def deliveries() -> list[NotificationDelivery]:
    with owner_session() as db:
        return list(db.scalars(select(NotificationDelivery).order_by(NotificationDelivery.created_at)))


def outbox(channel: str) -> list[dict[str, Any]]:
    d = Path(get_settings().notification_outbox_dir) / channel
    return [json.loads(f.read_text()) for f in sorted(d.glob("*.json"))] if d.exists() else []


@pytest.fixture
def mock_sms(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "sms_backend", "mock")
    monkeypatch.setattr(s, "whatsapp_backend", "mock")
    monkeypatch.setattr(s, "notification_outbox_dir", str(tmp_path / "outbox"))
    return s


def verified_phone(client: Any, channel: str = "sms", number: str = "+919876543210") -> dict[str, Any]:
    r = client.post("/me/notification-contacts", json={"channel": channel, "address": number})
    assert r.status_code == 201, r.text
    code = outbox(channel)[-1]["text"].split("code is ")[1][:6]
    r = client.post(f"/me/notification-contacts/{r.json()['id']}/verify", json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- schedule arithmetic
def test_schedule_arithmetic():
    # 08:00 in India is 02:30 UTC
    assert fire_at(dt.date(2027, 3, 10)) == dt.datetime(2027, 3, 10, 2, 30, tzinfo=dt.UTC)
    # lead days count back from the occurrence; New York observes DST
    ny = schedule.fire_time(dt.date(2027, 7, 10), 7, 9, "America/New_York")
    assert ny == dt.datetime(2027, 7, 3, 13, 0, tzinfo=dt.UTC)
    leap = schedule.Anchor(month=2, day=29, year=1948)
    assert schedule.occurrence_in(leap, 2027) == dt.date(2027, 2, 28)
    assert schedule.occurrence_in(leap, 2028) == dt.date(2028, 2, 29)
    for raw, code in (
        ({"precision": "year_only", "year": 1950}, "date_incomplete"),
        (
            {"precision": "exact", "year": 2007, "month": 3, "day": 1, "calendar": "vikram_samvat"},
            "calendar_not_supported",
        ),
        (None, "date_unknown"),
        ({"precision": "year_only", "year": 1950, "redacted": True}, "date_hidden"),
    ):
        with pytest.raises(schedule.NotSchedulable) as e:
            schedule.anchor_from_date(raw, ReminderRecurrence.ANNUAL)
        assert e.value.code == code
    # never before the event itself
    a = schedule.Anchor(month=6, day=1, year=2030)
    assert schedule.next_occurrence(a, ReminderRecurrence.ANNUAL, dt.date(2026, 1, 1)) is not None
    fires = list(
        schedule.fires(a, ReminderRecurrence.ANNUAL, [0], 8, TZ, dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    )
    assert fires == []


# ---------------------------------------------------------------- email end to end
def test_email_birthday_reminder_end_to_end(owner, tree):
    tid = tree["id"]
    occ = day_in(10)
    dadi = create_person(owner, tid, "Kamla", **birth_on(occ, 1950))
    eid = birth_event_id(owner, tid, dadi["id"])
    r = remind(owner, tid, eid, lead_days=[0, 7])
    assert r.status_code == 201, r.text
    rem = r.json()
    assert rem["kind"] == "birthday" and rem["recurrence"] == "annual"
    assert rem["channels"] == ["email"] and rem["label"] == "Kamla Iyer's birthday"
    assert rem["next_occurrence"] == occ.isoformat()
    assert rem["next_fire_at"].startswith((occ - dt.timedelta(days=7)).isoformat())
    # subscribing opted this user in for this tree
    pref = owner.get(f"/trees/{tid}/notification-preferences").json()
    assert pref["enabled"] is True and pref["exists"] is True

    before = len(all_mail(owner.user["email"]))
    res = tick(now=fire_at(occ, 7) + dt.timedelta(minutes=1))
    assert res.created == 1 and res.enqueued == 1
    mails = all_mail(owner.user["email"])[before:]
    assert len(mails) == 1
    assert "Kamla Iyer's birthday" in mails[0]["subject"] and "in 7 days" in mails[0]["subject"]
    assert f"{occ.year - 1950} years" in mails[0]["text"]
    assert mails[0]["kind"] == "reminder"
    # the same tick again (or a second scheduler) sends nothing more
    tick(now=fire_at(occ, 7) + dt.timedelta(minutes=2))
    assert len(all_mail(owner.user["email"])) == before + 1
    # the day itself
    tick(now=fire_at(occ, 0) + dt.timedelta(minutes=1))
    assert "today" in all_mail(owner.user["email"])[-1]["subject"]
    hist = owner.get(f"/trees/{tid}/notifications").json()["items"]
    assert [h["status"] for h in hist] == ["sent", "sent"]
    assert {h["lead_days"] for h in hist} == {0, 7}
    assert hist[0]["provider"] == "email:file" and hist[0]["label"] == "Kamla Iyer's birthday"
    assert "text" not in hist[0] and "to" not in hist[0]
    # next year's reminder is already scheduled
    rem = owner.get(f"/trees/{tid}/reminders").json()[0]
    assert rem["next_fire_at"].startswith(str(occ.year + 1)[:4])


def test_test_send_and_upcoming(owner, tree, member_factory):
    tid = tree["id"]
    occ = day_in(5)
    p = create_person(owner, tid, "Ravi", **birth_on(occ, 1980))
    living = create_person(owner, tid, "Nita", status="living", **birth_on(day_in(6), 1995))
    eid = birth_event_id(owner, tid, p["id"])
    rem = remind(owner, tid, eid).json()
    r = owner.post(f"/trees/{tid}/reminders/{rem['id']}/test")
    assert r.status_code == 200 and [d["status"] for d in r.json()] == ["sent"]
    assert all_mail(owner.user["email"])[-1]["subject"].startswith("[Test] Reminder:")
    up = owner.get(f"/trees/{tid}/reminders/upcoming?days=30").json()
    names = {u["display_name"]: u for u in up}
    assert names["Ravi Iyer"]["reminder_id"] == rem["id"] and names["Ravi Iyer"]["days_until"] == 5
    assert names["Ravi Iyer"]["anniversary"] == occ.year - 1980
    assert "Nita Iyer" in names  # the owner may see a living person's full birth date
    viewer = member_factory(["VIEWER"])
    seen = {u["display_name"] for u in viewer.get(f"/trees/{tid}/reminders/upcoming").json()}
    assert "Ravi Iyer" in seen and "Nita Iyer" not in seen  # living: year only for viewers
    mine = owner.get(f"/trees/{tid}/reminders/upcoming?scope=mine").json()
    assert [u["display_name"] for u in mine] == ["Ravi Iyer"]
    assert living  # created for the visibility check above


# ---------------------------------------------------------------- privacy
def test_reminder_needs_the_visible_full_date(owner, tree, member_factory):
    tid = tree["id"]
    nita = create_person(owner, tid, "Nita", status="living", **birth_on(day_in(20), 1995))
    eid = birth_event_id(owner, tid, nita["id"])
    viewer = member_factory(["VIEWER"])
    r = remind(viewer, tid, eid)
    assert r.status_code == 422 and r.json()["error"]["code"] in ("date_hidden", "date_incomplete")
    yearonly = create_person(owner, tid, "Old", birth={"date": {"precision": "year_only", "year": 1900}})
    r = remind(owner, tid, birth_event_id(owner, tid, yearonly["id"]))
    assert r.status_code == 422 and r.json()["error"]["code"] == "date_incomplete"
    hidden = create_person(owner, tid, "Secret", privacy_level="PRIVATE_TREE_ADMINS", **birth_on(day_in(3)))
    assert remind(viewer, tid, birth_event_id(owner, tid, hidden["id"])).status_code == 404


def test_visibility_is_rechecked_at_send_time(owner, tree, member_factory):
    tid = tree["id"]
    occ = day_in(12)
    p = create_person(owner, tid, "Mohan", **birth_on(occ, 1940))
    eid = birth_event_id(owner, tid, p["id"])
    member = member_factory(["VIEWER"], name="Cousin")
    assert remind(member, tid, eid).status_code == 201
    before = len(all_mail(member.user["email"]))
    # the person is made private after the reminder was set
    r = owner.put(f"/trees/{tid}/people/{p['id']}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 200
    tick(now=fire_at(occ) + dt.timedelta(minutes=1))
    assert len(all_mail(member.user["email"])) == before
    d = [x for x in deliveries() if x.user_id.hex == member.user["id"].replace("-", "")]
    assert [(x.status.value, x.cancelled_reason) for x in d] == [("cancelled", "no_longer_visible")]
    # the member cannot list their stale reminder's details either
    assert member.get(f"/trees/{tid}/reminders").json()[0]["deliverable"] is False


def test_removed_member_gets_nothing(owner, tree, member_factory):
    tid = tree["id"]
    occ = day_in(15)
    p = create_person(owner, tid, "Gita", **birth_on(occ, 1945))
    member = member_factory(["VIEWER"], name="Ex member")
    assert remind(member, tid, birth_event_id(owner, tid, p["id"])).status_code == 201
    members = owner.get(f"/trees/{tid}/members").json()
    mid = next(m["id"] for m in members if m["user_id"] == member.user["id"])
    assert owner.delete(f"/trees/{tid}/members/{mid}").status_code == 200
    tick(now=fire_at(occ) + dt.timedelta(minutes=1))
    assert [(x.status.value, x.cancelled_reason) for x in deliveries()] == [("cancelled", "not_a_member")]


def test_reminders_are_private_to_their_owner(owner, tree, member_factory):
    tid = tree["id"]
    p = create_person(owner, tid, "Hari", **birth_on(day_in(40)))
    rem = remind(owner, tid, birth_event_id(owner, tid, p["id"])).json()
    other = member_factory(["FAMILY_ADMIN"])
    assert other.get(f"/trees/{tid}/reminders").json() == []
    assert other.patch(f"/trees/{tid}/reminders/{rem['id']}", json={"active": False}).status_code == 404
    assert other.delete(f"/trees/{tid}/reminders/{rem['id']}").status_code == 404
    assert other.post(f"/trees/{tid}/reminders/{rem['id']}/test").status_code == 404
    assert other.get(f"/trees/{tid}/notifications").json()["items"] == []
    # one reminder per event and user
    assert remind(owner, tid, birth_event_id(owner, tid, p["id"])).status_code == 409


def test_paused_preferences_and_deleted_reminders_send_nothing(owner, tree):
    tid = tree["id"]
    occ = day_in(9)
    a = create_person(owner, tid, "A", **birth_on(occ))
    b = create_person(owner, tid, "B", **birth_on(occ, 1960))
    ra = remind(owner, tid, birth_event_id(owner, tid, a["id"])).json()
    remind(owner, tid, birth_event_id(owner, tid, b["id"]))
    assert owner.delete(f"/trees/{tid}/reminders/{ra['id']}").status_code == 200
    r = owner.put(
        f"/trees/{tid}/notification-preferences",
        json={
            "enabled": False,
            "channels": ["email"],
            "timezone": TZ,
            "send_hour": 8,
            "default_lead_days": [0],
        },
    )
    assert r.status_code == 200 and r.json()["enabled"] is False
    before = len(all_mail(owner.user["email"]))
    tick(now=fire_at(occ) + dt.timedelta(minutes=1))
    assert len(all_mail(owner.user["email"])) == before
    assert [(d.status.value, d.cancelled_reason) for d in deliveries()] == [
        ("cancelled", "notifications_paused")
    ]


def test_preferences_validation(owner, tree):
    tid = tree["id"]
    base = {"enabled": True, "channels": ["email"], "timezone": TZ, "send_hour": 8, "default_lead_days": [0]}
    assert (
        owner.put(
            f"/trees/{tid}/notification-preferences", json={**base, "timezone": "Mars/Base"}
        ).status_code
        == 422
    )
    assert (
        owner.put(f"/trees/{tid}/notification-preferences", json={**base, "send_hour": 24}).status_code == 422
    )
    assert (
        owner.put(
            f"/trees/{tid}/notification-preferences", json={**base, "default_lead_days": [400]}
        ).status_code
        == 422
    )
    r = owner.put(f"/trees/{tid}/notification-preferences", json={**base, "channels": ["sms"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "channel_unavailable"
    r = owner.put(f"/trees/{tid}/notification-preferences", json={**base, "default_lead_days": [7, 1, 1]})
    assert r.json()["default_lead_days"] == [1, 7]


def test_one_time_reminder_rules(owner, tree):
    tid = tree["id"]
    p = create_person(owner, tid, "Om")
    past = owner.post(
        f"/trees/{tid}/events",
        json={
            "category": "graduation",
            "participants": [{"person_id": p["id"]}],
            "date": {"precision": "exact", "year": 2001, "month": 5, "day": 1},
        },
    ).json()
    r = remind(owner, tid, past["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "date_in_past"
    r = remind(owner, tid, past["id"], recurrence="annual")  # remember it every year instead
    assert r.status_code == 201 and r.json()["kind"] == "one_time"
    soon = day_in(4)
    fut = owner.post(
        f"/trees/{tid}/events",
        json={
            "category": "engagement",
            "title": "Om's engagement",
            "participants": [{"person_id": p["id"]}],
            "date": {"precision": "exact", "year": soon.year, "month": soon.month, "day": soon.day},
        },
    ).json()
    r = remind(owner, tid, fut["id"], lead_days=[1])
    assert (
        r.status_code == 201 and r.json()["recurrence"] == "none" and r.json()["label"] == "Om's engagement"
    )
    tick(now=fire_at(soon, 1) + dt.timedelta(minutes=1))
    assert "Om's engagement" in all_mail(owner.user["email"])[-1]["subject"]
    rem = owner.get(f"/trees/{tid}/reminders?event_id={fut['id']}").json()[0]
    assert rem["next_fire_at"] is None and rem["active"] is False  # done


# ---------------------------------------------------------------- SMS / WhatsApp
def test_phone_contact_verification_and_encryption(owner, mock_sms):
    r = owner.post("/me/notification-contacts", json={"channel": "sms", "address": "98765 43210"})
    assert r.status_code == 422  # E.164 only
    r = owner.post("/me/notification-contacts", json={"channel": "sms", "address": "+91 98765 43210"})
    assert (
        r.status_code == 201 and r.json()["address_hint"] == "+91******3210" and r.json()["verified"] is False
    )
    cid = r.json()["id"]
    msg = outbox("sms")[-1]
    assert msg["to"] == "+919876543210" and msg["kind"] == "verify_contact"
    code = msg["text"].split("code is ")[1][:6]
    bad = "000000" if code != "000000" else "111111"
    r = owner.post(f"/me/notification-contacts/{cid}/verify", json={"code": bad})
    assert r.status_code == 422 and r.json()["error"]["code"] == "code_invalid"
    r = owner.post(f"/me/notification-contacts/{cid}/verify", json={"code": code})
    assert r.status_code == 200 and r.json()["verified"] is True
    assert "9876543210" not in owner.get("/me/notification-contacts").text
    with owner_session() as db:
        stored = db.scalar(select(NotificationContact.address_enc))
    assert stored and "9876543210" not in stored
    assert owner.get("/notification-channels").json() == {"email": True, "sms": True, "whatsapp": True}


def test_contact_verification_attempts_are_limited(owner, mock_sms):
    r = owner.post("/me/notification-contacts", json={"channel": "whatsapp", "address": "+919000000001"})
    cid = r.json()["id"]
    code = outbox("whatsapp")[-1]["text"].split("code is ")[1][:6]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert owner.post(f"/me/notification-contacts/{cid}/verify", json={"code": wrong}).status_code == 422
    r = owner.post(f"/me/notification-contacts/{cid}/verify", json={"code": code})
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_many_attempts"


def test_sms_reminder_carries_no_names_and_retries_then_fails(owner, tree, mock_sms, monkeypatch):
    tid = tree["id"]
    verified_phone(owner)
    occ = day_in(11)
    p = create_person(owner, tid, "Savitri", **birth_on(occ, 1952))
    r = remind(owner, tid, birth_event_id(owner, tid, p["id"]), channels=["sms", "email"])
    assert r.status_code == 201, r.text
    tick(now=fire_at(occ) + dt.timedelta(minutes=1))
    sms = outbox("sms")[-1]
    assert sms["kind"] == "reminder" and "Savitri" not in sms["text"] and "birthday" in sms["text"]
    assert {d.status.value for d in deliveries()} == {"sent"}

    # a provider outage: retried with back-off, then failed after the last attempt
    monkeypatch.setenv("VSH_NOTIFICATION_MOCK_FAIL", "sms")
    occ2 = day_in(13)
    q = create_person(owner, tid, "Shyam", **birth_on(occ2, 1955))
    remind(owner, tid, birth_event_id(owner, tid, q["id"]), channels=["sms"])
    now = fire_at(occ2) + dt.timedelta(minutes=1)
    tick(now=now)
    for expected in (1, 2, 3):
        d = next(x for x in deliveries() if x.occurrence_date == occ2)
        assert d.status.value == "retrying" and d.attempts == expected and d.last_error_code == "mock_failure"
        tick(now=d.next_attempt_at + dt.timedelta(seconds=1))
    d = next(x for x in deliveries() if x.occurrence_date == occ2)
    assert d.status.value == "failed" and d.attempts == 4 and d.next_attempt_at is None


def test_sms_channel_needs_a_verified_number(owner, tree, mock_sms):
    tid = tree["id"]
    p = create_person(owner, tid, "X", **birth_on(day_in(30)))
    r = remind(owner, tid, birth_event_id(owner, tid, p["id"]), channels=["sms"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "contact_not_verified"


def test_channels_unavailable_when_disabled(owner, tree):
    tid = tree["id"]
    p = create_person(owner, tid, "X", **birth_on(day_in(30)))
    r = remind(owner, tid, birth_event_id(owner, tid, p["id"]), channels=["whatsapp"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "channel_unavailable"
    r = owner.post("/me/notification-contacts", json={"channel": "sms", "address": "+919876543210"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "channel_unavailable"
    assert owner.get("/notification-channels").json() == {"email": True, "sms": False, "whatsapp": False}


def test_production_refuses_mock_providers():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="mock"):
        Settings(env="production", sms_backend="mock")
