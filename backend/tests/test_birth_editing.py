"""Profile birth edits preserve claims, legacy privacy, and scheduled occurrences."""

import datetime as dt
import threading
import uuid

import pytest
from sqlalchemy import select

from app.models import Event, EventReminder, NotificationDelivery
from app.models.enums import DeliveryStatus
from app.modules.notifications import service as notifications
from tests.conftest import owner_session
from tests.helpers import create_person
from tests.mail import all_mail
from tests.test_reminders import birth_event_id, birth_on, day_in, fire_at, remind
from tests.test_takedown_ownership import _ctx, _run, _wait_until_blocked


def event(client, tid, pid):
    return client.get(f"/trees/{tid}/people/{pid}/events").json()[0]


def test_field_scoped_birth_edit_and_stale_revision(owner, tree):
    tid = tree["id"]
    p = create_person(owner, tid, "Ravi", **birth_on(day_in(20)))
    e = event(owner, tid, p["id"])
    url = f"/trees/{tid}/events/{e['id']}"
    changed = owner.patch(
        url,
        json={"date": {"precision": "year_only", "year": 1951}, "expected_revision": e.get("revision", 1)},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["id"] == e["id"]
    assert changed.json()["date"].get("month") is None
    stale = owner.patch(
        url,
        json={"date": {"precision": "year_only", "year": 1999}, "expected_revision": e.get("revision", 1)},
    )
    assert stale.status_code == 409, stale.text
    assert event(owner, tid, p["id"])["date"]["year"] == 1951


@pytest.mark.parametrize(
    "patch",
    [
        {"date": {"precision": "exact", "year": 1980, "month": 1, "day": 2}},
        {"time": {"value": "04:12", "precision": "approximate", "source": "verbal"}},
        {"timezone_id": "Asia/Kolkata"},
        {"utc_offset_minutes": 330},
        {"place_as_recorded": "Private hospital"},
    ],
)
def test_general_editor_cannot_overwrite_hidden_birth_fields(owner, tree, member_factory, patch):
    tid = tree["id"]
    p = create_person(owner, tid, "Protected", status="living", **birth_on(day_in(20)))
    eid = birth_event_id(owner, tid, p["id"])
    owner.put(
        f"/trees/{tid}/people/{p['id']}/privacy",
        json={"field_privacy": {"birth_place_detail": "PRIVATE_SELF"}},
    )
    editor = member_factory(["CONTRIBUTOR"])
    before = event(owner, tid, p["id"])
    response = editor.patch(f"/trees/{tid}/events/{eid}", json=patch)
    assert response.status_code == 403, response.text
    assert event(owner, tid, p["id"]) == before


def test_legacy_admin_access_and_hidden_time_are_preserved(owner, tree, member_factory):
    tid = tree["id"]
    p = create_person(
        owner,
        tid,
        "Protected",
        status="living",
        birth={
            "date": {"precision": "exact", "year": 1980, "month": 3, "day": 2},
            "time": {"value": "04:12:34", "precision": "approximate", "source": "verbal"},
        },
    )
    eid = birth_event_id(owner, tid, p["id"])
    owner.put(
        f"/trees/{tid}/people/{p['id']}/privacy", json={"field_privacy": {"birth_date_full": "TREE_MEMBERS"}}
    )
    editor = member_factory(["CONTRIBUTOR"])
    r = editor.patch(f"/trees/{tid}/events/{eid}", json={"date": {"precision": "year_only", "year": 1981}})
    assert r.status_code == 200, r.text
    assert r.json()["time"] is None
    admin = member_factory(["FAMILY_ADMIN"])
    assert event(admin, tid, p["id"])["time"]["value"] == "04:12:34"


def test_earlier_date_reschedules_and_incomplete_date_pauses_then_resumes(owner, tree):
    tid = tree["id"]
    old, new = day_in(30), day_in(5)
    p = create_person(owner, tid, "Ravi", **birth_on(old))
    eid = birth_event_id(owner, tid, p["id"])
    rid = remind(owner, tid, eid).json()["id"]
    url = f"/trees/{tid}/events/{eid}"
    assert owner.patch(url, json={"date": birth_on(new)["birth"]["date"]}).status_code == 200
    with owner_session() as db:
        r = db.get(EventReminder, uuid.UUID(rid))
        assert r.next_fire_at == fire_at(new)
    assert owner.patch(url, json={"date": {"precision": "year_only", "year": 1950}}).status_code == 200
    with owner_session() as db:
        assert db.get(EventReminder, uuid.UUID(rid)).next_fire_at is None
    assert owner.patch(url, json={"date": birth_on(new)["birth"]["date"]}).status_code == 200
    before = len(all_mail(owner.user["email"]))
    notifications.tick(now=fire_at(new) + dt.timedelta(minutes=1))
    notifications.tick(now=fire_at(new) + dt.timedelta(minutes=2))
    assert len(all_mail(owner.user["email"])) == before + 1


def test_edit_cancels_queued_occurrence_without_sending_old_date(owner, tree, monkeypatch):
    tid = tree["id"]
    old, new = day_in(5), day_in(30)
    p = create_person(owner, tid, "Ravi", **birth_on(old))
    eid = birth_event_id(owner, tid, p["id"])
    remind(owner, tid, eid)
    monkeypatch.setattr(notifications, "enqueue", lambda *a, **kw: None)
    notifications.tick(now=fire_at(old) + dt.timedelta(minutes=1))
    with owner_session() as db:
        delivery = db.scalar(select(NotificationDelivery))
        did = str(delivery.id)
        assert delivery.status == DeliveryStatus.PENDING
    assert (
        owner.patch(f"/trees/{tid}/events/{eid}", json={"date": birth_on(new)["birth"]["date"]}).status_code
        == 200
    )
    before = len(all_mail(owner.user["email"]))
    notifications.deliver(did, tid)
    assert len(all_mail(owner.user["email"])) == before
    with owner_session() as db:
        assert db.get(NotificationDelivery, uuid.UUID(did)).status == DeliveryStatus.CANCELLED


@pytest.mark.parametrize("edit_first", [True, False])
def test_date_edit_and_delivery_serialize_on_the_event(owner, tree, monkeypatch, edit_first):
    from app.core.db import get_sessionmaker
    from app.modules.genealogy.schemas import EventUpdate
    from app.modules.genealogy.service import update_event

    tid = tree["id"]
    old, new = day_in(5), day_in(30)
    p = create_person(owner, tid, "Race", **birth_on(old))
    eid = birth_event_id(owner, tid, p["id"])
    remind(owner, tid, eid)
    monkeypatch.setattr(notifications, "enqueue", lambda *a, **kw: None)
    notifications.tick(now=fire_at(old) + dt.timedelta(minutes=1))
    with owner_session() as db:
        did = str(db.scalar(select(NotificationDelivery.id)))
    before = len(all_mail(owner.user["email"]))

    def edit(db):
        return update_event(
            _ctx(db, tid, owner.user["id"]),
            uuid.UUID(eid),
            EventUpdate.model_validate({"date": birth_on(new)["birth"]["date"]}),
        ).id

    if edit_first:
        with get_sessionmaker()() as first:
            edit(first)
            th, out = _run(lambda _: notifications.deliver(did, tid))
            try:
                _wait_until_blocked()
                assert th.is_alive()
                first.commit()
            finally:
                first.rollback()
                th.join(20)
        assert not th.is_alive() and "error" not in out, out
        assert len(all_mail(owner.user["email"])) == before
    else:
        composing, release = threading.Event(), threading.Event()
        compose = notifications._compose

        def pause(*args, **kwargs):
            composing.set()
            assert release.wait(20)
            return compose(*args, **kwargs)

        monkeypatch.setattr(notifications, "_compose", pause)
        delivery_thread, delivery_out = _run(lambda _: notifications.deliver(did, tid))
        edit_thread = None
        try:
            assert composing.wait(15)
            edit_thread, edit_out = _run(edit)
            _wait_until_blocked()
            assert edit_thread.is_alive()
        finally:
            release.set()
            delivery_thread.join(20)
            if edit_thread:
                edit_thread.join(20)
        assert not delivery_thread.is_alive() and "error" not in delivery_out, delivery_out
        assert edit_thread and not edit_thread.is_alive() and "error" not in edit_out, edit_out
        assert len(all_mail(owner.user["email"])) == before + 1
    assert event(owner, tid, p["id"])["date"]["day"] == new.day


def test_reviewed_date_edit_can_be_rebased_and_reschedules(owner, tree, member_factory):
    from tests.test_proposals import propose, set_policy

    tid = tree["id"]
    new = day_in(5)
    p = create_person(owner, tid, "Reviewed", **birth_on(day_in(30)))
    e = event(owner, tid, p["id"])
    rid = remind(owner, tid, e["id"]).json()["id"]
    set_policy(owner, tid, "all")
    contributor = member_factory(["CONTRIBUTOR"])
    prop = propose(
        contributor,
        tid,
        [
            {
                "target_type": "event",
                "op": "update",
                "target_id": e["id"],
                "patch": {"date": birth_on(new)["birth"]["date"], "expected_revision": e["revision"]},
            }
        ],
    ).json()
    assert (
        owner.patch(f"/trees/{tid}/events/{e['id']}", json={"description": "More evidence"}).status_code
        == 200
    )
    assert owner.post(f"/trees/{tid}/proposals/{prop['id']}/approve", json={}).status_code == 409
    rebased = contributor.post(f"/trees/{tid}/proposals/{prop['id']}/rebase")
    assert rebased.status_code == 201, rebased.text
    approved = owner.post(f"/trees/{tid}/proposals/{rebased.json()['id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    with owner_session() as db:
        assert db.get(EventReminder, uuid.UUID(rid)).next_fire_at == fire_at(new)


def test_toggling_date_rearms_only_an_unsent_occurrence(owner, tree, monkeypatch):
    tid = tree["id"]
    old, new = day_in(5), day_in(30)
    p = create_person(owner, tid, "Toggle", **birth_on(old))
    eid = birth_event_id(owner, tid, p["id"])
    remind(owner, tid, eid)
    monkeypatch.setattr(notifications, "enqueue", lambda *a, **kw: None)

    def tick():
        notifications.tick(now=fire_at(old) + dt.timedelta(minutes=1))

    def toggle():
        for date in (new, old):
            r = owner.patch(f"/trees/{tid}/events/{eid}", json={"date": birth_on(date)["birth"]["date"]})
            assert r.status_code == 200, r.text

    tick()
    with owner_session() as db:
        did = str(db.scalar(select(NotificationDelivery.id)))
    # The original fire is already past, but still inside the ordinary scheduler grace window.
    monkeypatch.setattr(notifications, "_now", lambda: fire_at(old) + dt.timedelta(minutes=2))
    toggle()
    tick()
    with owner_session() as db:
        assert db.get(NotificationDelivery, uuid.UUID(did)).status == DeliveryStatus.PENDING
    before = len(all_mail(owner.user["email"]))
    assert notifications.deliver(did, tid) == "sent"
    toggle()
    tick()
    assert notifications.deliver(did, tid) == "skipped"
    assert len(all_mail(owner.user["email"])) == before + 1
    with owner_session() as db:
        assert len(list(db.scalars(select(NotificationDelivery)))) == 1


def test_birth_event_cannot_be_patched_through_another_tree(owner, tree):
    p = create_person(owner, tree["id"], "Scoped", **birth_on(day_in(5)))
    eid = birth_event_id(owner, tree["id"], p["id"])
    other = owner.post("/trees", json={"name": "Other tree"}).json()["id"]
    response = owner.patch(f"/trees/{other}/events/{eid}", json={"date": None})
    assert response.status_code == 404, response.text
    assert event(owner, tree["id"], p["id"])["date"] is not None


def test_birth_year_correction_keeps_a_still_valid_queued_birthday(owner, tree, monkeypatch):
    tid = tree["id"]
    date = day_in(5)
    p = create_person(owner, tid, "Year correction", **birth_on(date))
    eid = birth_event_id(owner, tid, p["id"])
    remind(owner, tid, eid)
    monkeypatch.setattr(notifications, "enqueue", lambda *a, **kw: None)
    notifications.tick(now=fire_at(date) + dt.timedelta(minutes=1))
    monkeypatch.setattr(notifications, "_now", lambda: fire_at(date) + dt.timedelta(minutes=2))
    response = owner.patch(
        f"/trees/{tid}/events/{eid}", json={"date": birth_on(date, year=1951)["birth"]["date"]}
    )
    assert response.status_code == 200, response.text
    with owner_session() as db:
        delivery = db.scalar(select(NotificationDelivery))
        did = str(delivery.id)
        assert delivery.status == DeliveryStatus.PENDING
    before = len(all_mail(owner.user["email"]))
    assert notifications.deliver(did, tid) == "sent"
    assert len(all_mail(owner.user["email"])) == before + 1


@pytest.mark.parametrize("writer", ["create", "update", "preferences"])
@pytest.mark.parametrize("edit_first", [True, False])
def test_schedule_writers_and_date_edits_use_the_same_anchor_lock(owner, tree, writer, edit_first):
    from app.core.db import get_sessionmaker
    from app.modules.genealogy.schemas import EventUpdate
    from app.modules.genealogy.service import update_event
    from app.modules.notifications.schemas import PreferenceIn, ReminderIn, ReminderUpdate

    tid = tree["id"]
    new = day_in(5)
    p = create_person(owner, tid, "Schedule race", **birth_on(day_in(30)))
    eid = birth_event_id(owner, tid, p["id"])
    rid = None if writer == "create" else uuid.UUID(remind(owner, tid, eid).json()["id"])

    def edit(db):
        return update_event(
            _ctx(db, tid, owner.user["id"]),
            uuid.UUID(eid),
            EventUpdate.model_validate({"date": birth_on(new)["birth"]["date"]}),
        ).id

    def schedule_write(db):
        ctx = _ctx(db, tid, owner.user["id"])
        if writer == "create":
            return notifications.create_reminder(ctx, ReminderIn(event_id=uuid.UUID(eid))).id
        if writer == "update":
            return notifications.update_reminder(ctx, rid, ReminderUpdate(note="Updated note")).id
        return notifications.set_preferences(ctx, PreferenceIn(enabled=True))

    with get_sessionmaker()() as first:
        (edit if edit_first else schedule_write)(first)
        th, out = _run(schedule_write if edit_first else edit)
        try:
            _wait_until_blocked()
            assert th.is_alive()
            first.commit()
        finally:
            first.rollback()
            th.join(20)
    assert not th.is_alive() and "error" not in out, out
    with owner_session() as db:
        reminder = db.scalar(select(EventReminder).where(EventReminder.event_id == uuid.UUID(eid)))
        assert reminder.next_fire_at == fire_at(new)


@pytest.mark.parametrize("subscribe_first", [True, False])
def test_preference_change_cannot_miss_a_concurrent_new_subscription(owner, tree, subscribe_first):
    from app.core.db import get_sessionmaker
    from app.modules.notifications.schemas import PreferenceIn, ReminderIn

    tid = tree["id"]
    date = day_in(5)
    p = create_person(owner, tid, "New subscription", **birth_on(date))
    eid = birth_event_id(owner, tid, p["id"])

    def subscribe(db):
        return notifications.create_reminder(
            _ctx(db, tid, owner.user["id"]), ReminderIn(event_id=uuid.UUID(eid))
        ).id

    def preferences(db):
        return notifications.set_preferences(
            _ctx(db, tid, owner.user["id"]), PreferenceIn(enabled=True, send_hour=10)
        )

    with get_sessionmaker()() as first:
        (subscribe if subscribe_first else preferences)(first)
        th, out = _run(preferences if subscribe_first else subscribe)
        try:
            _wait_until_blocked()
            assert th.is_alive()
            first.commit()
        finally:
            first.rollback()
            th.join(20)
    assert not th.is_alive() and "error" not in out, out
    with owner_session() as db:
        reminder = db.scalar(select(EventReminder).where(EventReminder.event_id == uuid.UUID(eid)))
        assert reminder.next_fire_at == fire_at(date, hour=10)


def test_proposal_approval_rechecks_revision_after_waiting_for_an_edit(owner, tree, member_factory):
    from app.core.db import get_sessionmaker
    from app.modules.genealogy.schemas import EventUpdate
    from app.modules.genealogy.service import update_event
    from app.modules.review.service import approve
    from tests.test_proposals import propose, set_policy

    tid = tree["id"]
    p = create_person(owner, tid, "Concurrent proposal", **birth_on(day_in(30)))
    e = event(owner, tid, p["id"])
    set_policy(owner, tid, "all")
    contributor = member_factory(["CONTRIBUTOR"])
    prop = propose(
        contributor,
        tid,
        [
            {
                "target_type": "event",
                "op": "update",
                "target_id": e["id"],
                "patch": {"date": {"precision": "year_only", "year": 1999}},
            }
        ],
    ).json()
    with get_sessionmaker()() as first:
        update_event(
            _ctx(first, tid, owner.user["id"]),
            uuid.UUID(e["id"]),
            EventUpdate.model_validate({"date": {"precision": "year_only", "year": 1980}}),
        )

        def decide(db):
            ctx = _ctx(db, tid, owner.user["id"])
            # A review screen may already have loaded this record before approval takes its lock.
            cached = db.get(Event, uuid.UUID(e["id"]))
            assert cached.revision == e["revision"]
            return approve(ctx, uuid.UUID(prop["id"]), None).status.value

        th, out = _run(decide)
        try:
            _wait_until_blocked()
            first.commit()
        finally:
            first.rollback()
            th.join(20)
    assert not th.is_alive() and "error" not in out, out
    assert out["value"] == "stale"
    assert event(owner, tid, p["id"])["date"]["year"] == 1980
