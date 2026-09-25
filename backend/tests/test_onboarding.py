"""ADR-0011: family-data attestation and shareable (WhatsApp) claim invites."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text

from app.core.db import get_engine
from tests.conftest import attest, join_tree, owner_session
from tests.helpers import create_person, exact, person_body

GEDCOM = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Ravi /Iyer/\n0 TRLR\n"


def _statement(client: Any, kind: str, lang: str = "en") -> dict[str, Any]:
    r = client.get(f"/consent-statements/{kind}?lang={lang}")
    assert r.status_code == 200, r.text
    return r.json()


def _living(client: Any, tree_id: str, given: str = "Meera", **kw: Any) -> dict[str, Any]:
    return create_person(client, tree_id, given, status="living", **kw)


def _invite(client: Any, tree_id: str, person_id: str, role: str = "VIEWER") -> Any:
    return client.post(f"/trees/{tree_id}/people/{person_id}/claim-invites", json={"offered_role": role})


def _accept(client: Any, token: str, **overrides: Any) -> Any:
    stmt = _statement(client, "profile_claim")
    body = {"consent_version": stmt["version"], "language": "en", "confirm_adult": True, **overrides}
    return client.post(f"/claim-invites/{token}/accept", json=body)


def _relative(make_client: Any, name: str = "Meera Iyer") -> Any:
    c = make_client()
    c.register(name=name)
    return c


# ------------------------------------------------------------------ attestation
def test_statement_is_the_agreed_plain_language_text(owner):
    s = _statement(owner, "family_data")
    assert s["text"] == (
        "I agree to add my family members' names to this private tree, and I confirm I have their "
        "permission to do so."
    )
    hi = _statement(owner, "family_data", "hi")
    assert hi["language"] == "hi" and hi["version"] == s["version"] and "अनुमति" in hi["text"]
    # unknown languages fall back to English rather than showing nothing
    assert _statement(owner, "family_data", "xx")["language"] == "en"


def test_statement_requires_login(client):
    assert client.get("/consent-statements/family_data").status_code == 401


def test_adding_people_requires_attestation(owner):
    t = owner.post("/trees", json={"name": "Fresh"}).json()["id"]
    status = owner.get(f"/trees/{t}/attestation").json()
    assert status["attested"] is False and status["attestation"] is None

    r = owner.post(f"/trees/{t}/people", json=person_body("Ravi"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "attestation_required"

    row = attest(owner, t)
    assert row["withdrawn_at"] is None
    assert owner.get(f"/trees/{t}/attestation").json()["attested"] is True
    assert owner.post(f"/trees/{t}/people", json=person_body("Ravi")).status_code == 201
    # attesting again is idempotent
    assert attest(owner, t)["id"] == row["id"]


def test_add_relative_and_gedcom_import_also_require_attestation(owner, tree, make_client):
    t = tree["id"]
    anchor = create_person(owner, t, "Anchor")
    other = create_person(owner, t, "Other")
    contrib = make_client()
    contrib.register()
    join_tree(owner, contrib, t, ["CONTRIBUTOR"], attested=False)

    r = contrib.post(
        f"/trees/{t}/people/{anchor['id']}/relatives",
        json={"relation": "child", "new_person": person_body("Kid")},
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "attestation_required"
    # linking two people already in the tree adds nobody, so it needs no attestation
    r = contrib.post(
        f"/trees/{t}/people/{anchor['id']}/relatives",
        json={"relation": "sibling", "existing_person_id": other["id"]},
    )
    assert r.status_code == 201, r.text

    admin = make_client()
    admin.register()
    join_tree(owner, admin, t, ["FAMILY_ADMIN"], attested=False)
    r = admin.post(f"/trees/{t}/imports", files={"file": ("f.ged", GEDCOM.encode(), "text/plain")})
    assert r.status_code == 403 and r.json()["error"]["code"] == "attestation_required"
    attest(admin, t)
    r = admin.post(f"/trees/{t}/imports", files={"file": ("f.ged", GEDCOM.encode(), "text/plain")})
    assert r.status_code == 201, r.text


def test_attestation_is_per_user_and_per_tree(owner, tree, make_client):
    # the owner's confirmation does not cover another contributor
    contrib = make_client()
    contrib.register()
    join_tree(owner, contrib, tree["id"], ["CONTRIBUTOR"], attested=False)
    r = contrib.post(f"/trees/{tree['id']}/people", json=person_body("X"))
    assert r.json()["error"]["code"] == "attestation_required"
    # nor another tree of the same owner
    t2 = owner.post("/trees", json={"name": "Second"}).json()["id"]
    r = owner.post(f"/trees/{t2}/people", json=person_body("X"))
    assert r.json()["error"]["code"] == "attestation_required"


def test_attestation_rejects_stale_or_unknown_wording(owner):
    t = owner.post("/trees", json={"name": "Fresh"}).json()["id"]
    r = owner.post(f"/trees/{t}/attestation", json={"statement_version": "2020-01-v0", "language": "en"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "statement_outdated"
    version = _statement(owner, "family_data")["version"]
    r = owner.post(f"/trees/{t}/attestation", json={"statement_version": version, "language": "fr"})
    assert r.status_code == 422
    assert owner.get(f"/trees/{t}/attestation").json()["attested"] is False


def test_attestation_withdrawal_blocks_new_people_and_is_audited(owner, tree):
    t = tree["id"]
    r = owner.post(f"/trees/{t}/attestation/withdraw")
    assert r.status_code == 200 and r.json()["withdrawn_at"]
    assert owner.post(f"/trees/{t}/attestation/withdraw").status_code == 409
    assert owner.post(f"/trees/{t}/people", json=person_body("X")).status_code == 403
    actions = [e["action"] for e in owner.get(f"/trees/{t}/audit").json()["items"]]
    assert "attestation.accepted" in actions and "attestation.withdrawn" in actions


def test_attestation_is_stored_with_hash_and_request_info(owner, tree):
    import hashlib

    with owner_session() as db:  # the app role sees nothing without a tree bound (RLS)
        row = db.execute(
            text("SELECT statement_sha256, user_agent FROM family_data_attestation WHERE tree_id = :t"),
            {"t": tree["id"]},
        ).one()
    expected = hashlib.sha256(_statement(owner, "family_data")["text"].encode()).hexdigest()
    assert row.statement_sha256 == expected
    assert row.user_agent


def test_non_member_cannot_attest_or_read_attestation(owner, tree, make_client):
    stranger = make_client()
    stranger.register()
    v = _statement(stranger, "family_data")["version"]
    assert stranger.get(f"/trees/{tree['id']}/attestation").status_code == 404
    r = stranger.post(f"/trees/{tree['id']}/attestation", json={"statement_version": v, "language": "en"})
    assert r.status_code == 404


# ------------------------------------------------------------------ claim invites
def test_claim_invite_happy_path(owner, tree, make_client):
    t = tree["id"]
    meera = _living(owner, t)
    r = _invite(owner, t, meera["id"])
    assert r.status_code == 201, r.text
    inv = r.json()
    # the token lives in the URL fragment only (never sent to servers, logs or link previews)
    prefix, _, fragment = inv["url"].partition("#")
    assert prefix.endswith("/claim") and fragment == inv["token"] and inv["token"] not in prefix
    assert inv["state"] == "active" and inv["offered_role"] == "VIEWER"

    rel = _relative(make_client)
    preview = rel.get(f"/claim-invites/{inv['token']}")
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert p["tree_name"] == "Iyer Family" and p["person_name"] == "Meera Iyer"
    assert p["invited_by"] == "Tree Owner" and p["state"] == "active"
    # the preview holds names only: no dates, ids or other people
    assert set(p) == {
        "tree_name",
        "person_name",
        "invited_by",
        "offered_role",
        "expires_at",
        "state",
        "claim_id",
    }

    r = _accept(rel, inv["token"], message="It's me")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "requested"

    # a pending claim gives no access at all
    assert rel.get(f"/trees/{t}").status_code == 404
    assert rel.get(f"/trees/{t}/people/{meera['id']}").status_code == 404
    assert rel.get("/trees").json() == []

    claims = owner.get(f"/trees/{t}/claims").json()
    assert len(claims) == 1
    c = claims[0]
    assert c["via_invite"] is True and c["claimant_name"] == "Meera Iyer"
    assert c["claimant_email"] == rel.user["email"]
    r = owner.post(f"/trees/{t}/claims/{c['id']}/approve", json={})
    assert r.status_code == 200, r.text

    mine = rel.get("/trees").json()
    assert len(mine) == 1 and mine[0]["my_roles"] == ["VIEWER"]
    assert mine[0]["my_linked_person_id"] == meera["id"]
    person = rel.get(f"/trees/{t}/people/{meera['id']}").json()
    assert person["claimed_by_user_id"] == rel.user["id"]
    # the relative's own consent is now in the ledger, and they manage it
    consents = rel.get(f"/trees/{t}/people/{meera['id']}/consents").json()
    assert len(consents) == 1
    assert consents[0]["authority_basis"] == "self" and consents[0]["granted_by_user_id"] == rel.user["id"]
    # the viewer role really is read-only
    assert rel.post(f"/trees/{t}/people", json=person_body("X")).status_code == 403
    assert owner.get(f"/trees/{t}/claim-invites").json()[0]["state"] == "used"


def test_admin_can_offer_contributor_role(owner, tree, make_client):
    t = tree["id"]
    meera = _living(owner, t)
    inv = _invite(owner, t, meera["id"], "CONTRIBUTOR").json()
    rel = _relative(make_client)
    assert _accept(rel, inv["token"]).status_code == 201
    claim = owner.get(f"/trees/{t}/claims").json()[0]
    owner.post(f"/trees/{t}/claims/{claim['id']}/approve", json={})
    assert rel.get(f"/trees/{t}").json()["my_roles"] == ["CONTRIBUTOR"]


def test_rejected_claim_gives_no_access(owner, tree, make_client):
    t = tree["id"]
    meera = _living(owner, t)
    inv = _invite(owner, t, meera["id"]).json()
    rel = _relative(make_client)
    _accept(rel, inv["token"])
    claim = owner.get(f"/trees/{t}/claims").json()[0]
    assert owner.post(f"/trees/{t}/claims/{claim['id']}/reject", json={"note": "not her"}).status_code == 200
    assert rel.get(f"/trees/{t}").status_code == 404
    assert rel.get("/trees").json() == []
    assert owner.get(f"/trees/{t}/people/{meera['id']}").json()["claimed_by_user_id"] is None


def test_invite_is_single_use_and_leaks_nothing_once_used(owner, tree, make_client):
    t = tree["id"]
    inv = _invite(owner, t, _living(owner, t)["id"]).json()
    first = _relative(make_client)
    assert _accept(first, inv["token"]).status_code == 201
    # the same person can re-open their link to see it is pending
    assert first.get(f"/claim-invites/{inv['token']}").json()["state"] == "used"
    assert _accept(first, inv["token"]).status_code == 409

    forwarded = _relative(make_client, "Someone Else")
    r = forwarded.get(f"/claim-invites/{inv['token']}")
    assert r.status_code == 410 and r.json()["error"]["code"] == "invite_used"
    assert "Meera" not in r.text and "Iyer Family" not in r.text
    assert _accept(forwarded, inv["token"]).status_code == 410


def test_expired_and_revoked_invites(owner, tree, make_client):
    t = tree["id"]
    meera = _living(owner, t)
    expired = _invite(owner, t, meera["id"]).json()
    with get_engine().begin() as c:
        c.execute(
            text("UPDATE profile_claim_invite SET expires_at = :e WHERE id = :i"),
            {"e": dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1), "i": expired["id"]},
        )
    rel = _relative(make_client)
    r = rel.get(f"/claim-invites/{expired['token']}")
    assert r.status_code == 410 and r.json()["error"]["code"] == "invite_expired" and "Meera" not in r.text
    assert _accept(rel, expired["token"]).status_code == 410

    revoked = _invite(owner, t, meera["id"]).json()
    assert owner.delete(f"/trees/{t}/claim-invites/{revoked['id']}").status_code == 200
    assert rel.get(f"/claim-invites/{revoked['token']}").status_code == 404
    assert _accept(rel, revoked["token"]).status_code == 404
    assert rel.get("/claim-invites/not-a-real-token").status_code == 404


def test_accept_requires_consent_and_adult_confirmation(owner, tree, make_client):
    t = tree["id"]
    inv = _invite(owner, t, _living(owner, t)["id"]).json()
    rel = _relative(make_client)
    r = _accept(rel, inv["token"], confirm_adult=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "adult_required"
    r = _accept(rel, inv["token"], consent_version="old")
    assert r.status_code == 409 and r.json()["error"]["code"] == "statement_outdated"
    # failed attempts did not use the invite up
    assert rel.get(f"/claim-invites/{inv['token']}").json()["state"] == "active"
    assert _accept(rel, inv["token"]).status_code == 201


def test_invite_link_needs_a_signed_in_account(owner, tree, client):
    inv = _invite(owner, tree["id"], _living(owner, tree["id"])["id"]).json()
    assert client.get(f"/claim-invites/{inv['token']}").status_code == 401
    assert client.post(f"/claim-invites/{inv['token']}/accept", json={}).status_code == 401


def test_cannot_invite_for_deceased_minor_or_claimed_profiles(owner, tree, make_client):
    t = tree["id"]
    dead = create_person(owner, t, "Ancestor")
    r = _invite(owner, t, dead["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_living"
    this_year = dt.date.today().year
    child = _living(owner, t, "Chotu", birth={"date": exact(this_year - 8, 1, 1)})
    r = _invite(owner, t, child["id"])
    assert r.status_code == 422 and r.json()["error"]["code"] == "minor_profile"

    meera = _living(owner, t)
    inv = _invite(owner, t, meera["id"]).json()
    rel = _relative(make_client)
    _accept(rel, inv["token"])
    claim = owner.get(f"/trees/{t}/claims").json()[0]
    owner.post(f"/trees/{t}/claims/{claim['id']}/approve", json={})
    r = _invite(owner, t, meera["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_claimed"


def test_one_claimed_profile_per_user_per_tree(owner, tree, make_client):
    t = tree["id"]
    a = _invite(owner, t, _living(owner, t, "Asha")["id"]).json()
    b = _invite(owner, t, _living(owner, t, "Bela")["id"]).json()
    rel = _relative(make_client)
    _accept(rel, a["token"])
    claim = owner.get(f"/trees/{t}/claims").json()[0]
    owner.post(f"/trees/{t}/claims/{claim['id']}/approve", json={})
    r = _accept(rel, b["token"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_linked"


def test_invite_permissions(owner, tree, member_factory, make_client):
    t = tree["id"]
    meera = _living(owner, t)
    viewer = member_factory(["VIEWER"])
    assert _invite(viewer, t, meera["id"]).status_code == 403
    contrib = member_factory(["CONTRIBUTOR"])
    # contributors may invite, but only as viewers (no privilege escalation through the link)
    r = _invite(contrib, t, meera["id"], "CONTRIBUTOR")
    assert r.status_code == 403
    assert _invite(contrib, t, meera["id"], "OWNER").status_code == 422
    mine = _invite(contrib, t, meera["id"]).json()
    theirs = _invite(owner, t, meera["id"]).json()
    # contributors see and revoke only their own invites; admins see all
    assert [i["id"] for i in contrib.get(f"/trees/{t}/claim-invites").json()] == [mine["id"]]
    assert len(owner.get(f"/trees/{t}/claim-invites").json()) == 2
    assert contrib.delete(f"/trees/{t}/claim-invites/{theirs['id']}").status_code == 404
    assert contrib.delete(f"/trees/{t}/claim-invites/{mine['id']}").status_code == 200
    # a contributor cannot read the claim queue's claimant details
    assert contrib.get(f"/trees/{t}/claims").json() == []


def test_hidden_person_cannot_be_invited(owner, tree, member_factory):
    t = tree["id"]
    secret = create_person(owner, t, "Hidden", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    contrib = member_factory(["CONTRIBUTOR"])
    assert _invite(contrib, t, secret["id"]).status_code == 404
    # and invites for people the member cannot see are not listed to them
    _invite(owner, t, secret["id"])
    assert contrib.get(f"/trees/{t}/claim-invites").json() == []


def test_claim_invites_are_tree_isolated(owner, tree, make_client):
    t = tree["id"]
    meera = _living(owner, t)
    inv = _invite(owner, t, meera["id"]).json()
    other = make_client()
    other.register()
    tb = other.post("/trees", json={"name": "B"}).json()["id"]
    # tree A's person through tree B's URL, and tree A's invite through tree B
    assert _invite(other, tb, meera["id"]).status_code == 404
    assert other.delete(f"/trees/{tb}/claim-invites/{inv['id']}").status_code == 404
    assert other.delete(f"/trees/{t}/claim-invites/{inv['id']}").status_code == 404
    assert other.get(f"/trees/{t}/claim-invites").status_code == 404


def test_approval_keeps_an_existing_members_roles(owner, tree, member_factory):
    t = tree["id"]
    meera = _living(owner, t)
    inv = _invite(owner, t, meera["id"], "CONTRIBUTOR").json()
    viewer = member_factory(["VIEWER"])
    _accept(viewer, inv["token"])
    claim = owner.get(f"/trees/{t}/claims").json()[0]
    owner.post(f"/trees/{t}/claims/{claim['id']}/approve", json={})
    # the link offered CONTRIBUTOR, but an existing membership is never widened by a claim
    assert viewer.get(f"/trees/{t}").json()["my_roles"] == ["VIEWER"]


def test_branch_scoped_inviter_cannot_widen_scope(owner, tree, member_factory, make_client):
    t = tree["id"]
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Chennai branch"}).json()
    meera = _living(owner, t, branch_ids=[branch["id"]])
    badmin = member_factory(["BRANCH_ADMIN"], branch_id=branch["id"])
    r = _invite(badmin, t, meera["id"])
    assert r.status_code == 201, r.text
    rel = _relative(make_client)
    _accept(rel, r.json()["token"])
    claim = owner.get(f"/trees/{t}/claims").json()[0]
    owner.post(f"/trees/{t}/claims/{claim['id']}/approve", json={})
    assert rel.get(f"/trees/{t}").json()["my_branch_id"] == branch["id"]


def test_erasure_revokes_outstanding_invites(owner, tree, make_client):
    t = tree["id"]
    meera = _living(owner, t)
    inv = _invite(owner, t, meera["id"]).json()
    r = owner.post(f"/trees/{t}/people/{meera['id']}/erase", json={"reason": "DPDP request", "confirm": True})
    assert r.status_code == 200, r.text
    rel = _relative(make_client)
    assert rel.get(f"/claim-invites/{inv['token']}").status_code == 404


def test_invite_creation_and_claims_are_audited_without_tokens(owner, tree, make_client):
    t = tree["id"]
    inv = _invite(owner, t, _living(owner, t)["id"]).json()
    _accept(_relative(make_client), inv["token"])
    events = owner.get(f"/trees/{t}/audit").json()["items"]
    actions = [e["action"] for e in events]
    assert "profile.claim_invite_created" in actions and "profile.claim_requested" in actions
    assert inv["token"] not in str(events)
    with get_engine().connect() as c:
        stored = c.execute(text("SELECT token_hash FROM profile_claim_invite")).scalar_one()
    assert stored != inv["token"] and len(stored) == 64
