"""Automatic narrowing tells the owner, and a hidden profile narrows its records (ADR-0027 §5).

When a record is made more private because someone linked to it (or its event) became private, its
owner gets an in-app notice: a kind and the record's id, never who or why. A profile hidden by a
"remove me" request through a claim link narrows the records tagging it at once, like any privacy
change; declining the request restores the profile but never widens a record again.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import AuditEvent
from tests.conftest import _ADMIN_URL, _BASE, owner_session
from tests.doc_fixtures import unique_png, upload
from tests.helpers import create_person
from tests.test_migrations import DB, _cfg

_n = 2000


def _doc(client: Any, t: str, person_id: str, title: str = "Holi 1998") -> str:
    global _n
    _n += 1
    r = upload(
        client,
        t,
        unique_png(_n, "Narrowing photo"),
        mime="image/png",
        title=title,
        privacy_level="TREE_MEMBERS",
        link_target_type="person",
        link_target_id=person_id,
    )
    assert r.status_code == 201, r.text
    assert r.json()["privacy_level"] == "TREE_MEMBERS"
    return r.json()["id"]


def _sees(client: Any, t: str, doc_id: str) -> bool:
    r = client.get(f"/trees/{t}/documents/{doc_id}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


def _inbox(client: Any, t: str) -> list[dict[str, Any]]:
    r = client.get(f"/trees/{t}/inbox")
    assert r.status_code == 200, r.text
    return [i for i in r.json()["items"] if i["kind"].endswith("_narrowed")]


def _hide(owner: Any, t: str, person_id: str) -> None:
    r = owner.put(f"/trees/{t}/people/{person_id}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 200, r.text


def test_owner_is_told_when_their_document_is_narrowed(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    viewer = member_factory(["VIEWER"], name="Viewer")
    ravi = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    doc = _doc(author, t, ravi["id"])
    assert _sees(viewer, t, doc)
    _hide(owner, t, ravi["id"])
    assert not _sees(viewer, t, doc)

    notes = _inbox(author, t)
    assert len(notes) == 1
    n = notes[0]
    assert n["kind"] == "document_narrowed" and n["subject_id"] == doc and n["read"] is False
    assert "“Holi 1998”" in n["text"] and "more private" in n["text"]
    # nobody is named: not the person who caused it, nor the person it protects
    assert "Ravi" not in n["text"] and "Owner" not in n["text"]
    # nobody else is told
    assert _inbox(owner, t) == [] and _inbox(viewer, t) == []

    # a second narrowing while the notice is unread does not pile up
    r = author.post(
        f"/trees/{t}/documents/{doc}/links",
        json={"target_type": "person", "target_id": create_person(owner, t, "Kamla", status="living")["id"]},
    )
    assert r.status_code == 201, r.text
    assert len(_inbox(author, t)) == 1


def test_narrowing_your_own_record_is_not_a_notice(owner, tree):
    t = tree["id"]
    aunt = create_person(owner, t, "Kamla", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    other = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    doc = _doc(owner, t, other["id"])
    r = owner.post(
        f"/trees/{t}/documents/{doc}/links", json={"target_type": "person", "target_id": aunt["id"]}
    )
    assert r.status_code == 201, r.text
    assert owner.get(f"/trees/{t}/documents/{doc}/sharing").json()["privacy_level"] == "SELECTED_MEMBERS"
    assert _inbox(owner, t) == []


def test_owner_is_told_when_their_tradition_is_narrowed(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    ravi = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    r = author.post(
        f"/trees/{t}/traditions",
        json={
            "kind": "recipe",
            "title": "Ravi's kheer",
            "body": "Rice, milk, jaggery.",
            "privacy_level": "TREE_MEMBERS",
            "links": [{"target_type": "person", "target_id": ravi["id"]}],
        },
    )
    assert r.status_code == 201, r.text
    entry = r.json()["id"]
    _hide(owner, t, ravi["id"])
    notes = _inbox(author, t)
    assert [(n["kind"], n["subject_id"]) for n in notes] == [("tradition_narrowed", entry)]
    assert "“Ravi's kheer”" in notes[0]["text"]
    # the notice stops quoting the title once the entry is withdrawn
    assert author.delete(f"/trees/{t}/traditions/{entry}").status_code in (200, 204)
    assert "kheer" not in _inbox(author, t)[0]["text"]


def test_remove_me_hides_the_profile_and_narrows_its_records(owner, tree, member_factory, make_client):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    viewer = member_factory(["VIEWER"], name="Viewer")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    meera = create_person(owner, t, "Meera", status="living", privacy_level="TREE_MEMBERS")
    doc = _doc(author, t, meera["id"], title="At the ghat")
    inv = owner.post(f"/trees/{t}/people/{meera['id']}/claim-invites", json={"offered_role": "VIEWER"})
    assert inv.status_code == 201, inv.text
    rel = make_client()
    rel.register(name="Meera Iyer")
    r = rel.post(f"/claim-invites/{inv.json()['token']}/request-removal", json={"confirm_is_me": True})
    assert r.status_code == 201, r.text

    # the photo tagging her is narrowed at once; members outside the new audience lose it
    assert not _sees(viewer, t, doc) and not _sees(admin, t, doc)
    assert author.get(f"/trees/{t}/documents/{doc}/sharing").json()["privacy_level"] == "SELECTED_MEMBERS"
    # the link holder is not a member and gains nothing
    assert rel.get(f"/trees/{t}/documents/{doc}").status_code in (403, 404)
    # the owner is told it was narrowed, never that someone asked to be removed
    notes = _inbox(author, t)
    assert len(notes) == 1 and notes[0]["subject_id"] == doc
    assert all(w not in notes[0]["text"].lower() for w in ("remov", "claim", "meera"))
    # audited like any privacy change, as the system
    with owner_session() as db:
        events = db.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "record.visibility_changed", AuditEvent.target_id == uuid.UUID(doc)
            )
        ).all()
    assert [(e.actor_user_id, e.details["reason"]) for e in events] == [(None, "person_privacy")]
    assert "claim" not in json.dumps([e.details for e in events])

    # declining the request restores the profile but never widens the photo again
    claim = owner.get(f"/trees/{t}/claims").json()[0]
    assert owner.post(f"/trees/{t}/claims/{claim['id']}/reject", json={"note": "not her"}).status_code == 200
    assert owner.get(f"/trees/{t}/people/{meera['id']}").json()["privacy_level"] == "TREE_MEMBERS"
    assert author.get(f"/trees/{t}/documents/{doc}/sharing").json()["privacy_level"] == "SELECTED_MEMBERS"
    assert not _sees(viewer, t, doc)
    # its owner may widen it again now that she is visible
    r = author.put(
        f"/trees/{t}/documents/{doc}/sharing", json={"privacy_level": "TREE_MEMBERS", "confirm_wider": True}
    )
    assert r.status_code == 200, r.text
    assert _sees(viewer, t, doc)


def test_notices_are_the_readers_own(owner, tree, member_factory):
    """Another member cannot read, mark or count someone else's notices."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    other = member_factory(["FAMILY_ADMIN"], name="Other")
    ravi = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    _doc(author, t, ravi["id"])
    _hide(owner, t, ravi["id"])
    note = _inbox(author, t)[0]
    assert other.get(f"/trees/{t}/inbox").json()["unread"] == 0
    other.post(f"/trees/{t}/inbox/read", json={"ids": [note["id"]]})
    assert _inbox(author, t)[0]["read"] is False


def test_migration_adds_the_kinds_and_downgrade_removes_their_notices():
    """c7e3a1f5b829: two notification kinds; the downgrade deletes those notices first."""
    db = DB + "_narrowing"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "c7e3a1f5b829")
        engine = create_engine(url)
        tree_id, user_id = uuid.uuid4(), uuid.uuid4()
        insert = text(
            "INSERT INTO user_notification (id, tree_id, user_id, kind, subject_id) VALUES (:id, :t, :u, :k, :s)"
        )
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"),
                {"id": tree_id, "s": str(tree_id)},
            )
            for kind in ("document_narrowed", "tradition_narrowed", "offer_accepted"):
                conn.execute(
                    insert, {"id": uuid.uuid4(), "t": tree_id, "u": user_id, "k": kind, "s": uuid.uuid4()}
                )
        engine.dispose()
        command.downgrade(cfg, "b5c1e7a93d42")
        engine = create_engine(url)
        with engine.begin() as conn:
            kinds = conn.execute(text("SELECT kind FROM user_notification")).scalars().all()
            assert kinds == ["offer_accepted"]
            with pytest.raises(IntegrityError, match="ck_user_notification"), conn.begin_nested():
                conn.execute(
                    insert,
                    {"id": uuid.uuid4(), "t": tree_id, "u": user_id, "k": "document_narrowed", "s": None},
                )
        engine.dispose()
        command.upgrade(cfg, "c7e3a1f5b829")
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()
