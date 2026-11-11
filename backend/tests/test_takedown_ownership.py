"""An ownership offer that exists when a record is suspended (ADR-0027 §8.2 detail 9).

The owner's decision of 9 Nov 2026 (option 1): a suspension cancels any pending offer in the same
transaction; no offer and no acceptance succeeds while the record is suspended; after a lift the owner
must make a fresh offer. Suspension and acceptance lock the same record row, so they are serialised:
if acceptance commits first, the suspension and its notice use the new owner; if the suspension
commits first, acceptance fails and ownership does not move.

The concurrency tests use two real database sessions (the application role, row-level security on)
and hold one transaction open while the other runs, checking in ``pg_stat_activity`` that the second
is actually waiting on a lock before the first commits.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from sqlalchemy import select, text

from app.authz.context import load_tree_context
from app.core.db import get_sessionmaker
from app.core.errors import NotFound
from app.models import AuditEvent, Document, User, UserNotification
from app.models.enums import GrantResource, NotificationKind
from app.modules.ownership import service as ownership
from app.modules.takedown import service as takedown
from tests.conftest import owner_session
from tests.test_record_takedown import _decide, _doc, _mid, _report, _setup, _suspend


def _offer_url(t: str, doc: str) -> str:
    return f"/trees/{t}/records/document/{doc}/ownership-offer"


def _offered(owner_client: Any, t: str, doc: str, to: Any) -> None:
    r = owner_client.post(_offer_url(t, doc), json={"user_id": to.user["id"]})
    assert r.status_code == 200, r.text


def _doc_row(doc: str) -> Document:
    with owner_session() as db:
        d = db.get(Document, uuid.UUID(doc))
        assert d is not None
        return d


def _events(action: str, target: str) -> list[AuditEvent]:
    with owner_session() as db:
        return list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == action, AuditEvent.target_id == uuid.UUID(target)
                )
            )
        )


# ---------------------------------------------------------------- the decision, end to end
def test_suspension_cancels_the_offer_and_a_fresh_one_is_needed_after_a_lift(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    other = member_factory(["CONTRIBUTOR"], name="Other")
    _offered(s["author"], t, doc, heir)
    assert [o["resource_id"] for o in heir.get(f"/trees/{t}/ownership-offers").json()] == [doc]
    sid = _suspend(s["a"], t, _report(s["reporter"], t, doc).json()["id"])["id"]

    # cancelled at once, in the suspension's transaction
    assert _doc_row(doc).pending_owner_membership_id is None
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []  # offer list redacted
    # nothing succeeds while suspended
    assert heir.post(f"{_offer_url(t, doc)}/accept").status_code == 404
    r = s["author"].post(_offer_url(t, doc), json={"user_id": heir.user["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_suspended"  # the owner knows
    assert _doc_row(doc).owner_membership_id == uuid.UUID(_mid(owner, t, s["author"]))

    assert _decide(s["b"], t, sid, "lift", reason="mistaken_report").status_code == 200
    # the old offer does not come back
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []
    assert heir.post(f"{_offer_url(t, doc)}/accept").status_code == 404
    # a fresh owner-initiated offer works
    _offered(s["author"], t, doc, other)
    r = other.post(f"{_offer_url(t, doc)}/accept")
    assert r.status_code == 200 and r.json()["owner_membership_id"] == _mid(owner, t, other)


def test_the_offered_member_cannot_tell_a_suspension_from_any_other_missing_offer(
    owner, tree, member_factory
):
    """Accepting or declining after the suspension answers exactly like a record never offered."""
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    plain = _doc(s["author"], t, title="Never offered")
    _offered(s["author"], t, doc, heir)
    _suspend(s["a"], t, _report(s["reporter"], t, doc).json()["id"])

    def answer(method: str, rid: str) -> tuple[int, dict[str, Any]]:
        url = _offer_url(t, rid) + ("/accept" if method == "post" else "")
        r = getattr(heir, method)(url)
        return r.status_code, r.json()

    for method in ("post", "delete"):
        got, baseline = answer(method, doc), answer(method, plain)
        assert got == baseline and got[0] == 404, (method, got, baseline)
    # and like a record that does not exist at all
    assert answer("post", doc) == answer("post", str(uuid.uuid4()))
    # the record itself is just "not found" too
    r1, r2 = heir.get(f"/trees/{t}/documents/{doc}"), heir.get(f"/trees/{t}/documents/{uuid.uuid4()}")
    assert (r1.status_code, r1.json()) == (r2.status_code, r2.json())


def test_cancellation_audit_and_notices_reveal_nothing_to_unauthorised_members(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    _offered(s["author"], t, doc, heir)
    _report_resp = _report(s["reporter"], t, doc, reason="intimate", note="see the second photo")
    _suspend(s["a"], t, _report_resp.json()["id"])

    # stored: one system event, no actor, no reason
    ev = _events("record.ownership_offer_cancelled", doc)
    assert [(e.actor_user_id, e.details, e.target_type) for e in ev] == [(None, {"by": "system"}, "document")]

    # the audit API: members without audit.read get nothing; handlers see the cancellation only as an
    # opaque "private record" entry (they cannot see the suspended record), never its id or title
    for who in (heir, s["reporter"], s["author"]):
        assert who.get(f"/trees/{t}/audit").status_code == 403
    for who in (s["a"], owner):
        items = who.get(f"/trees/{t}/audit", params={"limit": 200}).json()["items"]
        blob = json.dumps(items)
        assert doc not in blob and "Diwali" not in blob and "second photo" not in blob
        cancelled = [i for i in items if i["action"] == "record.ownership_offer_cancelled"]
        assert len(cancelled) == 1 and cancelled[0]["target_type"] == "private_record"
        assert cancelled[0]["details"] == {} and cancelled[0]["target_id"] is None

    # notices: the offered member hears nothing; the owner's names no title and no reason; the
    # reporter's says only that the report was reviewed
    assert heir.get(f"/trees/{t}/inbox").json()["items"] == []
    owner_notes = s["author"].get(f"/trees/{t}/inbox").json()["items"]
    assert [n["kind"] for n in owner_notes] == ["record_suspended"]
    text_ = owner_notes[0]["text"]
    assert "Diwali" not in text_ and "intimate" not in text_ and "Reporter" not in text_
    assert "offer of its ownership was cancelled" in text_
    rep = [n["text"] for n in s["reporter"].get(f"/trees/{t}/inbox").json()["items"]]
    assert (
        len(rep) == 1 and "reviewed" in rep[0] and "Diwali" not in rep[0] and "suspend" not in rep[0].lower()
    )
    # no notice anywhere carries the record's title or the reason
    with owner_session() as db:
        kinds = {n.kind for n in db.scalars(select(UserNotification))}
    assert NotificationKind.RECORD_SUSPENDED in kinds
    for who in (heir, s["reporter"], s["a"], s["b"], owner):
        blob = json.dumps(who.get(f"/trees/{t}/inbox").json())
        assert "Diwali" not in blob and "intimate" not in blob and doc not in blob, who


def test_member_removal_and_lift(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    # (a) the offered member leaves before the suspension: the offer lapses; nothing to cancel
    _offered(s["author"], t, doc, heir)
    assert owner.delete(f"/trees/{t}/members/{_mid(owner, t, heir)}").status_code == 200
    assert _doc_row(doc).pending_owner_membership_id is None
    sid = _suspend(s["a"], t, _report(s["reporter"], t, doc).json()["id"])["id"]
    assert _events("record.ownership_offer_cancelled", doc) == []
    # (b) the owner leaves during the suspension: the record is orphaned; lifting tells nobody and
    # nobody can offer or claim it, the former owner included
    author_mid = _mid(owner, t, s["author"])
    assert owner.delete(f"/trees/{t}/members/{author_mid}").status_code == 200
    assert _decide(s["b"], t, sid, "lift", reason="mistaken_report").status_code == 200
    with owner_session() as db:
        lifted = [
            n
            for n in db.scalars(select(UserNotification).where(UserNotification.subject_id == uuid.UUID(sid)))
            if n.kind == NotificationKind.SUSPENSION_LIFTED
        ]
    assert lifted == []
    assert _doc_row(doc).owner_membership_id is None
    for who in (s["b"], s["reporter"]):
        assert who.post(f"{_offer_url(t, doc)}/accept").status_code == 404
        assert who.post(_offer_url(t, doc), json={"user_id": who.user["id"]}).status_code == 404


# ---------------------------------------------------------------- concurrency, on real transactions
def _ctx(db: Any, tree_id: str, user_id: str) -> Any:
    user = db.get(User, uuid.UUID(user_id))
    return load_tree_context(db, uuid.UUID(tree_id), user)


def _wait_until_blocked(timeout: float = 15.0) -> None:
    """Until some session of this test database waits on a row lock."""
    deadline = time.monotonic() + timeout
    with owner_session() as db:
        while time.monotonic() < deadline:
            n = db.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            ).scalar()
            if n:
                return
            db.rollback()
            time.sleep(0.05)
    raise AssertionError("the second transaction never waited on the record lock")


def _run(fn: Any) -> tuple[threading.Thread, dict[str, Any]]:
    out: dict[str, Any] = {}

    def body() -> None:
        db = get_sessionmaker()()
        try:
            out["value"] = fn(db)
            db.commit()
        except Exception as exc:
            db.rollback()
            out["error"] = exc
        finally:
            db.close()

    th = threading.Thread(target=body)
    th.start()
    return th, out


def _prepare(owner: Any, tree: dict[str, Any], member_factory: Any) -> dict[str, Any]:
    s = _setup(owner, tree, member_factory)
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    _offered(s["author"], s["t"], s["doc"], heir)
    s["heir"] = heir
    s["report"] = _report(s["reporter"], s["t"], s["doc"]).json()["id"]
    return s


def _suspended_notice_users(doc: str) -> list[uuid.UUID]:
    with owner_session() as db:
        sus = db.scalars(
            text("SELECT id FROM record_suspension WHERE resource_id = :r").bindparams(r=uuid.UUID(doc))
        ).all()
        return [
            n.user_id
            for n in db.scalars(select(UserNotification).where(UserNotification.subject_id.in_(sus)))
            if n.kind == NotificationKind.RECORD_SUSPENDED
        ]


def test_acceptance_first_then_suspension_uses_the_new_owner(owner, tree, member_factory):
    s = _prepare(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    first = get_sessionmaker()()
    try:
        ownership.accept(_ctx(first, t, s["heir"].user["id"]), GrantResource.DOCUMENT, uuid.UUID(doc))
        # the acceptance holds the record lock and has not committed; the suspension starts now
        th, out = _run(lambda db: takedown.suspend(_ctx(db, t, s["a"].user["id"]), uuid.UUID(s["report"])).id)
        _wait_until_blocked()
        assert th.is_alive()  # really waiting for the acceptance
        first.commit()
    finally:
        first.close()
    th.join(20)
    assert "error" not in out, out.get("error")
    row = _doc_row(doc)
    assert row.owner_membership_id == uuid.UUID(_mid(owner, t, s["heir"]))  # the transfer stands
    assert row.suspended_at is not None and row.pending_owner_membership_id is None
    # the suspension saw the committed transfer: the notice went to the new owner, not the old one
    assert _suspended_notice_users(doc) == [uuid.UUID(s["heir"].user["id"])]
    assert _events("record.ownership_offer_cancelled", doc) == []  # nothing left to cancel
    # and the new owner, not the old one, keeps sight of the record and may appeal
    assert s["heir"].get(f"/trees/{t}/documents/{doc}").status_code == 200
    assert s["author"].get(f"/trees/{t}/documents/{doc}").status_code == 404


def test_suspension_first_then_acceptance_fails_without_transfer(owner, tree, member_factory):
    s = _prepare(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    first = get_sessionmaker()()
    try:
        takedown.suspend(_ctx(first, t, s["a"].user["id"]), uuid.UUID(s["report"]))
        th, out = _run(
            lambda db: ownership.accept(
                _ctx(db, t, s["heir"].user["id"]), GrantResource.DOCUMENT, uuid.UUID(doc)
            )
        )
        _wait_until_blocked()
        assert th.is_alive()  # really waiting for the suspension
        first.commit()
    finally:
        first.close()
    th.join(20)
    assert isinstance(out.get("error"), NotFound), out  # same "Record not found" as any missing offer
    row = _doc_row(doc)
    assert row.owner_membership_id == uuid.UUID(_mid(owner, t, s["author"]))  # ownership did not move
    assert row.pending_owner_membership_id is None and row.suspended_at is not None
    assert _suspended_notice_users(doc) == [uuid.UUID(s["author"].user["id"])]
    assert [e.details for e in _events("record.ownership_offer_cancelled", doc)] == [{"by": "system"}]
    assert _events("record.ownership_transferred", doc) == []


def test_no_new_offer_races_past_a_suspension(owner, tree, member_factory):
    """A new offer started while a suspension holds the lock waits, then is refused."""
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    report = _report(s["reporter"], t, doc).json()["id"]
    first = get_sessionmaker()()
    try:
        takedown.suspend(_ctx(first, t, s["a"].user["id"]), uuid.UUID(report))
        th, out = _run(
            lambda db: ownership.offer(
                _ctx(db, t, s["author"].user["id"]),
                GrantResource.DOCUMENT,
                uuid.UUID(doc),
                uuid.UUID(heir.user["id"]),
            )
        )
        _wait_until_blocked()
        first.commit()
    finally:
        first.close()
    th.join(20)
    err = out.get("error")
    assert err is not None and getattr(err, "code", None) == "record_suspended", out
    assert _doc_row(doc).pending_owner_membership_id is None
