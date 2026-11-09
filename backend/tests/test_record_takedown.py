"""Takedown of shareable records: reports, suspension, appeals and decisions (ADR-0027 §8.2).

The owner's decisions of 9 Nov 2026: a suspension stays in effect while an appeal is reviewed; an
admin with `record.takedown` upholds or lifts it without seeing the record; where possible a
different admin reviews the appeal, with an explicit fallback when only one can; lifting re-checks
the record as it is now and restores nothing; appeals have a deadline and are escalated, and neither
restores access; the reporter is never named to the owner.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import create_engine, select, text, update

from alembic import command
from app.core.config import get_settings
from app.models import AuditEvent, RecordSuspension
from tests.conftest import _ADMIN_URL, _BASE, owner_session
from tests.doc_fixtures import unique_png, upload
from tests.helpers import create_person
from tests.test_migrations import DB, _cfg

_n = 3000


def _doc(client: Any, t: str, level: str = "TREE_MEMBERS", **form: Any) -> str:
    global _n
    _n += 1
    r = upload(
        client,
        t,
        unique_png(_n, "Takedown photo"),
        mime="image/png",
        title=form.pop("title", "Diwali 2001"),
        privacy_level=level,
        **form,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mid(owner: Any, t: str, client: Any) -> str:
    return next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == client.user["id"])


def _sees(client: Any, t: str, doc: str) -> bool:
    r = client.get(f"/trees/{t}/documents/{doc}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


def _report(client: Any, t: str, doc: str, kind: str = "document", **body: Any) -> Any:
    return client.post(f"/trees/{t}/records/{kind}/{doc}/reports", json={"reason": "abuse", **body})


def _suspend(admin: Any, t: str, report_id: str) -> dict[str, Any]:
    r = admin.post(f"/trees/{t}/record-reports/{report_id}/suspend")
    assert r.status_code == 201, r.text
    return r.json()


def _decide(
    client: Any, t: str, sid: str, decision: str, reason: str = "report_confirmed", **body: Any
) -> Any:
    return client.post(
        f"/trees/{t}/record-suspensions/{sid}/decision",
        json={"decision": decision, "reason": reason, "note": "Reviewed the report", **body},
    )


def _appeal(client: Any, t: str, sid: str) -> Any:
    return client.post(
        f"/trees/{t}/record-suspensions/{sid}/appeal", json={"note": "This is our wedding photo"}
    )


def _inbox(client: Any, t: str) -> list[dict[str, Any]]:
    r = client.get(f"/trees/{t}/inbox")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _kinds(client: Any, t: str) -> list[str]:
    return [i["kind"] for i in _inbox(client, t)]


def _setup(owner: Any, tree: dict[str, Any], member_factory: Any) -> dict[str, Any]:
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author Asha")
    reporter = member_factory(["VIEWER"], name="Reporter Ravi")
    admin_a = member_factory(["FAMILY_ADMIN"], name="Admin One")
    admin_b = member_factory(["FAMILY_ADMIN"], name="Admin Two")
    doc = _doc(author, t)
    return {"t": t, "author": author, "reporter": reporter, "a": admin_a, "b": admin_b, "doc": doc}


# ---------------------------------------------------------------- reports
def test_reporting_needs_sight_of_the_record_and_hides_the_reporter(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    private = _doc(s["author"], t, "ONLY_ME")
    # a record you cannot see does not exist for you; your own record is not reportable
    assert _report(s["reporter"], t, private).status_code == 404
    assert _report(s["reporter"], t, str(uuid.uuid4())).status_code == 404
    assert _report(s["author"], t, doc).status_code == 409
    r = _report(s["reporter"], t, doc, note="Shows my child without asking")
    assert r.status_code == 201, r.text
    ref = r.json()["reference"]
    assert ref.startswith("R-") and len(ref) == 8
    assert _report(s["reporter"], t, doc).status_code == 409  # once while open

    # handlers see the reason and note, never the record nor who reported
    reports = s["a"].get(f"/trees/{t}/record-reports").json()
    assert [(x["reference"], x["resource_type"], x["reason"]) for x in reports] == [
        (ref, "document", "abuse")
    ]
    blob = json.dumps(reports)
    assert "Reporter" not in blob and s["reporter"].user["id"] not in blob and doc not in blob
    assert "Diwali" not in blob
    assert "record_reported" in _kinds(s["a"], t) and "record_reported" in _kinds(s["b"], t)
    # members without record.takedown cannot list reports
    assert s["reporter"].get(f"/trees/{t}/record-reports").status_code == 403
    assert s["author"].get(f"/trees/{t}/record-reports").status_code == 403
    # the author learns nothing about a report until something happens to the record
    assert _kinds(s["author"], t) == []


def test_mistaken_report_is_dismissed_without_touching_the_record(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    rid = _report(s["reporter"], t, doc).json()["id"]
    r = s["a"].post(f"/trees/{t}/record-reports/{rid}/dismiss", json={"reason": "mistaken_report"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed", r.text
    assert _sees(s["reporter"], t, doc) and _sees(s["b"], t, doc)
    assert _kinds(s["author"], t) == []  # the owner is never told of a dismissed report
    assert "report_reviewed" in _kinds(s["reporter"], t)
    # a closed report cannot be suspended afterwards
    assert s["b"].post(f"/trees/{t}/record-reports/{rid}/suspend").status_code == 409


# ---------------------------------------------------------------- suspension
def test_suspension_hides_the_record_from_everyone_but_its_owner(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    grantee = member_factory(["VIEWER"], name="Grantee")
    r = owner.post(
        f"/trees/{t}/grants",
        json={
            "user_id": grantee.user["id"],
            "resource_type": "document",
            "resource_id": doc,
            "permission": "download",
        },
    )
    assert r.status_code == 201, r.text
    url = grantee.post(f"/trees/{t}/documents/{doc}/download-url", params={"variant": "original"}).json()[
        "url"
    ]
    assert grantee.get(url).status_code == 200
    col = s["author"].post(
        f"/trees/{t}/collections", json={"title": "Festivals", "privacy_level": "TREE_MEMBERS"}
    )
    cid = col.json()["id"]
    assert (
        s["author"].post(f"/trees/{t}/collections/{cid}/items", json={"document_id": doc}).status_code == 201
    )

    rid = _report(s["reporter"], t, doc).json()["id"]
    susp = _suspend(s["a"], t, rid)
    assert susp["status"] == "active" and susp["resource_id"] is None  # the handler never needs it

    for who in (s["reporter"], s["a"], s["b"], owner, grantee):
        assert not _sees(who, t, doc)
        listed = who.get(f"/trees/{t}/documents").json()
        assert doc not in json.dumps(listed)
        items = who.get(f"/trees/{t}/collections/{cid}").json()["items"]
        assert all(i["document_id"] != doc for i in items)
        assert doc not in json.dumps(who.get(f"/trees/{t}/search", params={"q": "Diwali"}).json()["hits"])
    assert grantee.get(url).status_code == 403  # a link issued before is refused at once
    # the owner still has it, and is told without being told who reported
    assert _sees(s["author"], t, doc)
    notes = [n for n in _inbox(s["author"], t) if n["kind"] == "record_suspended"]
    assert len(notes) == 1 and "Reporter" not in notes[0]["text"] and susp["reference"] in notes[0]["text"]
    mine = s["author"].get(f"/trees/{t}/record-suspensions").json()
    assert [(m["resource_id"], m["is_owner"]) for m in mine] == [(doc, True)]
    assert "suspended_by_name" not in json.dumps({k: v for k, v in mine[0].items() if v})
    # members who are neither owner nor handler see no suspensions
    assert s["reporter"].get(f"/trees/{t}/record-suspensions").json() == []

    # the audit holds ids and codes only
    with owner_session() as db:
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "record.suspended")).all()
    assert len(ev) == 1 and set(ev[0].details) == {"resource_type", "reason"}


def test_suspended_record_only_narrows(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t = s["t"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    doc = _doc(s["author"], t, "ONLY_ME")
    sharing = f"/trees/{t}/documents/{doc}/sharing"
    reporter = [{"membership_id": _mid(owner, t, s["reporter"]), "can_download": False}]
    r = s["author"].put(
        sharing, json={"privacy_level": "SELECTED_MEMBERS", "members": reporter, "confirm_wider": True}
    )
    assert r.status_code == 200, r.text
    rid = _report(s["reporter"], t, doc).json()["id"]
    _suspend(s["a"], t, rid)
    members = [{"membership_id": _mid(owner, t, viewer), "can_download": True}]
    # widening (or adding anyone) is refused while suspended, so a lift cannot reveal more
    r = s["author"].put(
        sharing, json={"privacy_level": "TREE_MEMBERS", "allow_download": True, "confirm_wider": True}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_suspended"
    r = s["author"].post(
        f"/trees/{t}/grants",
        json={
            "user_id": viewer.user["id"],
            "resource_type": "document",
            "resource_id": doc,
            "permission": "view",
        },
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_suspended"
    r = s["author"].put(
        sharing,
        json={"privacy_level": "SELECTED_MEMBERS", "members": reporter + members, "confirm_wider": True},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_suspended"
    # narrowing is allowed
    r = s["author"].put(sharing, json={"privacy_level": "ONLY_ME", "confirm_wider": True})
    assert r.status_code == 200, r.text


def test_handlers_never_act_on_their_own_record(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t = s["t"]
    own = _doc(s["a"], t, title="Admin's own photo")
    rid = _report(s["reporter"], t, own).json()["id"]
    reports = {x["id"]: x for x in s["a"].get(f"/trees/{t}/record-reports").json()}
    assert reports[rid]["can_act"] is False
    assert s["a"].post(f"/trees/{t}/record-reports/{rid}/suspend").status_code == 403
    sid = _suspend(s["b"], t, rid)["id"]
    assert _sees(s["a"], t, own)  # the owner keeps it
    assert _decide(s["a"], t, sid, "lift").status_code == 403


# ---------------------------------------------------------------- appeals
def test_appeal_is_reviewed_by_a_different_admin_and_can_be_upheld(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    sid = _suspend(s["a"], t, _report(s["reporter"], t, doc).json()["id"])["id"]
    assert _appeal(s["reporter"], t, sid).status_code == 404  # not theirs, not a handler
    assert _appeal(s["a"], t, sid).status_code == 403  # a handler is not the owner
    r = _appeal(s["author"], t, sid)
    assert r.status_code == 200, r.text
    assert r.json()["appeal_status"] == "pending" and r.json()["appeal_due_at"]
    assert _appeal(s["author"], t, sid).status_code == 409  # once
    # the suspension stays in effect while the appeal is reviewed
    assert not _sees(s["reporter"], t, doc)
    # the reviewer is someone other than the admin who suspended it
    assert "suspension_appealed" in _kinds(s["b"], t)
    r = _decide(s["a"], t, sid, "uphold")
    assert r.status_code == 403 and r.json()["error"]["code"] == "different_reviewer_required"
    assert {x["id"]: x["can_decide"] for x in s["a"].get(f"/trees/{t}/record-suspensions").json()}[
        sid
    ] is False
    r = _decide(s["b"], t, sid, "uphold")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "active" and out["appeal_status"] == "upheld" and out["sole_reviewer"] is False
    assert out["decided_by_name"] == "Admin Two" and out["decision_reason"] == "report_confirmed"
    assert not _sees(s["reporter"], t, doc)
    assert "suspension_upheld" in _kinds(s["author"], t)
    # the owner sees the decision and reason, not who decided
    mine = s["author"].get(f"/trees/{t}/record-suspensions/{sid}").json()
    assert mine["decision_note"] == "Reviewed the report" and mine["decided_by_name"] is None
    with owner_session() as db:
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "record.suspension_decided")).one()
    assert ev.actor_user_id == uuid.UUID(s["b"].user["id"])
    assert ev.details == {
        "resource_type": "document",
        "decision": "uphold",
        "reason": "report_confirmed",
        "appealed": True,
        "sole_reviewer": False,
    }


def test_lifting_reevaluates_and_restores_nothing(owner, tree, member_factory, monkeypatch):
    s = _setup(owner, tree, member_factory)
    t = s["t"]
    kept, revoked, leaver = (member_factory(["VIEWER"], name=n) for n in ("Kept", "Revoked", "Leaver"))
    cousin = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    doc = _doc(s["author"], t, "ONLY_ME", link_target_type="person", link_target_id=cousin["id"])
    members = [{"membership_id": _mid(owner, t, m), "can_download": True} for m in (kept, revoked, leaver)]
    r = s["author"].put(
        f"/trees/{t}/documents/{doc}/sharing",
        json={"privacy_level": "SELECTED_MEMBERS", "members": members, "confirm_wider": True},
    )
    assert r.status_code == 200, r.text
    monkeypatch.setattr(get_settings(), "download_url_ttl_seconds", 1)
    url = kept.post(f"/trees/{t}/documents/{doc}/download-url", params={"variant": "original"}).json()["url"]
    sid = _suspend(s["a"], t, _report(kept, t, doc).json()["id"])["id"]

    # during the suspension: a grant is revoked, a member leaves, a ceiling tightens, links expire
    r = s["author"].put(
        f"/trees/{t}/documents/{doc}/sharing",
        json={
            "privacy_level": "SELECTED_MEMBERS",
            "members": members[:1] + members[2:],
            "confirm_wider": True,
        },
    )
    assert r.status_code == 200, r.text
    assert owner.delete(f"/trees/{t}/members/{_mid(owner, t, leaver)}").status_code == 200
    r = owner.put(f"/trees/{t}/people/{cousin['id']}/privacy", json={"privacy_level": "FAMILY_BRANCH"})
    assert r.status_code == 200, r.text
    time.sleep(2.1)

    assert _appeal(s["author"], t, sid).status_code == 200
    r = _decide(s["b"], t, sid, "lift", reason="mistaken_report")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "lifted" and r.json()["appeal_status"] == "lifted"
    assert "suspension_lifted" in _kinds(s["author"], t)

    # the record follows its current settings: the revoked grantee and the leaver stay out
    assert _sees(kept, t, doc)
    assert not _sees(revoked, t, doc)
    got = s["author"].get(f"/trees/{t}/documents/{doc}/sharing").json()
    assert {m["membership_id"] for m in got["members"]} == {members[0]["membership_id"]}
    # the link issued before the suspension stays dead once expired
    assert kept.get(url).status_code in (401, 403, 404, 410)
    # a fresh link works for whoever may download now
    fresh = kept.post(f"/trees/{t}/documents/{doc}/download-url", params={"variant": "original"})
    assert fresh.status_code == 200, fresh.text
    # a lifted suspension cannot be decided again
    assert _decide(s["b"], t, sid, "uphold").status_code == 409


def test_lift_narrows_at_once_when_a_ceiling_tightened(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t = s["t"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    cousin = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    doc = _doc(s["author"], t, link_target_type="person", link_target_id=cousin["id"])
    sid = _suspend(s["a"], t, _report(s["reporter"], t, doc).json()["id"])["id"]
    # the person is made private while the photo is suspended
    owner.put(f"/trees/{t}/people/{cousin['id']}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert _decide(s["b"], t, sid, "lift", reason="mistaken_report").status_code == 200
    assert not _sees(viewer, t, doc)
    assert (
        s["author"].get(f"/trees/{t}/documents/{doc}/sharing").json()["privacy_level"] == "SELECTED_MEMBERS"
    )


def test_single_admin_tree_needs_explicit_sole_reviewer_confirmation(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    reporter = member_factory(["VIEWER"], name="Reporter")
    doc = _doc(author, t)
    sid = _suspend(owner, t, _report(reporter, t, doc).json()["id"])["id"]
    assert _appeal(author, t, sid).status_code == 200
    assert "suspension_appealed" in _kinds(owner, t)  # nobody else could review it
    assert {x["id"]: x["can_decide"] for x in owner.get(f"/trees/{t}/record-suspensions").json()}[sid]
    r = _decide(owner, t, sid, "lift", reason="mistaken_report")
    assert r.status_code == 409 and r.json()["error"]["code"] == "sole_reviewer_confirmation_required"
    assert not _sees(reporter, t, doc)
    r = _decide(owner, t, sid, "lift", reason="mistaken_report", confirm_sole_reviewer=True)
    assert r.status_code == 200 and r.json()["sole_reviewer"] is True, r.text
    assert _sees(reporter, t, doc)
    with owner_session() as db:
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "record.suspension_decided")).one()
    assert ev.details["sole_reviewer"] is True and ev.details["appealed"] is True


def test_overdue_appeal_is_escalated_once_and_restores_nothing(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    sid = _suspend(s["a"], t, _report(s["reporter"], t, doc).json()["id"])["id"]
    assert _appeal(s["author"], t, sid).status_code == 200
    with owner_session() as db:
        db.execute(
            update(RecordSuspension)
            .where(RecordSuspension.id == uuid.UUID(sid))
            .values(appeal_due_at=text("now() - interval '1 day'"))
        )
        db.commit()
    listed = {x["id"]: x for x in s["b"].get(f"/trees/{t}/record-suspensions").json()}
    assert listed[sid]["overdue"] is True and listed[sid]["escalated_at"]
    for who in (s["a"], s["b"], owner):
        assert _kinds(who, t).count("appeal_overdue") == 1
    assert "appeal_overdue" not in _kinds(s["author"], t)
    # still suspended; a second read does not escalate again
    assert not _sees(s["reporter"], t, doc)
    s["a"].get(f"/trees/{t}/record-suspensions")
    assert _kinds(s["b"], t).count("appeal_overdue") == 1
    # lifting without an appeal decision is still a decision by a reviewer
    assert _decide(s["b"], t, sid, "lift", reason="other").status_code == 200


def test_lift_without_appeal_and_suspensions_of_traditions(owner, tree, member_factory):
    s = _setup(owner, tree, member_factory)
    t = s["t"]
    r = s["author"].post(
        f"/trees/{t}/traditions",
        json={"kind": "recipe", "title": "Kheer", "body": "Rice and milk.", "privacy_level": "TREE_MEMBERS"},
    )
    entry = r.json()["id"]
    sid = _suspend(s["a"], t, _report(s["reporter"], t, entry, kind="tradition").json()["id"])["id"]
    assert s["reporter"].get(f"/trees/{t}/traditions/{entry}").status_code == 404
    assert s["author"].get(f"/trees/{t}/traditions/{entry}").status_code == 200
    # uphold needs an appeal; lifting a mistaken suspension does not
    assert _decide(s["b"], t, sid, "uphold").status_code == 409
    r = _decide(s["b"], t, sid, "lift", reason="mistaken_report")
    assert r.status_code == 200 and r.json()["appeal_status"] == "none"
    assert s["reporter"].get(f"/trees/{t}/traditions/{entry}").status_code == 200


def test_a_suspended_record_cannot_change_owner(owner, tree, member_factory):
    """Ownership stays put while a suspension is in effect: no new offer, no accepting an old one."""
    s = _setup(owner, tree, member_factory)
    t, doc = s["t"], s["doc"]
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    offer = f"/trees/{t}/records/document/{doc}/ownership-offer"
    assert s["author"].post(offer, json={"user_id": heir.user["id"]}).status_code == 200
    sid = _suspend(s["a"], t, _report(s["reporter"], t, doc).json()["id"])["id"]
    r = heir.post(f"{offer}/accept")
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_suspended"
    assert s["author"].delete(offer).status_code == 200  # cancelling stays possible
    r = s["author"].post(offer, json={"user_id": heir.user["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_suspended"
    assert _decide(s["b"], t, sid, "lift", reason="mistaken_report").status_code == 200
    assert s["author"].post(offer, json={"user_id": heir.user["id"]}).status_code == 200


def test_migration_downgrade_drops_takedown_and_its_notices():
    """d9b4f2c6a713: two tables, three columns, seven kinds; the downgrade removes them."""
    db = DB + "_takedown"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "d9b4f2c6a713")
        engine = create_engine(url)
        tree_id = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"),
                {"id": tree_id, "s": str(tree_id)},
            )
            conn.execute(
                text(
                    "INSERT INTO user_notification (id, tree_id, user_id, kind) VALUES (:id, :t, :u, 'record_suspended')"
                ),
                {"id": uuid.uuid4(), "t": tree_id, "u": uuid.uuid4()},
            )
        engine.dispose()
        command.downgrade(cfg, "c7e3a1f5b829")
        engine = create_engine(url)
        with engine.begin() as conn:
            tables = set(
                conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars()
            )
            assert not {"record_report", "record_suspension"} & tables
            cols = set(
                conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = 'document'")
                ).scalars()
            )
            assert "suspended_at" not in cols
            assert conn.execute(text("SELECT count(*) FROM user_notification")).scalar() == 0
        engine.dispose()
        command.upgrade(cfg, "d9b4f2c6a713")
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()
