"""ADR-0027 §2 ownership transfer for documents, traditions and photo collections, plus the paths
the sharing stack left open: render files and the consent evidence-document check."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import join_tree, new_tree
from tests.doc_fixtures import png_bytes, text_image, upload
from tests.helpers import create_person

_n = 0


def _png() -> bytes:
    global _n
    _n += 1
    return png_bytes(text_image([f"Ownership photo {_n}"], width=420))


def _mid(owner: Any, t: str, client: Any) -> str:
    return next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == client.user["id"])


def _record(kind: str, client: Any, t: str, title: str = "Heirloom") -> str:
    """A new Only-me record of the given kind, owned by ``client``."""
    if kind == "document":
        r = upload(client, t, _png(), mime="image/png", title=title, privacy_level="ONLY_ME")
    elif kind == "tradition":
        r = client.post(
            f"/trees/{t}/traditions",
            json={"kind": "recipe", "title": title, "body": "Khoya.", "privacy_level": "ONLY_ME"},
        )
    else:
        r = client.post(f"/trees/{t}/collections", json={"title": title, "privacy_level": "ONLY_ME"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


_PATHS = {"document": "documents", "tradition": "traditions", "collection": "collections"}


def _sees(client: Any, t: str, kind: str, rid: str) -> bool:
    r = client.get(f"/trees/{t}/{_PATHS[kind]}/{rid}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


@pytest.mark.parametrize("kind", ["document", "tradition", "collection"])
def test_ownership_is_offered_and_must_be_accepted(owner, tree, member_factory, kind):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    rid = _record(kind, uploader, t)
    offer = f"/trees/{t}/records/{kind}/{rid}/ownership-offer"

    assert heir.post(offer, json={"user_id": heir.user["id"]}).status_code == 404  # not the owner
    assert owner.post(offer, json={"user_id": owner.user["id"]}).status_code == 404  # nor the tree owner
    assert uploader.post(offer, json={"user_id": uploader.user["id"]}).status_code == 422

    r = uploader.post(offer, json={"user_id": heir.user["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["pending_owner_membership_id"] == _mid(owner, t, heir)
    assert not _sees(heir, t, kind, rid)  # an offer gives no access
    assert heir.get(f"/trees/{t}/ownership-offers").json() == [
        {"resource_type": kind, "resource_id": rid, "title": "Heirloom"}
    ]
    assert owner.get(f"/trees/{t}/ownership-offers").json() == []
    assert owner.post(f"{offer}/accept").status_code == 404

    r = heir.post(f"{offer}/accept")
    assert r.status_code == 200 and r.json()["owner_membership_id"] == _mid(owner, t, heir)
    assert _sees(heir, t, kind, rid) and not _sees(uploader, t, kind, rid)
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []
    assert heir.get(f"/trees/{t}/{_PATHS[kind]}/{rid}/sharing").status_code == 200  # the new owner shares
    assert uploader.get(f"/trees/{t}/{_PATHS[kind]}/{rid}/sharing").status_code == 404

    # the new owner offers it back: the old owner declines; an offer can also be cancelled
    assert heir.post(offer, json={"user_id": uploader.user["id"]}).status_code == 200
    assert uploader.delete(offer).status_code == 200
    assert uploader.post(f"{offer}/accept").status_code == 404
    assert heir.post(offer, json={"user_id": uploader.user["id"]}).status_code == 200
    assert heir.delete(offer).status_code == 200
    assert uploader.post(f"{offer}/accept").status_code == 404

    # the audit log keeps every step, and never names the record to someone outside its audience
    events = owner.get(f"/trees/{t}/audit", params={"limit": 200}).json()["items"]
    assert all(e.get("target_id") != rid for e in events)


def test_transfer_keeps_the_records_grants(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    cousin = member_factory(["VIEWER"], name="Cousin")
    rid = _record("tradition", uploader, t)
    r = uploader.put(
        f"/trees/{t}/traditions/{rid}/sharing",
        json={
            "privacy_level": "SELECTED_MEMBERS",
            "members": [{"membership_id": _mid(owner, t, cousin)}],
            "confirm_wider": True,
        },
    )
    assert r.status_code == 200, r.text
    offer = f"/trees/{t}/records/tradition/{rid}/ownership-offer"
    assert uploader.post(offer, json={"user_id": heir.user["id"]}).status_code == 200
    assert heir.post(f"{offer}/accept").status_code == 200
    assert _sees(cousin, t, "tradition", rid)
    grants = heir.get(f"/trees/{t}/grants").json()
    assert [g["resource_id"] for g in grants] == [rid]  # the new owner manages them
    assert uploader.get(f"/trees/{t}/grants").json() == []


def test_offers_and_orphans_cannot_be_used_to_claim_a_record(owner, tree, member_factory, make_client):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    heir = member_factory(["CONTRIBUTOR"], name="Heir")
    rid = _record("document", uploader, t)
    offer = f"/trees/{t}/records/document/{rid}/ownership-offer"

    stranger = make_client()
    stranger.register(name="Stranger")
    new_tree(stranger, "Elsewhere")
    assert uploader.post(offer, json={"user_id": stranger.user["id"]}).status_code == 404  # not a member here

    # an offer to someone who then leaves lapses with their membership
    assert uploader.post(offer, json={"user_id": heir.user["id"]}).status_code == 200
    assert owner.delete(f"/trees/{t}/members/{_mid(owner, t, heir)}").status_code == 200
    join_tree(owner, heir, t, ["CONTRIBUTOR"])
    assert heir.post(f"{offer}/accept").status_code == 404
    assert heir.get(f"/trees/{t}/ownership-offers").json() == []

    # an orphaned record (its owner left) is offered and accepted by nobody
    assert owner.delete(f"/trees/{t}/members/{_mid(owner, t, uploader)}").status_code == 200
    assert owner.post(offer, json={"user_id": owner.user["id"]}).status_code == 404
    join_tree(owner, uploader, t, ["CONTRIBUTOR"])
    assert uploader.post(offer, json={"user_id": uploader.user["id"]}).status_code == 404
    assert not _sees(uploader, t, "document", rid) and not _sees(owner, t, "document", rid)


def test_unknown_record_types_are_not_found(owner, tree):
    t = tree["id"]
    p = create_person(owner, t, "Asha")
    r = owner.post(f"/trees/{t}/records/person/{p['id']}/ownership-offer", json={"user_id": owner.user["id"]})
    assert r.status_code == 404


def test_consent_evidence_cannot_probe_for_a_hidden_document(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    rid = _record("document", uploader, t, title="Consent letter")
    p = create_person(owner, t, "Living", status="living")
    body = {
        "granted_by_name": "Living",
        "authority_basis": "self",
        "purpose": "Family history",
        "data_categories": ["names"],
        "evidence_document_id": rid,
    }
    r = owner.post(f"/trees/{t}/people/{p['id']}/consents", json=body)
    assert r.status_code == 404, r.text  # the same answer as for a document that does not exist
    own = _record("document", owner, t, title="Owner's letter")
    assert (
        owner.post(
            f"/trees/{t}/people/{p['id']}/consents", json={**body, "evidence_document_id": own}
        ).status_code
        == 201
    )
