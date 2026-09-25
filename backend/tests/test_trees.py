from __future__ import annotations

from sqlalchemy import text

from app.core.db import get_engine
from tests.conftest import join_tree


def test_create_and_list_tree(owner, tree):
    assert tree["my_roles"] == ["OWNER"]
    assert "person.write" in tree["my_permissions"]
    trees = owner.get("/trees").json()
    assert [t["id"] for t in trees] == [tree["id"]]


def test_non_member_gets_404_not_403(make_client, tree):
    stranger = make_client()
    stranger.register()
    r = stranger.get(f"/trees/{tree['id']}")
    assert r.status_code == 404
    assert stranger.get(f"/trees/{tree['id']}/members").status_code == 404


def test_invitation_flow_and_roles(owner, tree, make_client):
    viewer = make_client()
    viewer.register(email="viewer@example.com")
    t = join_tree(owner, viewer, tree["id"], ["VIEWER"])
    assert t["my_roles"] == ["VIEWER"]
    assert "person.write" not in t["my_permissions"]
    members = owner.get(f"/trees/{tree['id']}/members").json()
    assert {m["email"] for m in members} >= {"viewer@example.com"}
    # viewer cannot see other members' emails
    seen = viewer.get(f"/trees/{tree['id']}/members").json()
    assert all(m["email"] in ("", "viewer@example.com") for m in seen)


def test_invitation_bound_to_email(owner, tree, make_client):
    r = owner.post(
        f"/trees/{tree['id']}/invitations", json={"email": "intended@example.com", "roles": ["VIEWER"]}
    )
    token = r.json()["token"]
    other = make_client()
    other.register(email="attacker@example.com")
    assert other.post(f"/invitations/{token}/accept").status_code == 403


def test_invitation_single_use_and_revocable(owner, tree, make_client):
    r = owner.post(
        f"/trees/{tree['id']}/invitations", json={"email": "once@example.com", "roles": ["VIEWER"]}
    )
    inv = r.json()
    c = make_client()
    c.register(email="once@example.com")
    assert c.post(f"/invitations/{inv['token']}/accept").status_code == 200
    assert c.post(f"/invitations/{inv['token']}/accept").status_code == 409
    r2 = owner.post(
        f"/trees/{tree['id']}/invitations", json={"email": "revoked@example.com", "roles": ["VIEWER"]}
    )
    assert owner.delete(f"/trees/{tree['id']}/invitations/{r2.json()['id']}").status_code == 200
    d = make_client()
    d.register(email="revoked@example.com")
    assert d.post(f"/invitations/{r2.json()['token']}/accept").status_code == 404


def test_only_owner_can_grant_admin(member_factory, tree, make_client):
    admin = member_factory(["FAMILY_ADMIN"])
    r = admin.post(
        f"/trees/{tree['id']}/invitations", json={"email": "x@example.com", "roles": ["FAMILY_ADMIN"]}
    )
    assert r.status_code == 403
    r = admin.post(
        f"/trees/{tree['id']}/invitations", json={"email": "x@example.com", "roles": ["CONTRIBUTOR"]}
    )
    assert r.status_code == 201


def test_viewer_cannot_manage_members_or_tree(member_factory, tree):
    viewer = member_factory(["VIEWER"])
    assert (
        viewer.post(
            f"/trees/{tree['id']}/invitations", json={"email": "y@example.com", "roles": ["VIEWER"]}
        ).status_code
        == 403
    )
    assert viewer.patch(f"/trees/{tree['id']}", json={"public_mode": "DECEASED_ONLY"}).status_code == 403
    assert viewer.get(f"/trees/{tree['id']}/audit").status_code == 403


def test_member_cannot_escalate_own_roles(member_factory, tree):
    admin = member_factory(["FAMILY_ADMIN"])
    members = admin.get(f"/trees/{tree['id']}/members").json()
    mine = next(m for m in members if m["user_id"] == admin.user["id"])
    r = admin.patch(f"/trees/{tree['id']}/members/{mine['id']}", json={"roles": ["OWNER"]})
    assert r.status_code == 403


def test_last_owner_cannot_be_removed_or_demoted(owner, tree):
    members = owner.get(f"/trees/{tree['id']}/members").json()
    me = members[0]
    assert (
        owner.patch(f"/trees/{tree['id']}/members/{me['id']}", json={"roles": ["VIEWER"]}).status_code == 409
    )
    assert owner.delete(f"/trees/{tree['id']}/members/{me['id']}").status_code == 409


def test_public_mode_change_is_audited(owner, tree):
    r = owner.patch(f"/trees/{tree['id']}", json={"public_mode": "DECEASED_ONLY"})
    assert r.status_code == 200
    events = owner.get(f"/trees/{tree['id']}/audit").json()["items"]
    assert any(e["action"] == "tree.public_sharing_changed" for e in events)


def test_audit_table_is_append_only(owner, tree):
    import pytest
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError), get_engine().begin() as c:
        c.execute(text("UPDATE audit_event SET action = 'tampered'"))
    with pytest.raises(DBAPIError), get_engine().begin() as c:
        c.execute(text("DELETE FROM audit_event"))


def test_deleted_tree_not_accessible(owner, tree):
    assert owner.delete(f"/trees/{tree['id']}").status_code == 200
    assert owner.get(f"/trees/{tree['id']}").status_code == 404
    assert owner.get("/trees").json() == []
