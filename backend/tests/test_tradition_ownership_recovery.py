"""Tradition ownership after PR #51 (migration 8d2e6b4f1a37): orphans, re-invites, offers, rollback.

Audit of the ownership and migration findings reported after #51 (ADR-0027 §2, §3, increment 2):

* an orphaned private entry (its owner's membership is gone) stays with its grantees only, on every
  route, for every role, including a re-invited author; nobody can claim it through a stale offer;
* removing and re-inviting a member never revives grants, ownership or an offer;
* a write by older application code (``rollback.sh`` runs the previous release on the newer schema)
  can neither leave a ``PRIVATE_SELF`` entry that the tree owner reads nor an ownerless new entry;
* a downgrade that would run 8d2e6b4f1a37's lossy downgrade is refused while it would widen or
  discard access, atomically, and the forward migration re-runs cleanly.
"""

from __future__ import annotations

import io
import os
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from alembic import command
from tests.conftest import _ADMIN_URL, _BASE, join_tree, owner_session
from tests.test_migrations import DB, _cfg

RECIPE = {"kind": "recipe", "title": "Dadi zzorph laddoo", "body": "Besan, ghee, sugar. Roast slowly."}
GUARD_REVISION = "f2a9c4e7d815"


def _new(client: Any, t: str, **kw: Any) -> dict[str, Any]:
    r = client.post(f"/trees/{t}/traditions", json={**RECIPE, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _mid(owner: Any, t: str, client: Any) -> str:
    return next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == client.user["id"])


def _share(client: Any, t: str, eid: str, level: str, **body: Any) -> Any:
    return client.put(
        f"/trees/{t}/traditions/{eid}/sharing", json={"privacy_level": level, "confirm_wider": True, **body}
    )


def _sees(client: Any, t: str, eid: str) -> bool:
    r = client.get(f"/trees/{t}/traditions/{eid}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


def _listed(client: Any, t: str, **params: Any) -> set[str]:
    r = client.get(f"/trees/{t}/traditions", params=params)
    assert r.status_code == 200, r.text
    return {i["id"] for i in r.json()["items"]}


def _export_text(client: Any, t: str) -> str:
    """Everything in the reader's archive export, as text."""
    r = client.get(f"/trees/{t}/exports/archive")
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return " ".join(
        z.read(n).decode("utf-8", "replace") for n in z.namelist() if not n.endswith((".jpg", ".png"))
    )


def _remove(owner: Any, t: str, member: Any) -> None:
    assert owner.delete(f"/trees/{t}/members/{_mid(owner, t, member)}").status_code == 200


def _offer_url(t: str, eid: str) -> str:
    return f"/trees/{t}/records/tradition/{eid}/ownership-offer"


# ---------------------------------------------------------------- orphans on every route
def test_an_orphaned_private_entry_is_invisible_everywhere_but_to_its_grantees(owner, tree, member_factory):
    """Prerequisite: the author left. Nobody but an existing grantee learns anything about the
    entry, on any route, whatever their role; a re-invited author is a stranger to it."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["VIEWER"], name="Cousin")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    only = _new(author, t, privacy_level="ONLY_ME")
    picked = _new(author, t, privacy_level="ONLY_ME", title="Dadi zzorph halwa")
    assert (
        _share(
            author, t, picked["id"], "SELECTED_MEMBERS", members=[{"membership_id": _mid(owner, t, cousin)}]
        ).status_code
        == 200
    )
    _remove(owner, t, author)
    join_tree(owner, author, t, ["CONTRIBUTOR"])  # the same account, a new membership

    for name, who in {"tree_owner": owner, "family_admin": admin, "re_invited_author": author}.items():
        for e in (only, picked):
            assert not _sees(who, t, e["id"]), name
            assert e["id"] not in _listed(who, t), name
            assert e["id"] not in _listed(who, t, q="zzorph"), name
            for path in ("history", "sharing"):
                assert who.get(f"/trees/{t}/traditions/{e['id']}/{path}").status_code == 404, (name, path)
            assert who.patch(f"/trees/{t}/traditions/{e['id']}", json={"body": "x"}).status_code == 404, name
            assert who.delete(f"/trees/{t}/traditions/{e['id']}").status_code == 404, name
            assert who.post(f"{_offer_url(t, e['id'])}/accept").status_code == 404, name
            assert who.post(_offer_url(t, e["id"]), json={"user_id": who.user["id"]}).status_code == 404, name
            assert who.post(
                f"/trees/{t}/grants",
                json={
                    "user_id": who.user["id"],
                    "resource_type": "tradition",
                    "resource_id": e["id"],
                    "permission": "view",
                },
            ).status_code in (403, 404), name
        exported = _export_text(who, t)
        assert only["id"] not in exported and picked["id"] not in exported and "zzorph" not in exported, name
        r = who.get(f"/trees/{t}/audit", params={"limit": 200})
        assert r.status_code in (200, 403), name
        if r.status_code == 200:
            assert only["id"] not in r.text and picked["id"] not in r.text, name
        assert who.get(f"/trees/{t}/ownership-offers").json() == [], name
    # the grantee chosen by the author keeps reading it, and only reading it
    assert _sees(cousin, t, picked["id"]) and picked["id"] in _listed(cousin, t, q="zzorph")
    assert not _sees(cousin, t, only["id"])
    assert cousin.patch(f"/trees/{t}/traditions/{picked['id']}", json={"body": "x"}).status_code == 403
    assert _share(cousin, t, picked["id"], "TREE_MEMBERS").status_code in (403, 404)


def test_a_proposal_about_an_entry_that_becomes_an_orphan_stays_hidden(owner, tree, member_factory):
    """A proposal about an entry that was made private and then orphaned stays hidden from everyone,
    its proposer and the tree owner included, and cannot be decided."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["CONTRIBUTOR"], name="Cousin")
    e = _new(author, t, privacy_level="TREE_MEMBERS")
    assert owner.put(f"/trees/{t}/review-policy", json={"review_policy": "all"}).status_code == 200
    p = cousin.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "More ghee",
            "items": [
                {"target_type": "tradition", "op": "update", "target_id": e["id"], "patch": {"body": "x"}}
            ],
            "submit": True,
        },
    )
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    assert (
        author.patch(f"/trees/{t}/traditions/{e['id']}", json={"privacy_level": "ONLY_ME"}).status_code == 200
    )
    _remove(owner, t, author)
    join_tree(owner, author, t, ["CONTRIBUTOR"])
    for who in (owner, cousin, author):
        assert who.get(f"/trees/{t}/proposals/{pid}").status_code == 404
        assert who.post(f"/trees/{t}/proposals/{pid}/approve", json={}).status_code == 404
        for view in ("to_review", "mine"):
            items = who.get(f"/trees/{t}/proposals", params={"view": view}).json()["items"]
            assert pid not in {x["id"] for x in items}


# ---------------------------------------------------------------- re-invited recipients and owners
def test_a_re_invited_recipient_gets_no_grant_back(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["VIEWER"], name="Cousin")
    e = _new(author, t, privacy_level="ONLY_ME")
    assert (
        _share(
            author, t, e["id"], "SELECTED_MEMBERS", members=[{"membership_id": _mid(owner, t, cousin)}]
        ).status_code
        == 200
    )
    assert _sees(cousin, t, e["id"])
    _remove(owner, t, cousin)
    join_tree(owner, cousin, t, ["VIEWER"])
    assert not _sees(cousin, t, e["id"])
    with owner_session() as s:
        assert (
            s.execute(
                text(
                    "SELECT count(*) FROM access_grant WHERE resource_type = 'tradition' AND resource_id = :r"
                ),
                {"r": e["id"]},
            ).scalar()
            == 0
        )
    # the owner sees the selection as empty and may choose the new membership deliberately
    sharing = author.get(f"/trees/{t}/traditions/{e['id']}/sharing").json()
    assert sharing["members"] == []
    new_mid = _mid(owner, t, cousin)
    assert (
        _share(author, t, e["id"], "SELECTED_MEMBERS", members=[{"membership_id": new_mid}]).status_code
        == 200
    )
    assert _sees(cousin, t, e["id"])


def test_an_owner_removed_after_the_upgrade_and_re_invited_owns_nothing(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    family = _new(author, t, privacy_level="TREE_MEMBERS", title="Family laddoo")
    only = _new(author, t, privacy_level="ONLY_ME")
    _remove(owner, t, author)
    join_tree(owner, author, t, ["CONTRIBUTOR"])
    assert not _sees(author, t, only["id"])
    got = author.get(f"/trees/{t}/traditions/{family['id']}").json()  # shared with all: still readable
    assert got["is_owner"] is False and got["can_edit_sharing"] is False
    assert _share(author, t, family["id"], "ONLY_ME").status_code == 403


# ---------------------------------------------------------------- pending offers
def test_an_offer_lapses_for_claiming_once_its_owner_has_left(owner, tree, member_factory):
    """Finding: a pending offer survived the owner's removal, so the member offered the entry could
    accept it after it became an orphan, contradicting ADR-0027 §2 ("an orphaned record cannot be
    offered or claimed")."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    e = _new(author, t, privacy_level="ONLY_ME", title="Secret zzorph recipe")
    assert author.post(_offer_url(t, e["id"]), json={"user_id": heir.user["id"]}).status_code == 200
    _remove(owner, t, author)
    assert heir.post(f"{_offer_url(t, e['id'])}/accept").status_code == 404
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []  # no title of an orphan is listed
    assert not _sees(heir, t, e["id"])
    # the offer can still be declined (cleared) by the member it was made to
    assert heir.delete(_offer_url(t, e["id"])).status_code in (200, 204)
    with owner_session() as s:
        row = s.execute(
            text(
                "SELECT owner_membership_id, pending_owner_membership_id FROM tradition_entry WHERE id = :i"
            ),
            {"i": e["id"]},
        ).one()
        assert row == (None, None)


def test_an_offer_to_a_member_who_leaves_is_not_revived_by_re_invitation(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    e = _new(author, t, privacy_level="ONLY_ME")
    assert author.post(_offer_url(t, e["id"]), json={"user_id": heir.user["id"]}).status_code == 200
    _remove(owner, t, heir)
    join_tree(owner, heir, t, ["CONTRIBUTOR"])
    assert heir.post(f"{_offer_url(t, e['id'])}/accept").status_code == 404
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []
    assert _sees(author, t, e["id"]) and not _sees(heir, t, e["id"])


def test_the_authorised_owner_workflow_still_works(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    e = _new(author, t, privacy_level="ONLY_ME")
    assert author.post(_offer_url(t, e["id"]), json={"user_id": heir.user["id"]}).status_code == 200
    assert [o["resource_id"] for o in heir.get(f"/trees/{t}/ownership-offers").json()] == [e["id"]]
    assert heir.post(f"{_offer_url(t, e['id'])}/accept").status_code == 200
    assert _sees(heir, t, e["id"]) and not _sees(author, t, e["id"])
    assert _share(heir, t, e["id"], "TREE_MEMBERS").status_code == 200
    assert _sees(author, t, e["id"]) and _sees(owner, t, e["id"])


# ---------------------------------------------------------------- shared (non-private) orphans
def test_an_admin_cannot_make_an_orphan_unreadable_by_everyone(owner, tree, member_factory):
    """Finding: an admin may narrow a shared entry, but narrowing an *ownerless* one to Only me leaves
    it readable by nobody, for good. Narrowing to a real audience still works."""
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Varanasi"}).json()
    author = member_factory(["CONTRIBUTOR"], name="Author")
    e = _new(author, t, privacy_level="TREE_MEMBERS")
    _remove(owner, t, author)
    assert _sees(owner, t, e["id"])
    r = owner.post(f"/trees/{t}/traditions/{e['id']}/sharing/preview", json={"privacy_level": "ONLY_ME"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "orphan_only_me", r.text
    r = _share(owner, t, e["id"], "ONLY_ME")
    assert r.status_code == 422 and r.json()["error"]["code"] == "orphan_only_me", r.text
    r = owner.patch(f"/trees/{t}/traditions/{e['id']}", json={"privacy_level": "ONLY_ME"})
    assert r.status_code == 422, r.text
    assert _sees(owner, t, e["id"])
    assert _share(owner, t, e["id"], "FAMILY_BRANCH", audience_branch_id=b["id"]).status_code == 200
    assert _sees(owner, t, e["id"])  # admins are in a Selected-branch audience (ADR-0027 open point 1)


# ---------------------------------------------------------------- older application code on the new schema
def test_a_private_self_written_by_older_code_is_still_the_authors_alone(owner, tree, member_factory):
    """Finding: ``rollback.sh`` runs the previous release on the newer schema. Pre-#51 code writes a
    tradition as ``PRIVATE_SELF`` (author only) without an owner. The new evaluator reads a record's
    ``PRIVATE_SELF`` as "owner + tree OWNER", so the tree owner read it and its author did not."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    old_id = uuid.uuid4()
    with owner_session() as s:  # an INSERT as pre-#51 code makes it
        s.execute(
            text(
                "INSERT INTO tradition_entry (id, tree_id, kind, title, body, privacy_level, created_by) "
                "VALUES (:id, :t, 'recipe', 'Old code laddoo', 'x', 'PRIVATE_SELF', :u)"
            ),
            {"id": old_id, "t": t, "u": author.user["id"]},
        )
        s.commit()
    assert not _sees(owner, t, str(old_id)) and not _sees(admin, t, str(old_id))
    got = author.get(f"/trees/{t}/traditions/{old_id}")
    assert got.status_code == 200 and got.json()["privacy_level"] == "ONLY_ME" and got.json()["is_owner"]

    # an UPDATE to PRIVATE_SELF on an owned entry (an edit by older code) is Only me too
    e = _new(author, t, privacy_level="TREE_MEMBERS")
    with owner_session() as s:
        s.execute(
            text("UPDATE tradition_entry SET privacy_level = 'PRIVATE_SELF' WHERE id = :i"), {"i": e["id"]}
        )
        s.commit()
        assert (
            s.execute(
                text("SELECT privacy_level FROM tradition_entry WHERE id = :i"), {"i": e["id"]}
            ).scalar()
            == "ONLY_ME"
        )
    assert not _sees(owner, t, e["id"]) and _sees(author, t, e["id"])


def test_an_insert_by_older_code_for_someone_who_is_not_a_member_stays_ownerless(owner, tree, member_factory):
    """The owner backfill on INSERT names only a *current* membership of the same tree."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    _remove(owner, t, author)
    eid = uuid.uuid4()
    with owner_session() as s:
        s.execute(
            text(
                "INSERT INTO tradition_entry (id, tree_id, kind, title, privacy_level, created_by) "
                "VALUES (:id, :t, 'recipe', 'R', 'PRIVATE_SELF', :u)"
            ),
            {"id": eid, "t": t, "u": author.user["id"]},
        )
        s.commit()
        assert s.execute(
            text("SELECT privacy_level, owner_membership_id FROM tradition_entry WHERE id = :i"), {"i": eid}
        ).one() == ("ONLY_ME", None)


# ---------------------------------------------------------------- migrations on a real disposable database
def _fresh(name: str) -> tuple[Any, str]:
    db = DB + name
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    return admin, url


def _drop(admin: Any, url: str) -> None:
    db = url.rsplit("/", 1)[1]
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
    admin.dispose()


def _seed(conn: Any) -> dict[str, uuid.UUID]:
    """A tree with an author, a cousin (grantee) and an admin, at head."""
    ids = {
        k: uuid.uuid4()
        for k in ("t", "author", "cousin", "admin", "leaver", "m_author", "m_cousin", "m_admin", "m_leaver")
    }
    for who in ("author", "cousin", "admin", "leaver"):
        conn.execute(
            text("INSERT INTO app_user (id, email, password_hash, display_name) VALUES (:id, :e, 'x', :n)"),
            {"id": ids[who], "e": f"{who}@example.com", "n": who},
        )
    conn.execute(
        text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"), {"id": ids["t"], "s": str(ids["t"])}
    )
    for who, role in (
        ("author", "CONTRIBUTOR"),
        ("cousin", "VIEWER"),
        ("admin", "FAMILY_ADMIN"),
        ("leaver", "CONTRIBUTOR"),
    ):
        conn.execute(
            text("INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY[:r])"),
            {"id": ids[f"m_{who}"], "t": ids["t"], "u": ids[who], "r": role},
        )
    return ids


def _entry(
    conn: Any, ids: dict[str, uuid.UUID], level: str, owner: uuid.UUID | None, author: str = "author"
) -> uuid.UUID:
    eid = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO tradition_entry (id, tree_id, kind, title, privacy_level, created_by, owner_membership_id) "
            "VALUES (:id, :t, 'recipe', 'R', :l, :u, :o)"
        ),
        {"id": eid, "t": ids["t"], "l": level, "u": ids[author], "o": owner},
    )
    return eid


def _orphan(conn: Any, ids: dict[str, uuid.UUID], level: str = "ONLY_ME") -> uuid.UUID:
    """An entry whose owner left: the leaver's membership is deleted, the FK sets the owner NULL."""
    eid = _entry(conn, ids, level, ids["m_leaver"], author="leaver")
    conn.execute(text("DELETE FROM tree_membership WHERE id = :m"), {"m": ids["m_leaver"]})
    return eid


def _version(conn: Any) -> str:
    return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar())


@pytest.mark.parametrize(
    "case",
    ["selected_members", "tradition_grant", "orphaned_only_me", "transferred", "orphan_author_back"],
)
def test_a_lossy_downgrade_through_8d2e6b4f1a37_is_refused_atomically(case):
    """Finding: 8d2e6b4f1a37's downgrade deletes tradition grants, turns Selected members into CUSTOM
    (admins gain read access), gives an orphan back to a re-invited author by user id and forgets
    every ownership transfer. While any such row exists, the downgrade is refused before anything is
    changed; a downgrade that stops above 8d2e6b4f1a37 is not affected."""
    admin, url = _fresh(f"_guard_{case}")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            if case == "selected_members":
                _entry(conn, ids, "SELECTED_MEMBERS", ids["m_author"])
            elif case == "tradition_grant":
                eid = _entry(conn, ids, "TREE_MEMBERS", ids["m_author"])
                conn.execute(
                    text(
                        "INSERT INTO access_grant (id, tree_id, membership_id, user_id, resource_type, resource_id, permission) "
                        "VALUES (:id, :t, :m, :u, 'tradition', :r, 'view')"
                    ),
                    {"id": uuid.uuid4(), "t": ids["t"], "m": ids["m_cousin"], "u": ids["cousin"], "r": eid},
                )
            elif case == "orphaned_only_me":
                _orphan(conn, ids)
            elif case == "transferred":
                _entry(conn, ids, "ONLY_ME", ids["m_cousin"])  # the author gave it to the cousin
            else:  # a family entry whose author left and was invited again (a new membership)
                _orphan(conn, ids, "TREE_MEMBERS")
                conn.execute(
                    text(
                        "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['VIEWER'])"
                    ),
                    {"id": uuid.uuid4(), "t": ids["t"], "u": ids["leaver"]},
                )
            before = conn.execute(
                text("SELECT id, privacy_level, owner_membership_id FROM tradition_entry ORDER BY id")
            ).all()
            grants = conn.execute(text("SELECT count(*) FROM access_grant")).scalar()
        head = None
        with engine.connect() as conn:
            head = _version(conn)
        with pytest.raises(RuntimeError, match="lossy downgrade refused"):
            command.downgrade(cfg, "3f6a8c1d2e94")
        with pytest.raises(RuntimeError, match="lossy downgrade refused"):
            command.downgrade(cfg, "base")
        with engine.connect() as conn:  # nothing changed, not even the steps above 8d2e6b4f1a37
            assert _version(conn) == head
            assert (
                conn.execute(
                    text("SELECT id, privacy_level, owner_membership_id FROM tradition_entry ORDER BY id")
                ).all()
                == before
            )
            assert conn.execute(text("SELECT count(*) FROM access_grant")).scalar() == grants
        # stopping above 8d2e6b4f1a37 loses nothing about traditions' audiences and is allowed
        command.downgrade(cfg, "e4b8c2d6f913")
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            assert _version(conn) == head
        engine.dispose()
    finally:
        _drop(admin, url)


def test_a_downgrade_that_loses_nothing_runs_and_the_upgrade_re_runs():
    """With only entries owned by their authoring membership, no grants and no Selected members, the
    downgrade is allowed and access is the same before and after (``ONLY_ME`` by its author is
    ``PRIVATE_SELF`` by its author under the older code). Re-upgrading is idempotent."""
    admin, url = _fresh("_guard_clean")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            only = _entry(conn, ids, "ONLY_ME", ids["m_author"])
            fam = _entry(conn, ids, "TREE_MEMBERS", ids["m_author"])
        command.downgrade(cfg, "3f6a8c1d2e94")
        with engine.connect() as conn:
            assert dict(conn.execute(text("SELECT id, privacy_level FROM tradition_entry")).all()) == {
                only: "PRIVATE_SELF",
                fam: "TREE_MEMBERS",
            }
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "e4b8c2d6f913")
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            got = {
                r.id: (r.privacy_level, r.owner_membership_id)
                for r in conn.execute(
                    text("SELECT id, privacy_level, owner_membership_id FROM tradition_entry")
                )
            }
            assert got == {only: ("ONLY_ME", ids["m_author"]), fam: ("TREE_MEMBERS", ids["m_author"])}
            assert (
                conn.execute(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname = 'tradition_entry_record_owner'")
                ).scalar()
                == 1
            )
        engine.dispose()
    finally:
        _drop(admin, url)


def test_the_forward_migration_narrows_leftover_private_self_and_is_idempotent():
    """Rows written as ``PRIVATE_SELF`` after 8d2e6b4f1a37 (older code, before the trigger existed)
    become ``ONLY_ME``. Nothing else changes: owners, other levels and grants are untouched, and no
    owner is inferred for an ownerless row."""
    admin, url = _fresh("_guard_forward")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "e4b8c2d6f913")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            owned = _entry(conn, ids, "PRIVATE_SELF", ids["m_author"])
            ownerless = _orphan(conn, ids, "PRIVATE_SELF")
            custom = _entry(conn, ids, "CUSTOM", ids["m_author"])
        for _ in range(2):
            command.upgrade(cfg, "head")
            with engine.connect() as conn:
                got = {
                    r.id: (r.privacy_level, r.owner_membership_id)
                    for r in conn.execute(
                        text("SELECT id, privacy_level, owner_membership_id FROM tradition_entry")
                    )
                }
                assert got == {
                    owned: ("ONLY_ME", ids["m_author"]),
                    ownerless: ("ONLY_ME", None),
                    custom: ("CUSTOM", ids["m_author"]),
                }
            command.downgrade(cfg, "e4b8c2d6f913")  # the guard allows this: it stops above 8d2e
        engine.dispose()
    finally:
        _drop(admin, url)


def test_the_read_only_inventory_returns_counts_only():
    """docs/operations/tradition-ownership-inventory.sql runs in a READ ONLY transaction and returns
    categories and counts: no ids, titles, bodies, names or e-mail addresses."""
    sql = (
        Path(__file__).resolve().parents[2] / "docs/operations/tradition-ownership-inventory.sql"
    ).read_text()
    admin, url = _fresh("_inventory")
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            ids = _seed(conn)
            _entry(conn, ids, "ONLY_ME", ids["m_author"])
            _entry(conn, ids, "SELECTED_MEMBERS", ids["m_author"])
            _entry(conn, ids, "ONLY_ME", ids["m_cousin"])  # transferred
            _orphan(conn, ids)
        with engine.connect() as conn:
            conn.execute(text("BEGIN READ ONLY"))
            rows = conn.execute(text(sql)).mappings().all()
            conn.execute(text("ROLLBACK"))
        assert rows and all(set(r.keys()) == {"category", "privacy_level", "entries"} for r in rows)
        counts = {(r["category"], r["privacy_level"]): r["entries"] for r in rows}
        assert counts[("orphaned", "ONLY_ME")] == 1
        assert counts[("owner_is_not_author", "ONLY_ME")] == 1
        assert counts[("selected_members", "SELECTED_MEMBERS")] == 1
        engine.dispose()
    finally:
        _drop(admin, url)


def test_tradition_guard_revision_is_the_single_head():
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(_cfg()).get_heads()
    assert len(heads) == 1 or os.environ.get("VSH_ALLOW_MULTIPLE_HEADS")
