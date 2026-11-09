"""A private document is read-only to everyone but its owner (ADR-0027 §1, §10).

"Only me" and "Selected members" records may be shared with members of any role. Sharing gives
read access (and download when allowed), never the right to change the record: not to a family
admin, a custodian or a contributor, through any route. Someone else's private record is not even
counted where it is hidden (a property's "hidden documents").

Regression for items promised by closed PR #52 that #50 did not carry over: in a probe on main, a
family admin granted view on a Selected-members document could rename it (200), link it to a person
(201), reprocess it (200) and delete it (200).
"""

from __future__ import annotations

from typing import Any

from app.models import ExtractionProposal
from tests.conftest import owner_session
from tests.helpers import create_person
from tests.test_life_events import life_event
from tests.test_property import make_property
from tests.test_record_sharing import _doc, _mid, _share


def _pending_proposal(t: str, doc_id: str) -> str:
    with owner_session() as s, s.begin():
        p = ExtractionProposal(
            tree_id=t,
            document_id=doc_id,
            extractor="test",
            extractor_version="1",
            field="given_name",
            label="Given name",
            proposed_value="Kamla",
            display_value="Kamla",
        )
        s.add(p)
        s.flush()
        return str(p.id)


def _shared_with(owner: Any, t: str, uploader: Any, *grantees: Any) -> dict[str, Any]:
    doc = _doc(uploader, t, "ONLY_ME")
    r = _share(
        uploader,
        t,
        doc["id"],
        "SELECTED_MEMBERS",
        members=[{"membership_id": _mid(owner, t, g), "can_download": True} for g in grantees],
    )
    assert r.status_code == 200, r.text
    return doc


def _refused(r: Any, *, own_rule: bool = True) -> None:
    """Refused. ``own_rule=False`` where the route's own role check may refuse first (403, or 404 for
    a property the member cannot see); the admin, who passes those checks, gets ``not_content_owner``."""
    if not own_rule:
        assert r.status_code in (403, 404), r.text
        return
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "not_content_owner"


def test_members_it_is_shared_with_change_nothing_whatever_their_role(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    custodian = member_factory(["DOCUMENT_CUSTODIAN", "REVIEWER"], name="Custodian")
    cousin = member_factory(["CONTRIBUTOR"], name="Cousin")
    doc = _shared_with(owner, t, uploader, admin, custodian, cousin)
    d = doc["id"]
    ravi = create_person(owner, t, "Ravi")
    # the owner's own link, which grantees must not remove
    own_link = uploader.post(
        f"/trees/{t}/documents/{d}/links", json={"target_type": "person", "target_id": ravi["id"]}
    )
    assert own_link.status_code == 201, own_link.text
    proposal = _pending_proposal(t, d)
    event = life_event(owner, t, ravi["id"], category="award")
    prop = make_property(owner, t, privacy_level="TREE_MEMBERS")

    for grantee in (admin, custodian, cousin):
        got = grantee.get(f"/trees/{t}/documents/{d}")
        assert got.status_code == 200, got.text  # they can still read it
        assert (got.json()["can_change"], got.json()["is_owner"]) == (False, False)
        _refused(grantee.patch(f"/trees/{t}/documents/{d}", json={"title": "Renamed by a grantee"}))
        _refused(
            grantee.post(
                f"/trees/{t}/documents/{d}/links", json={"target_type": "person", "target_id": ravi["id"]}
            )
        )
        _refused(grantee.delete(f"/trees/{t}/documents/{d}/links/{own_link.json()['id']}"))
        _refused(
            grantee.post(f"/trees/{t}/events/{event['id']}/media/link", json={"document_id": d}),
            own_rule=grantee is admin,
        )
        _refused(
            grantee.post(
                f"/trees/{t}/properties/{prop['id']}/events", json={"type": "mutation", "document_ids": [d]}
            ),
            own_rule=grantee is admin,
        )
    _refused(admin.post(f"/trees/{t}/documents/{d}/reprocess"))
    _refused(custodian.post(f"/trees/{t}/extraction-proposals/{proposal}/review", json={"action": "reject"}))
    _refused(admin.delete(f"/trees/{t}/documents/{d}"))

    # nothing changed
    after = uploader.get(f"/trees/{t}/documents/{d}").json()
    assert after["title"] == doc["title"] and after["deleted_at"] is None
    assert [link["target_id"] for link in after["links"]] == [ravi["id"]]
    assert admin.get(f"/trees/{t}/events/{event['id']}/media").json() == []
    # the owner may still change their own record
    own = uploader.get(f"/trees/{t}/documents/{d}").json()
    assert (own["can_change"], own["is_owner"]) == (True, True)
    assert uploader.patch(f"/trees/{t}/documents/{d}", json={"title": "Nani's wedding"}).status_code == 200
    assert uploader.delete(f"/trees/{t}/documents/{d}/links/{own_link.json()['id']}").status_code == 200


def test_shared_audiences_keep_the_role_rules(owner, tree, member_factory):
    """Only private records change: on a shared record, managers still manage as before."""
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR"], name="Uploader")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    doc = _doc(uploader, t, "TREE_MEMBERS")
    assert admin.get(f"/trees/{t}/documents/{doc['id']}").json()["can_change"] is True
    r = admin.patch(f"/trees/{t}/documents/{doc['id']}", json={"title": "Corrected title"})
    assert r.status_code == 200, r.text
    assert admin.delete(f"/trees/{t}/documents/{doc['id']}").status_code == 200
    assert admin.post(f"/trees/{t}/documents/{doc['id']}/restore").status_code == 200


def test_a_property_does_not_count_someone_elses_private_document(owner, tree, member_factory):
    t = tree["id"]
    uploader = member_factory(["CONTRIBUTOR", "PROPERTY_CUSTODIAN"], name="Uploader")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    prop = make_property(owner, t, privacy_level="TREE_MEMBERS")
    private = _doc(uploader, t, "ONLY_ME", title="Uploader's own deed copy")
    r = uploader.post(
        f"/trees/{t}/documents/{private['id']}/links",
        json={"target_type": "property", "target_id": prop["id"]},
    )
    assert r.status_code == 201, r.text
    hidden_from_admin = _doc(uploader, t, "PRIVATE_TREE_ADMINS", title="Admin-only record")
    owner.post(
        f"/trees/{t}/documents/{hidden_from_admin['id']}/links",
        json={"target_type": "property", "target_id": prop["id"]},
    )

    for viewer in (owner, admin):
        tl = viewer.get(f"/trees/{t}/properties/{prop['id']}/timeline").json()
        titles = [d["title"] for d in tl["documents"]]
        assert "Uploader's own deed copy" not in titles
        assert tl["hidden_document_count"] == 0, tl  # not even counted
    own = uploader.get(f"/trees/{t}/properties/{prop['id']}/timeline").json()
    assert "Uploader's own deed copy" in [d["title"] for d in own["documents"]]
