"""ADR-0027 §1, §2, §10, §11: record audiences, content owners and who may change them.

``ONLY_ME`` and ``SELECTED_MEMBERS`` have no role-based visibility: the owner, admins, custodians,
reviewers and branch admins see nothing of someone else's private record unless they hold a grant.
"""

from __future__ import annotations

from typing import Any

from tests.conftest import join_tree, new_tree
from tests.doc_fixtures import png_bytes, text_image, text_pdf, upload
from tests.helpers import create_person, person_body

ROLES = [
    "OWNER",
    "FAMILY_ADMIN",
    "BRANCH_ADMIN",
    "DOCUMENT_CUSTODIAN",
    "PROPERTY_CUSTODIAN",
    "REVIEWER",
    "VIEWER",
]


def _png(label: str) -> bytes:
    return png_bytes(text_image([label], width=900))


def _doc(client: Any, t: str, label: str, **kw: Any) -> dict[str, Any]:
    r = upload(client, t, _png(label), mime="image/png", title=label, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def _vault(client: Any, t: str, label: str, **kw: Any) -> dict[str, Any]:
    r = upload(
        client,
        t,
        text_pdf([label]),
        filename="cert.pdf",
        mime="application/pdf",
        category="birth_certificate",
        title=label,
        **kw,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _grant(client: Any, t: str, user: Any, rtype: str, rid: str, perm: str = "view") -> Any:
    return client.post(
        f"/trees/{t}/grants",
        json={"user_id": user.user["id"], "resource_type": rtype, "resource_id": rid, "permission": perm},
    )


def _membership(owner: Any, t: str, user: Any) -> str:
    return next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == user.user["id"])


def _sees(client: Any, t: str, doc: dict[str, Any]) -> bool:
    """Every read path agrees: metadata, list, search and a download link."""
    meta = client.get(f"/trees/{t}/documents/{doc['id']}").status_code
    listed = doc["id"] in {d["id"] for d in client.get(f"/trees/{t}/documents").json()["items"]}
    url = client.post(f"/trees/{t}/documents/{doc['id']}/download-url").status_code
    assert (meta == 200) == listed == (url in (200, 201)), (meta, listed, url)
    return meta == 200


# ------------------------------------------------------------------ §1 no role-based visibility
def test_only_me_is_seen_by_its_owner_and_nobody_else(owner, tree, member_factory, make_client):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    photo = _doc(uploader, t, "Only me photo", privacy_level="ONLY_ME")
    assert photo["is_owner"] is True and photo["owner_membership_id"] == _membership(owner, t, uploader)
    assert _sees(uploader, t, photo)
    assert uploader.get(f"/trees/{t}/documents/{photo['id']}").json()["can_access_content"] is True
    branch = owner.post(f"/trees/{t}/branches", json={"name": "Pune branch"}).json()
    for role in ROLES[1:]:
        scope = branch["id"] if role == "BRANCH_ADMIN" else None
        assert not _sees(member_factory([role], branch_id=scope, name=role), t, photo), role
    assert not _sees(owner, t, photo)  # the tree owner too
    stranger = make_client()
    stranger.register(name="Stranger")
    assert stranger.get(f"/trees/{t}/documents/{photo['id']}").status_code == 404


def test_custodians_get_no_bytes_of_a_private_vault_document(owner, tree, member_factory):
    t = tree["id"]
    holder = member_factory(["CONTRIBUTOR", "DOCUMENT_CUSTODIAN"], name="Holder")
    cert = _vault(holder, t, "Birth certificate", privacy_level="SELECTED_MEMBERS")
    custodian = member_factory(["DOCUMENT_CUSTODIAN"], name="Custodian")
    assert custodian.get(f"/trees/{t}/documents/{cert['id']}").status_code == 404
    # a view grant shows the metadata, but a custodian role adds no vault bytes on a private record
    assert _grant(holder, t, custodian, "document", cert["id"]).status_code == 201
    got = custodian.get(f"/trees/{t}/documents/{cert['id']}").json()
    assert got["can_access_content"] is False
    assert custodian.post(f"/trees/{t}/documents/{cert['id']}/download-url").status_code == 403
    assert _grant(holder, t, custodian, "document", cert["id"], "download").status_code == 201
    assert custodian.post(f"/trees/{t}/documents/{cert['id']}/download-url").status_code == 200


def test_selected_members_are_chosen_by_the_owner_alone(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    chosen = member_factory(["VIEWER"], name="Chosen")
    other = member_factory(["VIEWER"], name="Other")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    doc = _doc(uploader, t, "Selected photo", privacy_level="SELECTED_MEMBERS")

    # the owner needs no privacy.manage to share their own record
    g = _grant(uploader, t, chosen, "document", doc["id"])
    assert g.status_code == 201, g.text
    assert _sees(chosen, t, doc) and not _sees(other, t, doc) and not _sees(admin, t, doc)
    assert [x["id"] for x in uploader.get(f"/trees/{t}/grants").json()] == [g.json()["id"]]

    # admins cannot see, list, add or revoke grants on someone else's private record
    assert g.json()["id"] not in {x["id"] for x in admin.get(f"/trees/{t}/grants").json()}
    assert _grant(admin, t, other, "document", doc["id"]).status_code == 404
    assert _grant(owner, t, other, "document", doc["id"]).status_code == 404
    assert admin.delete(f"/trees/{t}/grants/{g.json()['id']}").status_code == 404
    # a grantee changes nothing and shares nothing further
    assert chosen.patch(f"/trees/{t}/documents/{doc['id']}", json={"title": "x"}).status_code == 403
    assert chosen.delete(f"/trees/{t}/documents/{doc['id']}").status_code == 403
    assert _grant(chosen, t, other, "document", doc["id"]).status_code == 404
    assert chosen.get(f"/trees/{t}/records/document/{doc['id']}/sharing").status_code == 404

    sharing = uploader.get(f"/trees/{t}/records/document/{doc['id']}/sharing").json()
    assert sharing["privacy_level"] == "SELECTED_MEMBERS"
    assert [x["id"] for x in sharing["grants"]] == [g.json()["id"]]
    assert uploader.delete(f"/trees/{t}/grants/{g.json()['id']}").status_code == 200
    assert not _sees(chosen, t, doc)


def test_promotion_reveals_nothing(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "Private photo", privacy_level="ONLY_ME")
    viewer = member_factory(["VIEWER"], name="Later admin")
    mid = _membership(owner, t, viewer)
    assert owner.patch(f"/trees/{t}/members/{mid}", json={"roles": ["OWNER"]}).status_code == 200
    assert not _sees(viewer, t, doc)


def test_selected_branch_shares_with_one_branch(owner, tree, member_factory):
    t = tree["id"]
    pune = owner.post(f"/trees/{t}/branches", json={"name": "Pune branch"}).json()
    delhi = owner.post(f"/trees/{t}/branches", json={"name": "Delhi branch"}).json()
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "Pune wedding", privacy_level="FAMILY_BRANCH", audience_branch_id=pune["id"])
    assert doc["audience_branch_id"] == pune["id"]
    assert _sees(member_factory(["VIEWER"], branch_id=pune["id"], name="Pune"), t, doc)
    assert not _sees(member_factory(["VIEWER"], branch_id=delhi["id"], name="Delhi"), t, doc)
    assert not _sees(member_factory(["VIEWER"], name="No branch"), t, doc)
    assert _sees(member_factory(["FAMILY_ADMIN"], name="Admin"), t, doc)  # a shared audience
    other_tree = new_tree(owner, "Other")
    foreign = owner.post(f"/trees/{other_tree['id']}/branches", json={"name": "Elsewhere"}).json()
    r = upload(
        uploader,
        t,
        _png("Foreign"),
        mime="image/png",
        privacy_level="FAMILY_BRANCH",
        audience_branch_id=foreign["id"],
    )
    assert r.status_code == 404


# ------------------------------------------------------------------ §2 owners, orphans, transfer
def test_an_orphaned_private_record_stays_with_its_grantees(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    chosen = member_factory(["VIEWER"], name="Chosen")
    selected = _doc(uploader, t, "Selected", privacy_level="SELECTED_MEMBERS")
    only = _doc(uploader, t, "Only", privacy_level="ONLY_ME")
    assert _grant(uploader, t, chosen, "document", selected["id"]).status_code == 201
    assert owner.delete(f"/trees/{t}/members/{_membership(owner, t, uploader)}").status_code == 200
    assert _sees(chosen, t, selected)
    assert not _sees(owner, t, selected) and not _sees(owner, t, only)  # admins cannot claim them
    join_tree(owner, uploader, t, ["CONTRIBUTOR"])  # the same person, invited again
    assert not _sees(uploader, t, only) and not _sees(uploader, t, selected)


def test_ownership_is_offered_and_must_be_accepted(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    heir = member_factory(["VIEWER"], name="Heir")
    doc = _doc(uploader, t, "Heirloom", privacy_level="ONLY_ME")
    path = f"/trees/{t}/records/document/{doc['id']}/ownership-offer"

    assert heir.post(path, json={"user_id": heir.user["id"]}).status_code == 404  # not the owner
    assert owner.post(path, json={"user_id": owner.user["id"]}).status_code == 404
    stranger_tree = new_tree(owner, "Elsewhere")
    assert stranger_tree  # a non-member of this tree cannot be offered anything
    r = uploader.post(path, json={"user_id": heir.user["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["pending_owner_membership_id"] == _membership(owner, t, heir)
    assert not _sees(heir, t, doc)  # nothing changes until they accept
    assert heir.get(f"/trees/{t}/ownership-offers").json() == [
        {"resource_type": "document", "resource_id": doc["id"], "title": "Heirloom"}
    ]
    assert owner.post(f"{path}/accept").status_code == 404
    assert heir.post(f"{path}/accept").status_code == 200
    assert _sees(heir, t, doc) and not _sees(uploader, t, doc)
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []

    # declining and cancelling
    assert heir.post(path, json={"user_id": uploader.user["id"]}).status_code == 200
    assert uploader.delete(path).status_code == 200  # declined
    assert heir.post(f"{path}/accept").status_code == 404
    assert uploader.post(f"{path}/accept").status_code == 404
    assert _sees(heir, t, doc)


# ------------------------------------------------------------------ §10 who may change what
def test_the_uploader_can_make_their_own_document_more_private(owner, tree, member_factory):
    """A5: no document.manage needed to narrow, or widen, one's own document."""
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "Mine", privacy_level="TREE_MEMBERS")
    r = uploader.patch(f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "ONLY_ME"})
    assert r.status_code == 200, r.text
    r = uploader.patch(f"/trees/{t}/documents/{doc['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 200, r.text


def test_managers_only_narrow_shared_records(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    pune = owner.post(f"/trees/{t}/branches", json={"name": "Pune branch"}).json()
    doc = _doc(uploader, t, "Shared", privacy_level="TREE_MEMBERS")
    path = f"/trees/{t}/documents/{doc['id']}"
    assert (
        admin.patch(
            path, json={"privacy_level": "FAMILY_BRANCH", "audience_branch_id": pune["id"]}
        ).status_code
        == 200
    )
    assert admin.patch(path, json={"privacy_level": "TREE_MEMBERS"}).status_code == 403  # widening
    assert admin.patch(path, json={"audience_branch_id": None}).status_code == 403  # a different audience
    assert admin.patch(path, json={"privacy_level": "PRIVATE_TREE_ADMINS"}).status_code == 200
    assert uploader.patch(path, json={"privacy_level": "TREE_MEMBERS"}).status_code == 200

    legacy = _doc(uploader, t, "Legacy", privacy_level="CUSTOM")
    path = f"/trees/{t}/documents/{legacy['id']}"
    r = admin.patch(path, json={"privacy_level": "PRIVATE_TREE_ADMINS"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_content_owner"
    assert uploader.patch(path, json={"privacy_level": "SELECTED_MEMBERS"}).status_code == 200


def test_people_and_fields_refuse_the_record_only_levels(owner, tree):
    t = tree["id"]
    for level in ("ONLY_ME", "SELECTED_MEMBERS"):
        r = owner.post(f"/trees/{t}/people", json=person_body("Asha", privacy_level=level))
        assert r.status_code == 422, r.text
        assert owner.patch(f"/trees/{t}", json={"default_person_privacy": level}).status_code == 422
    p = create_person(owner, t, "Asha")
    assert (
        owner.put(f"/trees/{t}/people/{p['id']}/privacy", json={"privacy_level": "ONLY_ME"}).status_code
        == 422
    )
    r = owner.put(
        f"/trees/{t}/people/{p['id']}/privacy", json={"field_privacy": {"contact": "SELECTED_MEMBERS"}}
    )
    assert r.status_code == 422
    assert (
        owner.put(f"/trees/{t}/people/{p['id']}/privacy", json={"privacy_level": "TREE_MEMBERS"}).status_code
        == 200
    )


# ------------------------------------------------------------------ traditions
def _tradition(client: Any, t: str, **kw: Any) -> dict[str, Any]:
    r = client.post(
        f"/trees/{t}/traditions", json={"kind": "recipe", "title": "Gujiya", "body": "Khoya.", **kw}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_private_traditions(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    chosen = member_factory(["VIEWER"], name="Chosen")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    only = _tradition(author, t, privacy_level="ONLY_ME")
    selected = _tradition(author, t, privacy_level="SELECTED_MEMBERS")
    legacy = _tradition(author, t, privacy_level="PRIVATE_SELF")
    assert only["is_owner"] is True
    for who in (admin, owner, chosen):
        for e in (only, selected, legacy):
            assert who.get(f"/trees/{t}/traditions/{e['id']}").status_code == 404
    assert _grant(admin, t, chosen, "tradition", selected["id"]).status_code == 404
    assert _grant(author, t, chosen, "tradition", selected["id"]).status_code == 201
    assert chosen.get(f"/trees/{t}/traditions/{selected['id']}").status_code == 200
    listed = {e["id"] for e in chosen.get(f"/trees/{t}/traditions").json()["items"]}
    assert selected["id"] in listed and only["id"] not in listed
    got = chosen.get(f"/trees/{t}/traditions/{selected['id']}").json()
    assert got["can_edit"] is False and got["can_withdraw"] is False
    assert chosen.patch(f"/trees/{t}/traditions/{selected['id']}", json={"title": "x"}).status_code == 403
    assert chosen.delete(f"/trees/{t}/traditions/{selected['id']}").status_code == 403
    assert (
        author.patch(
            f"/trees/{t}/traditions/{only['id']}", json={"privacy_level": "TREE_MEMBERS"}
        ).status_code
        == 200
    )
    assert admin.get(f"/trees/{t}/traditions/{only['id']}").status_code == 200


def test_admins_only_narrow_a_shared_tradition(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    e = _tradition(author, t, privacy_level="TREE_MEMBERS")
    path = f"/trees/{t}/traditions/{e['id']}"
    assert admin.patch(path, json={"privacy_level": "PRIVATE_TREE_ADMINS"}).status_code == 200
    assert admin.patch(path, json={"privacy_level": "TREE_MEMBERS"}).status_code == 403


# ------------------------------------------------------------------ §11 audit, sources, consent
def test_the_audit_log_shows_someone_elses_private_record_only_as_opaque(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "Secret", privacy_level="ONLY_ME")
    shared = _doc(uploader, t, "Open", privacy_level="TREE_MEMBERS")
    events = owner.get(f"/trees/{t}/audit", params={"limit": 200}).json()["items"]
    assert all(e.get("target_id") != doc["id"] for e in events)
    assert any(e["action"] == "private_record" and e["target_id"] is None for e in events)
    assert any(e.get("target_id") == shared["id"] for e in events)
    mine = _doc(owner, t, "Owner's own", privacy_level="ONLY_ME")
    events = owner.get(f"/trees/{t}/audit", params={"limit": 200}).json()["items"]
    assert any(e.get("target_id") == mine["id"] for e in events)


def test_a_private_documents_source_follows_the_document(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "Letter", privacy_level="ONLY_ME")
    r = uploader.post(f"/trees/{t}/sources", json={"title": "Grandfather's letter", "document_id": doc["id"]})
    assert r.status_code == 201, r.text
    src = r.json()
    assert uploader.get(f"/trees/{t}/sources/{src['id']}").status_code == 200
    assert owner.get(f"/trees/{t}/sources/{src['id']}").status_code == 404


def test_consent_evidence_cannot_probe_for_a_hidden_document(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "Consent letter", privacy_level="ONLY_ME")
    p = create_person(owner, t, "Living", status="living")
    body = {
        "granted_by_name": "Living",
        "authority_basis": "self",
        "purpose": "Family history",
        "data_categories": ["names"],
        "evidence_document_id": doc["id"],
    }
    r = owner.post(f"/trees/{t}/people/{p['id']}/consents", json=body)
    assert r.status_code == 404, r.text  # the same answer as for a document that does not exist
