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
