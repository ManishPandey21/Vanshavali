"""Family Admin nominations, approved by an Owner (ADR-0006 amendment of 9 Nov 2026; threat T56).

A nomination never grants a role by itself: the nominee accepts, then an Owner approves through the
normal role-change path. These tests cover every test the amendment lists before code.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text

from tests.conftest import new_tree, owner_session

BASE = "/trees/{t}/admin-nominations"


def _mid(client: Any, t: str, user_id: str) -> str:
    return next(m["id"] for m in client.get(f"/trees/{t}/members").json() if m["user_id"] == user_id)


def _roles(owner: Any, t: str, user_id: str) -> list[str]:
    return next(m["roles"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == user_id)


def _nominate(admin: Any, t: str, membership_id: str, reason: str = "Keeps the Varanasi records") -> Any:
    return admin.post(BASE.format(t=t), json={"membership_id": membership_id, "reason": reason})


def _audit(owner: Any, t: str) -> list[dict[str, Any]]:
    return owner.get(f"/trees/{t}/audit", params={"action": "admin_nomination."}).json()["items"]


def _setup(owner: Any, tree: dict[str, Any], member_factory: Any, nominee_roles: list[str] | None = None):
    t = tree["id"]
    admin = member_factory(["FAMILY_ADMIN"], name="Asha (admin)")
    nominee = member_factory(nominee_roles or ["CONTRIBUTOR"], name="Ravi (cousin)")
    return t, admin, nominee, _mid(owner, t, nominee.user["id"])


def _status(t: str, nomination_id: str) -> str:
    with owner_session() as s:
        return s.execute(
            text("SELECT status FROM admin_nomination WHERE tree_id = :t AND id = :i"),
            {"t": t, "i": nomination_id},
        ).scalar_one()


# ------------------------------------------------------------------ the happy path
def test_nominate_accept_approve_grants_the_role_only_at_the_end(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    r = _nominate(admin, t, mid)
    assert r.status_code == 201, r.text
    n = r.json()
    assert n["status"] == "open" and n["nominee_name"] == "Ravi (cousin)"
    assert n["nominator_name"] == "Asha (admin)" and n["reason"] == "Keeps the Varanasi records"
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]

    # the nominee sees their own, with who nominated them and why (owner decision 3)
    mine = nominee.get(BASE.format(t=t)).json()
    assert [m["id"] for m in mine] == [n["id"]] and mine[0]["can_accept"] and mine[0]["is_mine"]
    assert mine[0]["nominator_name"] == "Asha (admin)" and mine[0]["reason"] == "Keeps the Varanasi records"

    assert nominee.post(f"{BASE.format(t=t)}/{n['id']}/accept").status_code == 200
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]  # still unchanged

    r = owner.post(f"{BASE.format(t=t)}/{n['id']}/approve", json={})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["reason"] == ""  # reason erased on close
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR", "FAMILY_ADMIN"]
    assert nominee.get(BASE.format(t=t)).json() == []

    # the role change went through update_member as that owner, with the usual audit
    updated = owner.get(f"/trees/{t}/audit", params={"action": "member.updated"}).json()["items"][0]
    assert updated["actor_user_id"] == owner.user["id"] and updated["details"]["admin_change"] is True


def test_every_step_is_audited_without_the_reason(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid, reason="SECRET-REASON-TEXT").json()["id"]
    nominee.post(f"{BASE.format(t=t)}/{nid}/accept")
    owner.post(f"{BASE.format(t=t)}/{nid}/approve", json={})
    events = _audit(owner, t)
    assert [e["action"] for e in reversed(events)] == [
        "admin_nomination.created",
        "admin_nomination.accepted_by_nominee",
        "admin_nomination.approved",
    ]
    actors = [e["actor_user_id"] for e in reversed(events)]
    assert actors == [admin.user["id"], nominee.user["id"], owner.user["id"]]
    assert all(e["details"]["nominee_membership_id"] == mid for e in events)
    assert "SECRET-REASON-TEXT" not in owner.get(f"/trees/{t}/audit").text

    # the other steps
    other = member_factory(["VIEWER"], name="Meena")
    omid = _mid(owner, t, other.user["id"])
    for step, actor, path in (
        ("declined_by_nominee", other, "decline"),
        ("declined_by_owner", owner, "reject"),
        ("withdrawn", admin, "withdraw"),
    ):
        nid = _nominate(admin, t, omid).json()["id"]
        assert actor.post(f"{BASE.format(t=t)}/{nid}/{path}").status_code == 200
        assert _audit(owner, t)[0]["action"] == f"admin_nomination.{step}"
        assert _status(t, nid) != "open"


# ------------------------------------------------------------------ who may nominate, and whom
def test_only_a_family_admin_can_nominate(owner, tree, member_factory):
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Patna branch"}).json()["id"]
    target = member_factory(["VIEWER"], name="Target")
    mid = _mid(owner, t, target.user["id"])
    for roles, branch in (
        (["VIEWER"], None),
        (["CONTRIBUTOR"], None),
        (["REVIEWER"], None),
        (["RESEARCHER"], None),
        (["DOCUMENT_CUSTODIAN"], None),
        (["BRANCH_ADMIN"], b),  # owner decision 2
    ):
        m = member_factory(roles, branch_id=branch, name=f"Not admin {roles[0]}")
        assert _nominate(m, t, mid).status_code == 403, roles
    # an owner grants the role directly instead
    assert _nominate(owner, t, mid).status_code == 403
    assert owner.get(BASE.format(t=t)).json() == []


def test_no_self_nomination_and_no_admins_or_duplicates(owner, tree, member_factory):
    t, admin, _nominee, mid = _setup(owner, tree, member_factory)
    r = _nominate(admin, t, _mid(owner, t, admin.user["id"]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_nomination"
    r = _nominate(admin, t, _mid(owner, t, owner.user["id"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_admin"
    assert _nominate(admin, t, mid).status_code == 201
    r = _nominate(admin, t, mid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_nominated"
    assert admin.post(BASE.format(t=t), json={"membership_id": mid, "reason": "x" * 501}).status_code == 422
    assert admin.post(BASE.format(t=t), json={"membership_id": mid, "reason": ""}).status_code == 422


def test_at_most_five_open_nominations_per_tree(owner, tree, member_factory):
    t = tree["id"]
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    mids = [_mid(owner, t, member_factory(["VIEWER"], name=f"M{i}").user["id"]) for i in range(6)]
    for mid in mids[:5]:
        assert _nominate(admin, t, mid).status_code == 201
    r = _nominate(admin, t, mids[5])
    assert r.status_code == 409 and r.json()["error"]["code"] == "nomination_limit"


# ------------------------------------------------------------------ the two consents
def test_only_an_owner_approves_and_only_after_the_nominee_accepts(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    second_admin = member_factory(["FAMILY_ADMIN"], name="Second admin")
    nid = _nominate(admin, t, mid).json()["id"]
    url = f"{BASE.format(t=t)}/{nid}"
    r = owner.post(f"{url}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nominee_not_accepted"
    # nobody else answers for the nominee
    for other in (owner, admin, second_admin):
        assert other.post(f"{url}/accept").status_code == 403
    assert nominee.post(f"{url}/accept").status_code == 200
    # nobody but an owner approves: not the nominator, another family admin, or the nominee
    for other in (admin, second_admin):
        assert other.post(f"{url}/approve", json={}).status_code == 403
        assert other.post(f"{url}/reject").status_code == 403
    assert nominee.post(f"{url}/approve", json={}).status_code == 403  # sees it, may not decide
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]
    # and only the nominator withdraws
    assert second_admin.post(f"{url}/withdraw").status_code == 403
    assert owner.post(f"{url}/approve", json={}).status_code == 200


def test_the_first_owner_decision_wins(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    co_owner = member_factory(["OWNER"], name="Co-owner")
    nid = _nominate(admin, t, mid).json()["id"]
    nominee.post(f"{BASE.format(t=t)}/{nid}/accept")
    assert owner.post(f"{BASE.format(t=t)}/{nid}/reject").status_code == 200
    r = co_owner.post(f"{BASE.format(t=t)}/{nid}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nomination_closed"
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]


def test_a_declined_nomination_changes_nothing(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    nominee.post(f"{BASE.format(t=t)}/{nid}/accept")
    assert nominee.post(f"{BASE.format(t=t)}/{nid}/decline").status_code == 200  # changed their mind
    assert owner.post(f"{BASE.format(t=t)}/{nid}/approve", json={}).status_code == 409
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]


def test_branch_scope_is_cleared_only_with_explicit_confirmation(owner, tree, member_factory):
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Varanasi branch"}).json()["id"]
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    cousin = member_factory(["BRANCH_ADMIN", "CONTRIBUTOR"], branch_id=b, name="Branch cousin")
    mid = _mid(owner, t, cousin.user["id"])
    n = _nominate(admin, t, mid).json()
    assert n["nominee_branch_scoped"] is True
    cousin.post(f"{BASE.format(t=t)}/{n['id']}/accept")
    r = owner.post(f"{BASE.format(t=t)}/{n['id']}/approve", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "branch_scope_confirmation_required"
    member = next(m for m in owner.get(f"/trees/{t}/members").json() if m["id"] == mid)
    assert member["branch_id"] == b and member["roles"] == ["BRANCH_ADMIN", "CONTRIBUTOR"]
    assert owner.post(f"{BASE.format(t=t)}/{n['id']}/approve", json={"clear_branch": True}).status_code == 200
    member = next(m for m in owner.get(f"/trees/{t}/members").json() if m["id"] == mid)
    assert member["branch_id"] is None and member["roles"] == ["CONTRIBUTOR", "FAMILY_ADMIN"]


# ------------------------------------------------------------------ lapsing and expiry
def test_lapses_when_the_nominator_loses_family_admin(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    nominee.post(f"{BASE.format(t=t)}/{nid}/accept")
    owner.patch(f"/trees/{t}/members/{_mid(owner, t, admin.user['id'])}", json={"roles": ["CONTRIBUTOR"]})
    assert _status(t, nid) == "lapsed"
    assert owner.post(f"{BASE.format(t=t)}/{nid}/approve", json={}).status_code == 409
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]
    lapsed = _audit(owner, t)[0]
    assert (
        lapsed["action"] == "admin_nomination.lapsed" and lapsed["details"]["cause"] == "nominator_lost_role"
    )


def test_lapses_when_the_nominator_or_nominee_leaves(owner, tree, member_factory):
    t, admin, _nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    owner.delete(f"/trees/{t}/members/{mid}")
    assert _status(t, nid) == "lapsed"

    other = member_factory(["VIEWER"], name="Meena")
    nid2 = _nominate(admin, t, _mid(owner, t, other.user["id"])).json()["id"]
    owner.delete(f"/trees/{t}/members/{_mid(owner, t, admin.user['id'])}")
    assert _status(t, nid2) == "lapsed"
    causes = [e["details"]["cause"] for e in _audit(owner, t) if e["action"] == "admin_nomination.lapsed"]
    assert sorted(causes) == ["nominator_left", "nominee_left"]


def test_lapses_when_the_nominee_closes_their_account(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    assert nominee.post("/auth/close-account", json={"password": nominee.user["password"]}).status_code == 200
    assert _status(t, nid) == "lapsed"


def test_lapses_when_the_nominee_becomes_an_admin_another_way(owner, tree, member_factory, make_client):
    t, admin, _nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    owner.patch(f"/trees/{t}/members/{mid}", json={"roles": ["CONTRIBUTOR", "FAMILY_ADMIN"]})
    assert _status(t, nid) == "lapsed"

    # an owner's invitation adding the role to an existing member
    other = member_factory(["VIEWER"], name="Meena")
    nid2 = _nominate(admin, t, _mid(owner, t, other.user["id"])).json()["id"]
    inv = owner.post(f"/trees/{t}/invitations", json={"email": other.user["email"], "roles": ["OWNER"]})
    assert other.post(f"/invitations/{inv.json()['token']}/accept").status_code == 200
    assert _status(t, nid2) == "lapsed"


def test_a_stale_nomination_is_refused_even_if_a_hook_missed_it(owner, tree, member_factory):
    """Approval re-checks the lapse conditions itself (defence in depth)."""
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    nominee.post(f"{BASE.format(t=t)}/{nid}/accept")
    with owner_session() as s, s.begin():  # demote the nominator behind the service's back
        s.execute(
            text("UPDATE tree_membership SET roles = ARRAY['VIEWER'] WHERE tree_id = :t AND user_id = :u"),
            {"t": t, "u": admin.user["id"]},
        )
    r = owner.post(f"{BASE.format(t=t)}/{nid}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nomination_lapsed"
    assert _status(t, nid) == "lapsed"
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]


def test_expires_after_fourteen_days(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    n = _nominate(admin, t, mid).json()
    created = dt.datetime.fromisoformat(n["created_at"])
    assert dt.datetime.fromisoformat(n["expires_at"]) - created >= dt.timedelta(days=14) - dt.timedelta(
        seconds=5
    )
    nominee.post(f"{BASE.format(t=t)}/{n['id']}/accept")
    with owner_session() as s, s.begin():
        s.execute(
            text("UPDATE admin_nomination SET expires_at = now() - interval '1 minute' WHERE id = :i"),
            {"i": n["id"]},
        )
    r = owner.post(f"{BASE.format(t=t)}/{n['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nomination_closed"
    assert owner.get(BASE.format(t=t)).json() == []
    assert _status(t, n["id"]) == "expired"
    assert _roles(owner, t, nominee.user["id"]) == ["CONTRIBUTOR"]
    # the nominator is told
    kinds = [i["kind"] for i in admin.get(f"/trees/{t}/inbox").json()["items"]]
    assert "nomination_expired" in kinds


# ------------------------------------------------------------------ visibility and isolation
def test_only_admins_and_the_nominee_see_a_nomination(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    second_admin = member_factory(["FAMILY_ADMIN"], name="Second admin")
    bystander = member_factory(["CONTRIBUTOR"], name="Bystander")
    nid = _nominate(admin, t, mid, reason="PRIVATE-REASON").json()["id"]
    for who in (owner, admin, second_admin, nominee):
        assert [n["reason"] for n in who.get(BASE.format(t=t)).json()] == ["PRIVATE-REASON"]
    r = bystander.get(BASE.format(t=t))
    assert r.status_code == 200 and r.json() == []
    for step in ("accept", "decline", "approve", "reject", "withdraw"):
        r = bystander.post(f"{BASE.format(t=t)}/{nid}/{step}", json={})
        assert r.status_code == 404 and "PRIVATE-REASON" not in r.text and "Ravi" not in r.text
    # nor does the bystander's inbox mention it
    assert "Ravi" not in bystander.get(f"/trees/{t}/inbox").text


def test_cross_tree_ids_are_not_found(owner, tree, member_factory, make_client):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    # the same people in a second tree, where they hold the same roles
    other = new_tree(owner, "Sharma Family")
    from tests.conftest import join_tree

    join_tree(owner, admin, other["id"], ["FAMILY_ADMIN"])
    join_tree(owner, nominee, other["id"], ["CONTRIBUTOR"])
    o = other["id"]
    for who, step in (
        (nominee, "accept"),
        (nominee, "decline"),
        (owner, "approve"),
        (owner, "reject"),
        (admin, "withdraw"),
    ):
        r = who.post(f"{BASE.format(t=o)}/{nid}/{step}", json={})
        assert r.status_code == 404, (step, r.status_code)
    # a membership id from another tree cannot be nominated
    assert _nominate(admin, o, mid).status_code == 404
    assert owner.get(BASE.format(t=o)).json() == []
    assert _status(t, nid) == "open"


def test_notifications_tell_the_right_people(owner, tree, member_factory):
    t, admin, nominee, mid = _setup(owner, tree, member_factory)
    nid = _nominate(admin, t, mid).json()["id"]
    owner_note = owner.get(f"/trees/{t}/inbox").json()["items"][0]
    assert owner_note["kind"] == "nomination_created"
    assert owner_note["text"] == "Asha (admin) nominated Ravi (cousin) to be a family admin."
    mine = nominee.get(f"/trees/{t}/inbox").json()["items"][0]
    assert mine["text"] == "Asha (admin) nominated you to be a family admin."
    nominee.post(f"{BASE.format(t=t)}/{nid}/accept")
    assert admin.get(f"/trees/{t}/inbox").json()["items"][0]["kind"] == "nomination_accepted"
    owner.post(f"{BASE.format(t=t)}/{nid}/approve", json={})
    assert admin.get(f"/trees/{t}/inbox").json()["items"][0]["kind"] == "nomination_approved"
    assert (
        nominee.get(f"/trees/{t}/inbox").json()["items"][0]["text"]
        == "An owner approved the nomination of you to be a family admin."
    )
