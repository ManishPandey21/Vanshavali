"""ADR-0027 for what the document work left out: private traditions, ownership transfer, and the
remaining paths that could reveal a private record (renders, consent evidence, proposals)."""

from __future__ import annotations

from typing import Any

from tests.conftest import join_tree, new_tree
from tests.doc_fixtures import png_bytes, text_image, upload
from tests.helpers import create_person

_n = 0


def _png() -> bytes:
    global _n
    _n += 1
    return png_bytes(text_image([f"Ownership test photo {_n}"], width=420))


def _doc(client: Any, t: str, level: str, title: str = "Heirloom") -> dict[str, Any]:
    r = upload(client, t, _png(), mime="image/png", title=title, privacy_level=level)
    assert r.status_code == 201, r.text
    return r.json()


def _tradition(client: Any, t: str, **kw: Any) -> dict[str, Any]:
    r = client.post(
        f"/trees/{t}/traditions", json={"kind": "recipe", "title": "Gujiya", "body": "Khoya.", **kw}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _grant(client: Any, t: str, user: Any, rtype: str, rid: str) -> Any:
    return client.post(
        f"/trees/{t}/grants",
        json={"user_id": user.user["id"], "resource_type": rtype, "resource_id": rid, "permission": "view"},
    )


def _mid(owner: Any, t: str, client: Any) -> str:
    return next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == client.user["id"])


def _reads(client: Any, t: str, e: dict[str, Any]) -> bool:
    one = client.get(f"/trees/{t}/traditions/{e['id']}").status_code
    listed = e["id"] in {i["id"] for i in client.get(f"/trees/{t}/traditions").json()["items"]}
    assert (one == 200) == listed, (one, listed)
    return one == 200


def _sees_doc(client: Any, t: str, d: dict[str, Any]) -> bool:
    return client.get(f"/trees/{t}/documents/{d['id']}").status_code == 200


# ------------------------------------------------------------------ private traditions
def test_private_traditions_are_seen_by_their_owner_and_grantees_only(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    chosen = member_factory(["VIEWER"], name="Chosen")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    only = _tradition(author, t, privacy_level="ONLY_ME")
    selected = _tradition(author, t, privacy_level="SELECTED_MEMBERS")
    legacy = _tradition(author, t, privacy_level="PRIVATE_SELF")
    assert only["is_owner"] is True and only["owner_membership_id"] == _mid(owner, t, author)
    for e in (only, selected, legacy):
        assert _reads(author, t, e)
        for who in (admin, owner, chosen):
            assert not _reads(who, t, e)

    # the owner shares without privacy.manage; admins cannot see, add or list such grants
    assert _grant(admin, t, chosen, "tradition", selected["id"]).status_code == 404
    g = _grant(author, t, chosen, "tradition", selected["id"])
    assert g.status_code == 201, g.text
    assert _reads(chosen, t, selected) and not _reads(admin, t, selected)
    assert g.json()["id"] in {x["id"] for x in author.get(f"/trees/{t}/grants").json()}
    assert g.json()["id"] not in {x["id"] for x in admin.get(f"/trees/{t}/grants").json()}
    r = _grant(author, t, chosen, "tradition", only["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "only_me_record"

    # a grantee reads but changes nothing
    got = chosen.get(f"/trees/{t}/traditions/{selected['id']}").json()
    assert got["can_edit"] is False and got["can_withdraw"] is False
    assert chosen.patch(f"/trees/{t}/traditions/{selected['id']}", json={"title": "x"}).status_code == 403
    assert chosen.delete(f"/trees/{t}/traditions/{selected['id']}").status_code == 403

    # the owner opens it up again
    r = author.patch(f"/trees/{t}/traditions/{only['id']}", json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 200, r.text
    assert _reads(admin, t, only)


def test_promotion_reveals_no_private_tradition(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    e = _tradition(author, t, privacy_level="ONLY_ME")
    later = member_factory(["VIEWER"], name="Later owner")
    assert (
        owner.patch(f"/trees/{t}/members/{_mid(owner, t, later)}", json={"roles": ["OWNER"]}).status_code
        == 200
    )
    assert not _reads(later, t, e)


def test_admins_only_narrow_a_shared_tradition(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    e = _tradition(author, t, privacy_level="TREE_MEMBERS")
    path = f"/trees/{t}/traditions/{e['id']}"
    assert admin.patch(path, json={"privacy_level": "PRIVATE_TREE_ADMINS"}).status_code == 200
    r = admin.patch(path, json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_content_owner"
    legacy = _tradition(author, t, privacy_level="CUSTOM")
    assert (
        admin.patch(
            f"/trees/{t}/traditions/{legacy['id']}", json={"privacy_level": "PRIVATE_TREE_ADMINS"}
        ).status_code
        == 403
    )
    assert (
        author.patch(
            f"/trees/{t}/traditions/{legacy['id']}", json={"privacy_level": "SELECTED_MEMBERS"}
        ).status_code
        == 200
    )


def test_people_still_refuse_record_only_levels(owner, tree):
    p = create_person(owner, tree["id"], "Asha")
    r = owner.put(f"/trees/{tree['id']}/people/{p['id']}/privacy", json={"privacy_level": "ONLY_ME"})
    assert r.status_code == 422


def test_audit_log_hides_someone_elses_private_tradition(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    hidden = _tradition(author, t, privacy_level="ONLY_ME")
    shared = _tradition(author, t, privacy_level="TREE_MEMBERS", title="Holi")
    events = owner.get(f"/trees/{t}/audit", params={"limit": 200}).json()["items"]
    assert all(e.get("target_id") != hidden["id"] for e in events)
    assert any(e["target_type"] == "private_record" and e["target_id"] is None for e in events)
    assert any(e.get("target_id") == shared["id"] for e in events)


def test_a_proposal_on_a_tradition_made_private_is_hidden_from_reviewers(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    cousin = member_factory(["CONTRIBUTOR"], name="Cousin")
    e = _tradition(author, t, privacy_level="TREE_MEMBERS", title="Holi")
    assert owner.put(f"/trees/{t}/review-policy", json={"review_policy": "all"}).status_code == 200
    prop = cousin.post(
        f"/trees/{t}/proposals",
        json={
            "rationale": "Colours from dawn",
            "items": [
                {"target_type": "tradition", "op": "update", "target_id": e["id"], "patch": {"body": "Dawn."}}
            ],
            "submit": True,
        },
    )
    assert prop.status_code == 201, prop.text
    pid = prop.json()["id"]
    assert owner.get(f"/trees/{t}/proposals/{pid}").status_code == 200
    assert (
        author.patch(f"/trees/{t}/traditions/{e['id']}", json={"privacy_level": "ONLY_ME"}).status_code == 200
    )
    assert owner.get(f"/trees/{t}/proposals/{pid}").status_code == 404
    listed = {
        p["id"] for p in owner.get(f"/trees/{t}/proposals", params={"view": "to_review"}).json()["items"]
    }
    assert pid not in listed
    assert cousin.get(f"/trees/{t}/proposals/{pid}").status_code == 404  # the proposer lost access too


# ------------------------------------------------------------------ ownership transfer (§2)
def test_ownership_is_offered_and_must_be_accepted(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    heir = member_factory(["VIEWER"], name="Heir")
    doc = _doc(uploader, t, "ONLY_ME")
    path = f"/trees/{t}/records/document/{doc['id']}/ownership-offer"

    assert heir.post(path, json={"user_id": heir.user["id"]}).status_code == 404  # not the owner
    assert owner.post(path, json={"user_id": owner.user["id"]}).status_code == 404  # nor is the tree owner
    stranger_tree = new_tree(owner, "Elsewhere")
    stranger = member_factory(["VIEWER"], name="Stranger")
    owner.delete(f"/trees/{t}/members/{_mid(owner, t, stranger)}")
    join_tree(owner, stranger, stranger_tree["id"], ["VIEWER"])
    assert uploader.post(path, json={"user_id": stranger.user["id"]}).status_code == 404  # not a member here
    assert uploader.post(path, json={"user_id": uploader.user["id"]}).status_code == 422

    r = uploader.post(path, json={"user_id": heir.user["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["pending_owner_membership_id"] == _mid(owner, t, heir)
    assert not _sees_doc(heir, t, doc)  # nothing changes until they accept
    assert heir.get(f"/trees/{t}/ownership-offers").json() == [
        {"resource_type": "document", "resource_id": doc["id"], "title": "Heirloom"}
    ]
    assert owner.post(f"{path}/accept").status_code == 404
    r = heir.post(f"{path}/accept")
    assert r.status_code == 200 and r.json()["owner_membership_id"] == _mid(owner, t, heir)
    assert _sees_doc(heir, t, doc) and not _sees_doc(uploader, t, doc)
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []

    # the new owner offers it back; the uploader declines
    assert heir.post(path, json={"user_id": uploader.user["id"]}).status_code == 200
    assert uploader.delete(path).status_code == 200
    assert uploader.post(f"{path}/accept").status_code == 404
    events = owner.get(f"/trees/{t}/audit", params={"limit": 200}).json()["items"]
    assert all(e.get("target_id") != doc["id"] for e in events)  # still private to the tree owner


def test_transferring_a_tradition_and_cancelling_an_offer(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    e = _tradition(author, t, privacy_level="ONLY_ME")
    path = f"/trees/{t}/records/tradition/{e['id']}/ownership-offer"
    assert author.post(path, json={"user_id": heir.user["id"]}).status_code == 200
    assert author.delete(path).status_code == 200  # cancelled
    assert heir.post(f"{path}/accept").status_code == 404
    assert author.post(path, json={"user_id": heir.user["id"]}).status_code == 200
    assert heir.post(f"{path}/accept").status_code == 200
    assert _reads(heir, t, e) and not _reads(author, t, e)
    got = heir.get(f"/trees/{t}/traditions/{e['id']}").json()
    assert got["is_owner"] is True and got["can_edit"] is True


def test_an_orphaned_record_cannot_be_claimed(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME")
    owner.delete(f"/trees/{t}/members/{_mid(owner, t, uploader)}")
    path = f"/trees/{t}/records/document/{doc['id']}/ownership-offer"
    assert owner.post(path, json={"user_id": owner.user["id"]}).status_code == 404
    join_tree(owner, uploader, t, ["CONTRIBUTOR"])  # the same person, invited again
    assert uploader.post(path, json={"user_id": owner.user["id"]}).status_code == 404
    assert not _sees_doc(uploader, t, doc)


# ------------------------------------------------------------------ other paths
def test_consent_evidence_cannot_probe_for_a_hidden_document(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    doc = _doc(uploader, t, "ONLY_ME", title="Consent letter")
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
