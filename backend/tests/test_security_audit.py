"""Security audit regression tests (2026-09-25).

Regression tests for the issues found in the security audit (SEC-1 … SEC-13). All are fixed; SEC-12
(account enumeration at registration) was closed by email verification (Phase 8).
Originally: every test here documented a CONFIRMED issue. Each was marked ``xfail(strict=True)``: it failed
(proving the bug) and will start "passing" — which strict xfail reports as a failure — once the
issue is fixed, at which point the marker should be removed so the test guards the fix.
"""

from __future__ import annotations

from typing import Any

from tests.conftest import join_tree
from tests.doc_fixtures import BIRTH_CERTIFICATE_LINES, text_pdf, upload
from tests.helpers import create_person, exact, link

# ------------------------------------------------------------------------------------ helpers


def _branch(owner: Any, t: str, name: str = "Madurai branch") -> str:
    r = owner.post(f"/trees/{t}/branches", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _my_membership_id(client: Any, t: str) -> str:
    r = client.get(f"/trees/{t}/members")
    assert r.status_code == 200, r.text
    return next(m["id"] for m in r.json() if m["user_id"] == client.user["id"])


# ------------------------------------------------------------------ SEC-1 branch scope bypass


def test_branch_scoped_contributor_pulls_outsider_into_branch_and_edits(owner, tree, make_client):
    t = tree["id"]
    branch_id = _branch(owner, t)
    outsider = create_person(owner, t, "Outsider")
    c = make_client()
    c.register()
    join_tree(owner, c, t, ["CONTRIBUTOR"], branch_id=branch_id)
    # baseline: outside the branch, writes are refused
    assert c.patch(f"/trees/{t}/people/{outsider['id']}", json={"occupation": "x"}).status_code == 403

    c.post(f"/trees/{t}/branches/{branch_id}/members", json={"person_ids": [outsider["id"]]})
    r = c.patch(f"/trees/{t}/people/{outsider['id']}", json={"occupation": "Forged"})
    assert r.status_code == 403


def test_branch_scoped_contributor_can_delete_any_household(owner, tree, make_client):
    t = tree["id"]
    branch_id = _branch(owner, t)
    other_branch = _branch(owner, t, "Other branch")
    h = owner.post(f"/trees/{t}/households", json={"name": "Other house", "branch_id": other_branch})
    assert h.status_code == 201, h.text
    c = make_client()
    c.register()
    join_tree(owner, c, t, ["CONTRIBUTOR"], branch_id=branch_id)
    assert c.delete(f"/trees/{t}/households/{h.json()['id']}").status_code == 403


# ------------------------------------------------ SEC-2 invitation merge drops branch scope


def test_branch_admin_invite_to_existing_member_grants_unscoped_write(
    owner, tree, make_client, member_factory
):
    t = tree["id"]
    branch_id = _branch(owner, t)
    outsider = create_person(owner, t, "Outsider")
    badmin = make_client()
    badmin.register()
    join_tree(owner, badmin, t, ["BRANCH_ADMIN"], branch_id=branch_id)
    viewer = member_factory(["VIEWER"], name="Existing viewer")  # unscoped membership

    inv = badmin.post(
        f"/trees/{t}/invitations",
        json={"email": viewer.user["email"], "roles": ["CONTRIBUTOR"], "branch_id": branch_id},
    )
    assert inv.status_code == 201, inv.text
    # the scoped invitation must not silently widen (or merge into) an unscoped membership
    assert viewer.post(f"/invitations/{inv.json()['token']}/accept").status_code == 409

    r = viewer.patch(f"/trees/{t}/people/{outsider['id']}", json={"occupation": "Forged"})
    assert r.status_code == 403


# --------------------------------------------- SEC-3 linked_person_id self-link = "self" view


def test_branch_admin_links_self_to_hidden_person(owner, tree, make_client):
    t = tree["id"]
    branch_id = _branch(owner, t)
    hidden = create_person(
        owner,
        t,
        "Hidden",
        status="living",
        privacy_level="PRIVATE_SELF",
        contact_info="+91 98765 43210",
        birth={"date": exact(1990, 4, 1)},
    )
    badmin = make_client()
    badmin.register()
    join_tree(owner, badmin, t, ["BRANCH_ADMIN"], branch_id=branch_id)
    assert badmin.get(f"/trees/{t}/people/{hidden['id']}").status_code == 404

    badmin.patch(
        f"/trees/{t}/members/{_my_membership_id(badmin, t)}", json={"linked_person_id": hidden["id"]}
    )
    r = badmin.get(f"/trees/{t}/people/{hidden['id']}")
    assert r.status_code == 404
    assert "98765" not in r.text


def test_member_list_leaks_hidden_linked_person_id(owner, tree, member_factory):
    t = tree["id"]
    hidden = create_person(owner, t, "HiddenSelf", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    linked = member_factory(["VIEWER"], name="Linked")
    owner.patch(f"/trees/{t}/members/{_my_membership_id(linked, t)}", json={"linked_person_id": hidden["id"]})
    viewer = member_factory(["VIEWER"], name="Nosy viewer")
    assert viewer.get(f"/trees/{t}/people/{hidden['id']}").status_code == 404
    assert hidden["id"] not in viewer.get(f"/trees/{t}/members").text


# -------------------------------------------------- SEC-4 family view leaks hidden partner


def test_family_view_leaks_hidden_partner_through_union(owner, tree, member_factory):
    t = tree["id"]
    visible = create_person(owner, t, "Visible", status="deceased")
    secret = create_person(owner, t, "SecretSpouse", status="living", privacy_level="PRIVATE_TREE_ADMINS")
    link(
        owner,
        t,
        visible["id"],
        secret["id"],
        "spouse",
        start_date=exact(2019, 11, 23),
        notes="Second marriage, kept quiet from the family",
    )
    viewer = member_factory(["VIEWER"])
    fam = viewer.get(f"/trees/{t}/people/{visible['id']}/family")
    assert fam.status_code == 200, fam.text
    assert fam.json()["unions"][0]["partner"]["hidden"] is True
    body = fam.text
    assert secret["id"] not in body
    assert "kept quiet" not in body
    assert "2019" not in body


# ----------------------------------------- SEC-5 source bound to a vault document it can't see


def test_contributor_source_hijacks_vault_document_extraction(owner, tree, member_factory):
    t = tree["id"]
    person = create_person(owner, t, "Aarav", "Sharma", status="living", birth={"date": exact(1985, 3, 12)})
    r = upload(
        owner,
        t,
        text_pdf(BIRTH_CERTIFICATE_LINES),
        filename="bc.pdf",
        mime="application/pdf",
        category="birth_certificate",
        title="Birth certificate",
        link_target_type="person",
        link_target_id=person["id"],
    )
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["storage_class"] == "VAULT" and doc["privacy_level"] == "PRIVATE_TREE_ADMINS"

    contributor = member_factory(["CONTRIBUTOR"])
    assert contributor.get(f"/trees/{t}/documents/{doc['id']}").status_code == 404
    src = contributor.post(
        f"/trees/{t}/sources",
        json={"title": "Innocent note", "document_id": doc["id"], "privacy_level": "TREE_MEMBERS"},
    )
    if src.status_code != 201:
        return  # fixed: the hidden document cannot be referenced
    props = {p["field"]: p for p in owner.get(f"/trees/{t}/documents/{doc['id']}/proposals").json()}
    rv = owner.post(
        f"/trees/{t}/extraction-proposals/{props['registration_number']['id']}/review",
        json={"action": "accept"},
    )
    assert rv.status_code == 200, rv.text
    leaked = contributor.get(f"/trees/{t}/sources/{src.json()['id']}")
    assert "B-1985-00432" not in leaked.text


# ---------------------------------------------------------------- SEC-6 PDF JavaScript filter


def test_pdf_javascript_filter_bypass(owner, tree):
    pdf = text_pdf(["Hello"], extra_catalog="/OpenAction << /S /J#61vaScript /JS(app.alert(1)) >> ")
    r = upload(owner, tree["id"], pdf, filename="x.pdf", mime="application/pdf", category="letter")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "unsafe_pdf"


def test_arbitrary_payload_accepted_as_mp4(owner, tree):
    payload = b"\x00\x00\x00\x18ftypisom" + b"<html><script>alert(document.domain)</script></html>" * 10
    r = upload(owner, tree["id"], payload, filename="clip.mp4", mime="video/mp4", category="video")
    assert r.status_code == 422, r.text


# ------------------------------------------------------ SEC-7 citation delete without target auth


def test_contributor_deletes_property_citation(owner, tree, member_factory):
    t = tree["id"]
    prop = owner.post(
        f"/trees/{t}/properties",
        json={"property_type": "agricultural_land", "display_name": "Khet", "privacy_level": "TREE_MEMBERS"},
    )
    assert prop.status_code == 201, prop.text
    src = owner.post(f"/trees/{t}/sources", json={"title": "Sale deed 1962"}).json()
    cite = owner.post(
        f"/trees/{t}/citations",
        json={"source_id": src["id"], "target_type": "property", "target_id": prop.json()["id"]},
    )
    assert cite.status_code == 201, cite.text
    contributor = member_factory(["CONTRIBUTOR"])  # property.read, no property.write
    assert contributor.patch(
        f"/trees/{t}/properties/{prop.json()['id']}", json={"display_name": "x"}
    ).status_code in (403, 404)
    assert contributor.delete(f"/trees/{t}/citations/{cite.json()['id']}").status_code in (403, 404)


# ------------------------------------------------------------------ SEC-8 researcher place edits


def test_researcher_can_rename_canonical_place(owner, tree, member_factory):
    t = tree["id"]
    place = owner.post(f"/trees/{t}/places", json={"canonical_name": "Lucknow"}).json()
    researcher = member_factory(["RESEARCHER"])
    r = researcher.patch(f"/trees/{t}/places/{place['id']}", json={"canonical_name": "Kanpur"})
    assert r.status_code == 403


# ----------------------------------------------------------- SEC-9 public union notes/provenance


def test_public_family_exposes_relationship_notes(owner, tree, client):
    t = tree["id"]
    owner.patch(f"/trees/{t}", json={"public_mode": "DECEASED_ONLY"})
    kw: dict[str, Any] = {"status": "deceased", "privacy_level": "PUBLIC_DECEASED_ONLY"}
    a = create_person(owner, t, "Ancestor", birth={"date": exact(1880, 1, 1)}, **kw)
    b = create_person(owner, t, "Spouse", birth={"date": exact(1885, 1, 1)}, **kw)
    link(owner, t, a["id"], b["id"], "spouse", notes="Family feud over the dowry land, see court file")
    r = client.get(f"/public/trees/{tree['slug']}/people/{a['id']}/family")
    assert r.status_code == 200, r.text
    assert "dowry" not in r.text


# ------------------------------------------------------ SEC-10 duplicate-upload existence oracle


def test_duplicate_upload_reveals_hidden_document(owner, tree, member_factory):
    t = tree["id"]
    data = text_pdf(["Last will and testament of Ram Prasad"])
    r = upload(owner, t, data, filename="will.pdf", mime="application/pdf", category="will", title="Will")
    assert r.status_code == 201, r.text
    contributor = member_factory(["CONTRIBUTOR"])
    assert contributor.get(f"/trees/{t}/documents/{r.json()['id']}").status_code == 404
    probe = upload(
        contributor, t, data, filename="guess.pdf", mime="application/pdf", category="letter", title="x"
    )
    assert probe.status_code != 409, probe.text


# --------------------------------------------------------------- SEC-11 incomplete erasure


def test_erasure_keeps_preserved_gedcom_payload(owner, tree):
    t = tree["id"]
    ged = (
        "0 HEAD\n1 GEDC\n2 VERS 7.0\n1 SCHMA\n2 TAG _ADDRX https://example.org/addr\n"
        "0 @I1@ INDI\n1 NAME Ramesh /Sharma/\n1 SEX M\n1 DEAT Y\n"
        "1 _ADDRX 14 Secret Lane, Varanasi\n0 TRLR\n"
    )
    up = owner.post(
        f"/trees/{t}/imports", files={"file": ("f.ged", ged.encode(), "application/octet-stream")}
    )
    assert up.status_code == 201 and up.json()["status"] == "ready", up.text
    assert (
        owner.post(f"/trees/{t}/imports/{up.json()['id']}/commit", json={"decisions": {}}).status_code == 200
    )
    pid = owner.get(f"/trees/{t}/people", params={"q": "Ramesh"}).json()["items"][0]["id"]
    before = owner.get(f"/trees/{t}/exports/gedcom?exclude_living=false&include_sensitive=true").text
    assert "Secret Lane" in before

    r = owner.post(f"/trees/{t}/people/{pid}/erase", json={"reason": "subject request", "confirm": True})
    assert r.status_code == 200, r.text
    after = owner.get(f"/trees/{t}/exports/gedcom?exclude_living=false&include_sensitive=true").text
    assert "Secret Lane" not in after


# ------------------------------------------------------------------ SEC-12 account enumeration


def test_registration_does_not_enumerate_accounts(owner, make_client):
    """SEC-12 (fixed): an existing and a new email get the same status and body."""
    taken = make_client().post(
        "/auth/register",
        json={"email": owner.user["email"], "password": "another good password", "display_name": "X"},
    )
    fresh = make_client().post(
        "/auth/register",
        json={"email": "brand-new@example.com", "password": "another good password", "display_name": "X"},
    )
    assert taken.status_code == fresh.status_code == 202
    assert taken.json() == fresh.json()
    assert "vsh_session" not in taken.cookies and "vsh_session" not in fresh.cookies


# ------------------------------------------------------------------------ SEC-13 audit gap


def test_reading_vault_proposals_is_not_audited(owner, tree):
    t = tree["id"]
    person = create_person(owner, t, "Aarav", "Sharma", status="living")
    r = upload(
        owner,
        t,
        text_pdf(BIRTH_CERTIFICATE_LINES),
        filename="bc.pdf",
        mime="application/pdf",
        category="birth_certificate",
        title="Birth certificate",
        link_target_type="person",
        link_target_id=person["id"],
    )
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    props = owner.get(f"/trees/{t}/documents/{doc_id}/proposals")
    assert "B-1985-00432" in props.text
    events = owner.get(f"/trees/{t}/audit", params={"limit": 200}).json()["items"]
    reads = [e for e in events if e["target_id"] == doc_id and "proposal" in e["action"]]
    assert reads, [e["action"] for e in events if e["target_id"] == doc_id]
