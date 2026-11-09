"""Family traditions on the record sharing model (ADR-0027, increment 2; threat T57).

A tradition entry is a shareable record: Only me, Selected members, Selected branch or All family
members, owned by its author's membership. Nobody outside its audience — tree owner, family admin,
branch admin or a promoted member — learns anything about it through any route.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from typing import Any

from sqlalchemy import create_engine, select, text

from alembic import command
from app.models import AuditEvent
from tests.conftest import _ADMIN_URL, _BASE, owner_session
from tests.helpers import create_person
from tests.test_migrations import DB, _cfg

RECIPE = {"kind": "recipe", "title": "Nani's kheer", "body": "Rice, milk, jaggery. Stir for an hour."}


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


def test_only_me_entry_is_invisible_to_every_role_on_every_route(owner, tree, member_factory):
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Pune"}).json()
    author = member_factory(["CONTRIBUTOR"], name="Author")
    e = _new(author, t, title="Nani zzqk kheer", privacy_level="ONLY_ME")
    assert e["privacy_level"] == "ONLY_ME" and e["is_owner"] is True and e["can_edit_sharing"] is True
    others = {
        "tree_owner": owner,
        "family_admin": member_factory(["FAMILY_ADMIN"], name="Admin"),
        "branch_admin": member_factory(["BRANCH_ADMIN"], branch_id=b["id"], name="Branch admin"),
        "reviewer": member_factory(["REVIEWER"], name="Reviewer"),
        "viewer": member_factory(["VIEWER"], name="Viewer"),
    }
    for name, c in others.items():
        assert not _sees(c, t, e["id"]), name
        assert c.get(f"/trees/{t}/traditions/{e['id']}/history").status_code == 404, name
        assert c.get(f"/trees/{t}/traditions/{e['id']}/sharing").status_code == 404, name
        assert e["id"] not in _listed(c, t), name
        assert e["id"] not in _listed(c, t, q="zzqk"), name
        assert (
            c.get(
                f"/trees/{t}/citations", params={"target_type": "tradition", "target_id": e["id"]}
            ).status_code
            == 404
        )
    assert _sees(author, t, e["id"])
    # the archive export, the grant list and the audit log say nothing about it either
    z = zipfile.ZipFile(io.BytesIO(owner.get(f"/trees/{t}/exports/archive").content))
    canonical = json.loads(
        z.read(next(n for n in z.namelist() if n.endswith("genealogy/canonical-data.json")))
    )
    assert e["id"] not in json.dumps(canonical)
    assert e["id"] not in str(owner.get(f"/trees/{t}/grants").json())


def test_private_self_keeps_its_author_only_meaning(owner, tree, member_factory):
    """Traditions used PRIVATE_SELF for "the author only"; it becomes ONLY_ME, never wider."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    e = _new(author, t, privacy_level="PRIVATE_SELF")
    assert e["privacy_level"] == "ONLY_ME"
    assert not _sees(owner, t, e["id"])  # PRIVATE_SELF elsewhere also admits the tree owner


def test_promotion_reveals_no_private_entry(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    e = _new(author, t, privacy_level="ONLY_ME")
    cousin = member_factory(["VIEWER"], name="Cousin")
    assert (
        owner.patch(
            f"/trees/{t}/members/{_mid(owner, t, cousin)}", json={"roles": ["FAMILY_ADMIN"]}
        ).status_code
        == 200
    )
    assert not _sees(cousin, t, e["id"])


def test_selected_members_and_revocation(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    asha, ravi = member_factory(["VIEWER"], name="Asha"), member_factory(["VIEWER"], name="Ravi")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    e = _new(author, t, privacy_level="ONLY_ME")
    r = _share(
        author,
        t,
        e["id"],
        "SELECTED_MEMBERS",
        members=[{"membership_id": _mid(owner, t, asha), "can_download": True}],
    )
    assert r.status_code == 200, r.text
    assert {a["display_name"]: a["access"] for a in r.json()["audience"]} == {
        "Author": "owner",
        "Asha": "selected",
    }
    assert r.json()["allow_download"] is False  # entries are text: no separate download right
    assert _sees(asha, t, e["id"]) and e["id"] in _listed(asha, t)
    assert not _sees(ravi, t, e["id"]) and not _sees(admin, t, e["id"])
    # the grant is the owner's to see and revoke; a privacy manager is not told it exists
    mine = [g for g in author.get(f"/trees/{t}/grants").json() if g["resource_type"] == "tradition"]
    assert len(mine) == 1 and e["id"] not in str(owner.get(f"/trees/{t}/grants").json())
    assert owner.delete(f"/trees/{t}/grants/{mine[0]['id']}").status_code == 404
    assert _share(author, t, e["id"], "ONLY_ME").status_code == 200
    assert not _sees(asha, t, e["id"])
    # no cross-tree members, and ONLY_ME cannot be granted directly
    assert (
        _share(
            author, t, e["id"], "SELECTED_MEMBERS", members=[{"membership_id": str(uuid.uuid4())}]
        ).status_code
        == 404
    )
    body = {
        "user_id": asha.user["id"],
        "resource_type": "tradition",
        "resource_id": e["id"],
        "permission": "view",
    }
    r = author.post(f"/trees/{t}/grants", json=body)
    assert r.status_code == 409 and r.json()["error"]["code"] == "only_me_record"


def test_grants_on_an_entry_die_with_the_membership(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    asha = member_factory(["VIEWER"], name="Asha")
    e = _new(author, t, privacy_level="ONLY_ME")
    mid = _mid(owner, t, asha)
    assert _share(author, t, e["id"], "SELECTED_MEMBERS", members=[{"membership_id": mid}]).status_code == 200
    assert owner.delete(f"/trees/{t}/members/{mid}").status_code == 200
    from tests.conftest import join_tree

    join_tree(owner, asha, t, ["VIEWER"])
    assert not _sees(asha, t, e["id"])


def test_branch_audience_widening_and_who_may_change_it(owner, tree, member_factory):
    t = tree["id"]
    pune = owner.post(f"/trees/{t}/branches", json={"name": "Pune"}).json()
    kashi = owner.post(f"/trees/{t}/branches", json={"name": "Kashi"}).json()
    author = member_factory(["CONTRIBUTOR"], name="Author")
    inside = member_factory(["VIEWER"], branch_id=pune["id"], name="Pune cousin")
    outside = member_factory(["VIEWER"], branch_id=kashi["id"], name="Kashi cousin")
    editor = member_factory(["CONTRIBUTOR"], name="Editor")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    e = _new(author, t, privacy_level="ONLY_ME")
    r = author.put(
        f"/trees/{t}/traditions/{e['id']}/sharing",
        json={"privacy_level": "FAMILY_BRANCH", "audience_branch_id": pune["id"]},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "confirm_wider"
    assert _share(author, t, e["id"], "FAMILY_BRANCH", audience_branch_id=pune["id"]).status_code == 200
    assert _sees(inside, t, e["id"]) and _sees(admin, t, e["id"]) and not _sees(outside, t, e["id"])
    # moving a "Selected branch" entry to another branch is an audience change: not for editors
    r = editor.patch(f"/trees/{t}/traditions/{e['id']}", json={"branch_id": kashi["id"]})
    assert r.status_code in (403, 404)
    assert not _sees(outside, t, e["id"])
    # an admin may narrow a shared entry, never widen it
    r = _share(admin, t, e["id"], "TREE_MEMBERS")
    assert r.status_code == 403 and r.json()["error"]["code"] == "owner_only_widening"
    r = admin.patch(f"/trees/{t}/traditions/{e['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 403
    assert _share(admin, t, e["id"], "ONLY_ME").status_code == 200
    assert not _sees(admin, t, e["id"]) and _sees(author, t, e["id"])
    with owner_session() as db:
        ev = db.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "record.visibility_changed", AuditEvent.target_id == e["id"]
            )
        ).all()
    assert [x.details["to"] for x in ev] == ["FAMILY_BRANCH", "ONLY_ME"]
    assert all("Nani" not in json.dumps(x.details) for x in ev)  # no content in the audit log


def test_linking_a_private_living_person_narrows(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    aunt = create_person(owner, t, "Kamla", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    e = _new(owner, t)  # All family members by default
    assert _sees(viewer, t, e["id"])
    r = owner.patch(
        f"/trees/{t}/traditions/{e['id']}",
        json={"links": [{"target_type": "person", "target_id": aunt["id"]}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["privacy_level"] == "SELECTED_MEMBERS"
    assert not _sees(viewer, t, e["id"])
    r = _share(owner, t, e["id"], "TREE_MEMBERS")
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"
    # a new entry about her: an explicit wide level is refused, the default narrows quietly
    link = [{"target_type": "person", "target_id": aunt["id"]}]
    r = owner.post(f"/trees/{t}/traditions", json={**RECIPE, "privacy_level": "TREE_MEMBERS", "links": link})
    assert r.status_code == 422 and r.json()["error"]["code"] == "privacy_too_open"
    r = owner.post(f"/trees/{t}/traditions", json={**RECIPE, "title": "About Kamla", "links": link})
    assert r.status_code == 201 and r.json()["privacy_level"] == "SELECTED_MEMBERS"


def test_making_a_person_private_narrows_their_entries(owner, tree, member_factory):
    t = tree["id"]
    viewer = member_factory(["VIEWER"], name="Viewer")
    ravi = create_person(owner, t, "Ravi", status="living", privacy_level="TREE_MEMBERS")
    e = _new(owner, t, links=[{"target_type": "person", "target_id": ravi["id"]}])
    assert _sees(viewer, t, e["id"])
    r = owner.put(f"/trees/{t}/people/{ravi['id']}/privacy", json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 200, r.text
    assert not _sees(viewer, t, e["id"])


def test_traditions_are_never_public(owner, tree):
    t = tree["id"]
    r = owner.post(f"/trees/{t}/traditions", json={**RECIPE, "privacy_level": "PUBLIC_DECEASED_ONLY"})
    assert r.status_code == 422
    e = _new(owner, t)
    assert _share(owner, t, e["id"], "PUBLIC_DECEASED_ONLY").status_code == 422


def test_a_proposal_cannot_change_who_reads_someone_elses_entry(owner, tree, member_factory):
    """Proposals are applied as the proposer (ADR-0021), so the sharing rules hold through review."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    other = member_factory(["CONTRIBUTOR"], name="Other")
    e = _new(author, t)
    prop = other.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "make it mine",
            "items": [
                {
                    "target_type": "tradition",
                    "op": "update",
                    "target_id": e["id"],
                    "patch": {"privacy_level": "ONLY_ME"},
                }
            ],
            "submit": True,
        },
    )
    assert prop.status_code == 201, prop.text
    r = owner.post(f"/trees/{t}/proposals/{prop.json()['id']}/approve", json={})
    assert r.status_code == 403
    assert owner.get(f"/trees/{t}/traditions/{e['id']}").json()["privacy_level"] == "TREE_MEMBERS"


def test_migration_maps_private_self_to_only_me_and_back():
    """8d2e6b4f1a37: a tradition's PRIVATE_SELF (author only) becomes ONLY_ME with its owner; the
    downgrade restores PRIVATE_SELF and deletes tradition grants."""
    db = DB + "_trad"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "3f6a8c1d2e94")
        engine = create_engine(url)
        tree_id, user_id, mid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        private, shared = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO app_user (id, email, password_hash, display_name) VALUES (:id, 'a@example.com', 'x', 'A')"
                ),
                {"id": user_id},
            )
            conn.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"),
                {"id": tree_id, "s": str(tree_id)},
            )
            conn.execute(
                text(
                    "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['CONTRIBUTOR'])"
                ),
                {"id": mid, "t": tree_id, "u": user_id},
            )
            for eid, level in ((private, "PRIVATE_SELF"), (shared, "TREE_MEMBERS")):
                conn.execute(
                    text(
                        "INSERT INTO tradition_entry (id, tree_id, kind, title, privacy_level, created_by) "
                        "VALUES (:id, :t, 'recipe', 'R', :lvl, :u)"
                    ),
                    {"id": eid, "t": tree_id, "lvl": level, "u": user_id},
                )
        command.upgrade(cfg, "8d2e6b4f1a37")
        with engine.begin() as conn:
            rows = dict(conn.execute(text("SELECT id, privacy_level FROM tradition_entry")).all())
            owners = set(conn.execute(text("SELECT owner_membership_id FROM tradition_entry")).scalars())
            assert rows == {private: "ONLY_ME", shared: "TREE_MEMBERS"} and owners == {mid}
            conn.execute(
                text("UPDATE tradition_entry SET privacy_level = 'SELECTED_MEMBERS' WHERE id = :id"),
                {"id": shared},
            )
            conn.execute(
                text(
                    "INSERT INTO access_grant (id, tree_id, membership_id, user_id, resource_type, resource_id, permission) "
                    "VALUES (:id, :t, :m, :u, 'tradition', :r, 'view')"
                ),
                {"id": uuid.uuid4(), "t": tree_id, "m": mid, "u": user_id, "r": shared},
            )
        command.downgrade(cfg, "3f6a8c1d2e94")
        with engine.connect() as conn:
            rows = dict(conn.execute(text("SELECT id, privacy_level FROM tradition_entry")).all())
            assert rows == {private: "PRIVATE_SELF", shared: "CUSTOM"}
            assert conn.execute(text("SELECT count(*) FROM access_grant")).scalar() == 0
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()


# ---------------------------------------------------------------- fixes before merging (review of #51)
def _audit_ids(client: Any, t: str) -> list[dict[str, Any]]:
    r = client.get(f"/trees/{t}/audit", params={"limit": 200})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_audit_log_never_reveals_someone_elses_private_entry(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    private = _new(author, t, privacy_level="ONLY_ME")
    shared = _new(author, t, privacy_level="TREE_MEMBERS", title="Holi")
    assert author.delete(f"/trees/{t}/traditions/{shared['id']}").status_code == 200  # withdrawn
    events = _audit_ids(owner, t)
    assert all(e.get("target_id") != private["id"] for e in events)
    assert any(
        e["target_type"] == "private_record" and e["target_id"] is None and e["details"] == {} for e in events
    )
    # a withdrawn entry that was shared keeps its history in the log
    actions = {e["action"] for e in events if e.get("target_id") == shared["id"]}
    assert {"tradition.created", "tradition.withdrawn"} <= actions
    # the tree owner's own private entry stays readable in the log
    mine = _new(owner, t, privacy_level="ONLY_ME", title="Mine")
    assert any(e.get("target_id") == mine["id"] for e in _audit_ids(owner, t))


def test_members_it_is_shared_with_only_read_a_private_entry(owner, tree, member_factory):
    """ADR-0027 §10: a grantee changes nothing, whatever their role (not even through review)."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["CONTRIBUTOR"], name="Cousin")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    e = _new(author, t, privacy_level="ONLY_ME")
    r = _share(
        author,
        t,
        e["id"],
        "SELECTED_MEMBERS",
        members=[{"membership_id": _mid(owner, t, cousin)}, {"membership_id": _mid(owner, t, admin)}],
    )
    assert r.status_code == 200, r.text
    for grantee in (cousin, admin):
        got = grantee.get(f"/trees/{t}/traditions/{e['id']}").json()
        assert (got["can_edit"], got["can_withdraw"], got["is_owner"]) == (False, False, False)
        r = grantee.patch(f"/trees/{t}/traditions/{e['id']}", json={"body": "Changed"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_content_owner"
        assert grantee.delete(f"/trees/{t}/traditions/{e['id']}").status_code == 403
    proposal = {
        "rationale": "Correct it",
        "items": [
            {"target_type": "tradition", "op": "update", "target_id": e["id"], "patch": {"body": "Changed"}}
        ],
        "submit": True,
    }
    assert cousin.post(f"/trees/{t}/proposals", json=proposal).status_code == 403
    assert author.get(f"/trees/{t}/traditions/{e['id']}").json()["body"] == RECIPE["body"]
    own = author.get(f"/trees/{t}/traditions/{e['id']}").json()
    assert (own["can_edit"], own["can_withdraw"], own["is_owner"]) == (True, True, True)
    assert author.patch(f"/trees/{t}/traditions/{e['id']}", json={"body": "Owner's edit"}).status_code == 200


def test_withdrawn_grants_give_no_access(owner, tree, member_factory):
    """Every way of taking access back works on the next request (ADR-0027 §7)."""
    import datetime as dt

    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["CONTRIBUTOR"], name="Cousin")
    other = member_factory(["VIEWER"], name="Other")
    cm, om = _mid(owner, t, cousin), _mid(owner, t, other)

    def shared_with_cousin() -> str:
        e = _new(author, t, privacy_level="ONLY_ME")
        assert (
            _share(author, t, e["id"], "SELECTED_MEMBERS", members=[{"membership_id": cm}]).status_code == 200
        )
        assert _sees(cousin, t, e["id"]) and e["id"] in _listed(cousin, t)
        return e["id"]

    def gone(eid: str) -> bool:
        return (
            not _sees(cousin, t, eid)
            and eid not in _listed(cousin, t)
            and eid not in _listed(cousin, t, q="kheer")
        )

    a = shared_with_cousin()  # removed from the members in the sharing panel
    assert _share(author, t, a, "SELECTED_MEMBERS", members=[{"membership_id": om}]).status_code == 200
    assert gone(a)
    b = shared_with_cousin()  # the grant revoked through /grants
    gid = next(g["id"] for g in author.get(f"/trees/{t}/grants").json() if g["resource_id"] == b)
    assert author.delete(f"/trees/{t}/grants/{gid}").status_code == 200
    assert gone(b)
    c = shared_with_cousin()  # narrowed to Only me, then shared with someone else
    assert author.patch(f"/trees/{t}/traditions/{c}", json={"privacy_level": "ONLY_ME"}).status_code == 200
    assert _share(author, t, c, "SELECTED_MEMBERS", members=[{"membership_id": om}]).status_code == 200
    assert gone(c)
    d = shared_with_cousin()  # the entry withdrawn
    assert author.delete(f"/trees/{t}/traditions/{d}").status_code == 200
    assert gone(d)
    e = _new(author, t, privacy_level="ONLY_ME")["id"]  # an expired grant
    assert _share(author, t, e, "SELECTED_MEMBERS", members=[{"membership_id": om}]).status_code == 200
    past = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)).isoformat()
    r = author.post(
        f"/trees/{t}/grants",
        json={
            "user_id": cousin.user["id"],
            "resource_type": "tradition",
            "resource_id": e,
            "permission": "view",
            "expires_at": past,
        },
    )
    assert r.status_code == 201, r.text
    assert gone(e)
    # a proposal the cousin made while they had access goes with it
    f = _new(author, t, privacy_level="TREE_MEMBERS", title="Shared kheer")["id"]
    p = cousin.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "r",
            "items": [{"target_type": "tradition", "op": "update", "target_id": f, "patch": {"body": "x"}}],
            "submit": False,
        },
    )
    assert p.status_code == 201, p.text
    assert _share(author, t, f, "SELECTED_MEMBERS", members=[{"membership_id": om}]).status_code == 200
    assert cousin.get(f"/trees/{t}/proposals/{p.json()['id']}").status_code == 404


def test_a_proposal_is_hidden_once_its_entry_becomes_private(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["CONTRIBUTOR"], name="Cousin")
    e = _new(author, t, privacy_level="TREE_MEMBERS", title="Holi")
    assert owner.put(f"/trees/{t}/review-policy", json={"review_policy": "all"}).status_code == 200
    p = cousin.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "Colours from dawn",
            "items": [
                {"target_type": "tradition", "op": "update", "target_id": e["id"], "patch": {"body": "Dawn."}}
            ],
            "submit": True,
        },
    )
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    assert owner.get(f"/trees/{t}/proposals/{pid}").status_code == 200
    assert (
        author.patch(f"/trees/{t}/traditions/{e['id']}", json={"privacy_level": "ONLY_ME"}).status_code == 200
    )
    for who in (owner, cousin):
        assert who.get(f"/trees/{t}/proposals/{pid}").status_code == 404
        assert pid not in {
            x["id"] for x in who.get(f"/trees/{t}/proposals", params={"view": "to_review"}).json()["items"]
        }
        assert who.post(f"/trees/{t}/proposals/{pid}/approve", json={}).status_code == 404
    # shared again: the proposal is back for the reviewer
    assert (
        author.patch(f"/trees/{t}/traditions/{e['id']}", json={"privacy_level": "TREE_MEMBERS"}).status_code
        == 200
    )
    assert owner.get(f"/trees/{t}/proposals/{pid}").status_code == 200


def test_migration_private_self_exception_edge_cases():
    """8d2e6b4f1a37 as an exception to ADR-0027 open point 2: what it changes and what it does not.

    Upgrade: an author who is a member owns their entries; a former member's entry becomes an
    orphan (no owner), even after that person is invited again; CUSTOM stays; withdrawn entries
    convert too; grants on other records are untouched and no grant is created. Downgrade: Only me
    returns to PRIVATE_SELF, Selected members to CUSTOM, tradition grants are deleted, others kept.
    """
    db = DB + "_trad_edges"
    url = f"{_BASE}/{db}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}"'))
    try:
        cfg = _cfg()
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "3f6a8c1d2e94")
        engine = create_engine(url)
        t, author, leaver = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        m_author, m_leaver_again = uuid.uuid4(), uuid.uuid4()
        mine, orphan, custom, withdrawn = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        person_grant = uuid.uuid4()
        with engine.begin() as conn:
            for uid, email in ((author, "a@example.com"), (leaver, "l@example.com")):
                conn.execute(
                    text(
                        "INSERT INTO app_user (id, email, password_hash, display_name) VALUES (:id, :e, 'x', 'U')"
                    ),
                    {"id": uid, "e": email},
                )
            conn.execute(
                text("INSERT INTO tree (id, name, slug) VALUES (:id, 'T', :s)"), {"id": t, "s": str(t)}
            )
            conn.execute(
                text(
                    "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['CONTRIBUTOR'])"
                ),
                {"id": m_author, "t": t, "u": author},
            )
            rows = (
                (mine, "PRIVATE_SELF", author, None),
                (orphan, "PRIVATE_SELF", leaver, None),  # the leaver is no longer a member
                (custom, "CUSTOM", author, None),
                (withdrawn, "PRIVATE_SELF", author, "2026-11-01T00:00:00+00:00"),
            )
            for eid, level, uid, gone in rows:
                conn.execute(
                    text(
                        "INSERT INTO tradition_entry (id, tree_id, kind, title, privacy_level, created_by, withdrawn_at) "
                        "VALUES (:id, :t, 'recipe', 'R', :lvl, :u, :w)"
                    ),
                    {"id": eid, "t": t, "lvl": level, "u": uid, "w": gone},
                )
            conn.execute(  # an existing grant on another kind of record
                text(
                    "INSERT INTO access_grant (id, tree_id, membership_id, user_id, resource_type, resource_id, permission) "
                    "VALUES (:id, :t, :m, :u, 'person', :r, 'view')"
                ),
                {"id": person_grant, "t": t, "m": m_author, "u": author, "r": uuid.uuid4()},
            )
        command.upgrade(cfg, "8d2e6b4f1a37")
        with engine.begin() as conn:
            got = {
                r.id: (r.privacy_level, r.owner_membership_id)
                for r in conn.execute(
                    text("SELECT id, privacy_level, owner_membership_id FROM tradition_entry")
                )
            }
            assert got == {
                mine: ("ONLY_ME", m_author),
                orphan: ("ONLY_ME", None),
                custom: ("CUSTOM", m_author),
                withdrawn: ("ONLY_ME", m_author),
            }
            grants = list(conn.execute(text("SELECT id, resource_type FROM access_grant")).all())
            assert [(g.id, g.resource_type) for g in grants] == [(person_grant, "person")]
            # the leaver is invited again: a new membership, still not the orphan's owner
            conn.execute(
                text(
                    "INSERT INTO tree_membership (id, tree_id, user_id, roles) VALUES (:id, :t, :u, ARRAY['CONTRIBUTOR'])"
                ),
                {"id": m_leaver_again, "t": t, "u": leaver},
            )
            assert (
                conn.execute(
                    text("SELECT owner_membership_id FROM tradition_entry WHERE id = :id"), {"id": orphan}
                ).scalar()
                is None
            )
            # sharing after upgrade, then a downgrade
            conn.execute(
                text("UPDATE tradition_entry SET privacy_level = 'SELECTED_MEMBERS' WHERE id = :id"),
                {"id": custom},
            )
            conn.execute(
                text(
                    "INSERT INTO access_grant (id, tree_id, membership_id, user_id, resource_type, resource_id, permission) "
                    "VALUES (:id, :t, :m, :u, 'tradition', :r, 'view')"
                ),
                {"id": uuid.uuid4(), "t": t, "m": m_leaver_again, "u": leaver, "r": custom},
            )
        command.downgrade(cfg, "3f6a8c1d2e94")
        with engine.connect() as conn:
            levels = dict(conn.execute(text("SELECT id, privacy_level FROM tradition_entry")).all())
            assert levels == {
                mine: "PRIVATE_SELF",
                orphan: "PRIVATE_SELF",
                custom: "CUSTOM",
                withdrawn: "PRIVATE_SELF",
            }
            assert [g.id for g in conn.execute(text("SELECT id FROM access_grant"))] == [person_grant]
            cols = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = 'tradition_entry'"
                    )
                ).scalars()
            )
            assert "owner_membership_id" not in cols
        command.upgrade(cfg, "8d2e6b4f1a37")  # and up again: the conversion is idempotent
        with engine.connect() as conn:
            levels = dict(conn.execute(text("SELECT id, privacy_level FROM tradition_entry")).all())
            assert levels == {mine: "ONLY_ME", orphan: "ONLY_ME", custom: "CUSTOM", withdrawn: "ONLY_ME"}
            owners = dict(conn.execute(text("SELECT id, owner_membership_id FROM tradition_entry")).all())
            # the re-invited leaver now matches created_by, so a second upgrade gives them their entry back
            assert owners[orphan] == m_leaver_again
        engine.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        admin.dispose()


def test_author_removed_and_invited_again(owner, tree, member_factory):
    """The owner is a membership: a removed author's private entries stay with their grantees only;
    nobody (admins included) can read, share or claim them, and inviting the author again gives
    nothing back."""
    from tests.conftest import join_tree

    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["VIEWER"], name="Cousin")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    only = _new(author, t, privacy_level="PRIVATE_SELF")  # a submitted PRIVATE_SELF is Only me
    assert only["privacy_level"] == "ONLY_ME"
    shared = _new(author, t, privacy_level="ONLY_ME", title="Shared kheer")
    assert (
        _share(
            author, t, shared["id"], "SELECTED_MEMBERS", members=[{"membership_id": _mid(owner, t, cousin)}]
        ).status_code
        == 200
    )
    assert owner.delete(f"/trees/{t}/members/{_mid(owner, t, author)}").status_code == 200

    assert _sees(cousin, t, shared["id"]) and not _sees(cousin, t, only["id"])  # grantees keep access
    for who in (admin, owner):
        assert not _sees(who, t, only["id"]) and not _sees(who, t, shared["id"])
        assert who.get(f"/trees/{t}/traditions/{shared['id']}/sharing").status_code == 404
        assert _share(who, t, shared["id"], "TREE_MEMBERS").status_code == 404
    assert cousin.patch(f"/trees/{t}/traditions/{shared['id']}", json={"body": "x"}).status_code == 403

    join_tree(owner, author, t, ["CONTRIBUTOR"])  # the same person, invited again
    assert not _sees(author, t, only["id"]) and not _sees(author, t, shared["id"])
    assert _share(author, t, shared["id"], "TREE_MEMBERS").status_code == 404
