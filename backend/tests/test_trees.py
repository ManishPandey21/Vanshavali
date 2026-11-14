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


def test_membership_invitation_creation_is_rate_limited(owner, tree):
    for index in range(30):
        response = owner.post(
            f"/trees/{tree['id']}/invitations",
            json={"email": f"relative-{index}@example.com", "roles": ["VIEWER"]},
        )
        assert response.status_code == 201, response.text

    limited = owner.post(
        f"/trees/{tree['id']}/invitations",
        json={"email": "one-too-many@example.com", "roles": ["VIEWER"]},
    )
    assert limited.status_code == 429


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


# ---------------------------------------------------------------- role management (regressions)
def _mid(client, t, user_id):
    return next(m["id"] for m in client.get(f"/trees/{t}/members").json() if m["user_id"] == user_id)


def _audit(owner, t, action):
    return [e for e in owner.get(f"/trees/{t}/audit").json()["items"] if e["action"] == action]


def test_only_the_owner_can_remove_a_family_admin(owner, tree, member_factory):
    """Regression: a family admin could not demote another admin, but could delete their membership."""
    t = tree["id"]
    a1 = member_factory(["FAMILY_ADMIN"], name="Admin one")
    a2 = member_factory(["FAMILY_ADMIN"], name="Admin two")
    target = _mid(owner, t, a2.user["id"])
    assert a1.patch(f"/trees/{t}/members/{target}", json={"roles": ["VIEWER"]}).status_code == 403
    assert a1.delete(f"/trees/{t}/members/{target}").status_code == 403
    assert a1.patch(f"/trees/{t}/members/{target}", json={"clear_branch": True}).status_code == 403
    assert any(m["user_id"] == a2.user["id"] for m in owner.get(f"/trees/{t}/members").json())
    # a family admin still manages ordinary members, and the owner manages admins
    c = member_factory(["CONTRIBUTOR"], name="Cousin")
    assert (
        a1.patch(f"/trees/{t}/members/{_mid(owner, t, c.user['id'])}", json={"roles": ["VIEWER"]}).status_code
        == 200
    )
    assert a1.delete(f"/trees/{t}/members/{_mid(owner, t, c.user['id'])}").status_code == 200
    assert owner.patch(f"/trees/{t}/members/{target}", json={"roles": ["CONTRIBUTOR"]}).status_code == 200
    assert owner.delete(f"/trees/{t}/members/{target}").status_code == 200


def test_branch_admin_only_changes_roles_it_could_grant(owner, tree, member_factory):
    """Regression: a branch admin could demote or remove peers and custodians in its branch."""
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Varanasi branch"}).json()["id"]
    ba1 = member_factory(["BRANCH_ADMIN"], branch_id=b, name="Branch admin one")
    ba2 = member_factory(["BRANCH_ADMIN"], branch_id=b, name="Branch admin two")
    cust = member_factory(["DOCUMENT_CUSTODIAN"], branch_id=b, name="Custodian")
    for target in (ba2, cust):
        mid = _mid(owner, t, target.user["id"])
        assert ba1.patch(f"/trees/{t}/members/{mid}", json={"roles": ["VIEWER"]}).status_code == 403
        assert ba1.delete(f"/trees/{t}/members/{mid}").status_code == 403
    # adding a role it cannot grant to a member it can manage is refused too
    c = member_factory(["CONTRIBUTOR"], branch_id=b, name="Branch cousin")
    cmid = _mid(owner, t, c.user["id"])
    assert (
        ba1.patch(f"/trees/{t}/members/{cmid}", json={"roles": ["CONTRIBUTOR", "REVIEWER"]}).status_code
        == 403
    )
    # within its grant: contributor <-> viewer, and removal
    assert ba1.patch(f"/trees/{t}/members/{cmid}", json={"roles": ["VIEWER"]}).status_code == 200
    assert ba1.delete(f"/trees/{t}/members/{cmid}").status_code == 200


def test_role_changes_are_audited_with_before_and_after(owner, tree, member_factory):
    t = tree["id"]
    m = member_factory(["VIEWER"], name="Nephew")
    mid = _mid(owner, t, m.user["id"])
    owner.patch(f"/trees/{t}/members/{mid}", json={"roles": ["FAMILY_ADMIN"]})
    owner.patch(f"/trees/{t}/members/{mid}", json={"roles": ["CONTRIBUTOR"]})
    owner.delete(f"/trees/{t}/members/{mid}")
    updated = _audit(owner, t, "member.updated")
    details = [e["details"] for e in updated]
    assert {"previous_roles": ["VIEWER"], "roles": ["FAMILY_ADMIN"], "admin_change": True}.items() <= details[
        -1
    ].items()
    assert {
        "previous_roles": ["FAMILY_ADMIN"],
        "roles": ["CONTRIBUTOR"],
        "admin_change": True,
    }.items() <= details[0].items()
    removed = _audit(owner, t, "member.removed")[0]
    assert removed["details"]["roles"] == ["CONTRIBUTOR"] and removed["actor_user_id"] == owner.user["id"]


def test_a_family_admin_never_sees_private_self_data(owner, tree, member_factory):
    """Several family admins must not widen PRIVATE_SELF: only the owner (and the claimant) see it."""
    from tests.helpers import create_person

    t = tree["id"]
    p = create_person(owner, t, "Kamla", privacy_level="PRIVATE_SELF")
    admin = member_factory(["FAMILY_ADMIN"], name="Second admin")
    assert owner.get(f"/trees/{t}/people/{p['id']}").status_code == 200
    assert admin.get(f"/trees/{t}/people/{p['id']}").status_code == 404


def test_the_ui_is_told_what_each_manager_may_do(owner, tree, member_factory):
    """my_grantable_roles and can_manage mirror the server's rules, so the UI hides what would be refused."""
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Patna branch"}).json()["id"]
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    badmin = member_factory(["BRANCH_ADMIN"], branch_id=b, name="Branch admin")
    member_factory(["CONTRIBUTOR"], branch_id=b, name="Branch cousin")
    viewer = member_factory(["VIEWER"], name="Viewer")
    assert set(owner.get(f"/trees/{t}").json()["my_grantable_roles"]) >= {"OWNER", "FAMILY_ADMIN"}
    granted = set(admin.get(f"/trees/{t}").json()["my_grantable_roles"])
    assert "FAMILY_ADMIN" not in granted and "OWNER" not in granted and "CONTRIBUTOR" in granted
    assert set(badmin.get(f"/trees/{t}").json()["my_grantable_roles"]) == {
        "CONTRIBUTOR",
        "RESEARCHER",
        "VIEWER",
    }
    assert viewer.get(f"/trees/{t}").json()["my_grantable_roles"] == []
    by_name = {m["display_name"]: m["can_manage"] for m in admin.get(f"/trees/{t}/members").json()}
    assert by_name["Branch cousin"] and by_name["Viewer"] and not by_name["Tree Owner"]
    by_name = {m["display_name"]: m["can_manage"] for m in badmin.get(f"/trees/{t}/members").json()}
    assert by_name["Branch cousin"] and not by_name["Viewer"] and not by_name["Admin"]
    assert not any(m["can_manage"] for m in viewer.get(f"/trees/{t}/members").json())
