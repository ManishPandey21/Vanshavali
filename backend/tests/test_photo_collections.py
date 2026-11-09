"""Standalone photo collections (ADR-0027 §6, increment 4; threat T59).

A collection is a shareable record of its own. Its photos keep their own audience: a viewer sees a
photo in a collection only when they may see both, counts and covers follow each viewer, and
sharing a collection never shares its photos.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models import AccessGrant
from tests.conftest import join_tree, new_tree, owner_session
from tests.doc_fixtures import png_bytes, text_image, upload

_n = 0


def _photo(client: Any, t: str, level: str, **form: Any) -> str:
    global _n
    _n += 1
    data = png_bytes(text_image([f"Collection photo {_n}"], width=320))
    r = upload(
        client, t, data, mime="image/png", category="photo", title=f"Photo {_n}", privacy_level=level, **form
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _collection(client: Any, t: str, **body: Any) -> dict[str, Any]:
    r = client.post(f"/trees/{t}/collections", json={"title": "Nani's village", **body})
    assert r.status_code == 201, r.text
    return r.json()


def _add(client: Any, t: str, cid: str, doc_id: str, **body: Any) -> Any:
    return client.post(f"/trees/{t}/collections/{cid}/items", json={"document_id": doc_id, **body})


def _mid(owner: Any, t: str, client: Any) -> str:
    return next(m["id"] for m in owner.get(f"/trees/{t}/members").json() if m["user_id"] == client.user["id"])


def _share(client: Any, t: str, cid: str, level: str, **body: Any) -> Any:
    return client.put(
        f"/trees/{t}/collections/{cid}/sharing", json={"privacy_level": level, "confirm_wider": True, **body}
    )


def _sees(client: Any, t: str, cid: str) -> bool:
    r = client.get(f"/trees/{t}/collections/{cid}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


def test_a_new_collection_is_only_me_and_invisible_to_every_role(owner, tree, member_factory):
    t = tree["id"]
    b = owner.post(f"/trees/{t}/branches", json={"name": "Pune"}).json()
    author = member_factory(["CONTRIBUTOR"], name="Author")
    c = _collection(author, t)
    assert (c["privacy_level"], c["is_owner"], c["item_count"]) == ("ONLY_ME", True, 0)
    for who in (
        owner,
        member_factory(["FAMILY_ADMIN"], name="Admin"),
        member_factory(["BRANCH_ADMIN"], branch_id=b["id"], name="Branch admin"),
        member_factory(["DOCUMENT_CUSTODIAN"], name="Custodian"),
        member_factory(["VIEWER"], name="Viewer"),
    ):
        assert not _sees(who, t, c["id"])
        assert c["id"] not in {x["id"] for x in who.get(f"/trees/{t}/collections").json()}
        assert who.get(f"/trees/{t}/collections/{c['id']}/sharing").status_code == 404
    items = owner.get(f"/trees/{t}/audit").json()["items"]
    assert c["id"] not in str(items) and any(i["target_type"] == "private_record" for i in items)


def test_viewers_see_only_the_photos_they_may_see(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    viewer = member_factory(["VIEWER"], name="Viewer")
    c = _collection(author, t, privacy_level="TREE_MEMBERS")
    shared = _photo(author, t, "TREE_MEMBERS")
    private = _photo(author, t, "ONLY_ME")
    assert _add(author, t, c["id"], private, is_cover=True).status_code == 201
    r = _add(author, t, c["id"], shared)
    assert r.status_code == 201, r.text
    mine = r.json()
    assert (mine["item_count"], mine["cover_document_id"]) == (2, private)
    # the owner is told which photos part of the collection's audience cannot see
    flags = {i["document_id"]: i["shared_with_collection_audience"] for i in mine["items"]}
    assert flags == {private: False, shared: True} and mine["items_not_shared"] == 1
    theirs = viewer.get(f"/trees/{t}/collections/{c['id']}").json()
    assert [i["document_id"] for i in theirs["items"]] == [shared]
    assert (theirs["item_count"], theirs["cover_document_id"]) == (1, shared)
    assert theirs["items_not_shared"] is None and all(
        i["shared_with_collection_audience"] is None for i in theirs["items"]
    )
    summary = next(x for x in viewer.get(f"/trees/{t}/collections").json() if x["id"] == c["id"])
    assert (summary["item_count"], summary["cover_document_id"]) == (1, shared)
    # sharing the collection never shares the photo
    assert viewer.get(f"/trees/{t}/documents/{private}").status_code == 404


def test_only_the_owner_changes_the_contents(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    c = _collection(author, t, privacy_level="TREE_MEMBERS")
    p = _photo(admin, t, "TREE_MEMBERS")
    assert _add(admin, t, c["id"], p).status_code == 403
    assert admin.patch(f"/trees/{t}/collections/{c['id']}", json={"title": "x"}).status_code == 403
    assert admin.delete(f"/trees/{t}/collections/{c['id']}").status_code == 403
    item = _add(author, t, c["id"], p).json()["items"][0]
    assert admin.delete(f"/trees/{t}/collections/{c['id']}/items/{item['id']}").status_code == 403
    # an admin may narrow a shared collection, never widen it; the owner widens with confirmation
    assert _share(admin, t, c["id"], "ONLY_ME").status_code == 200
    assert not _sees(admin, t, c["id"])
    r = author.put(f"/trees/{t}/collections/{c['id']}/sharing", json={"privacy_level": "TREE_MEMBERS"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "confirm_wider"


def test_only_visible_photos_can_be_added(owner, tree, member_factory, make_client):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    c = _collection(author, t)
    someone_elses = _photo(owner, t, "ONLY_ME")
    assert _add(author, t, c["id"], someone_elses).status_code == 404
    letter = upload(
        author, t, png_bytes(text_image(["A letter"])), mime="image/png", category="letter", title="Letter"
    )
    assert _add(author, t, c["id"], letter.json()["id"]).status_code == 422
    other = new_tree(owner, "Other family")
    far = _photo(owner, other["id"], "TREE_MEMBERS")
    assert _add(author, t, c["id"], far).status_code == 404  # never another tree's photo
    p = _photo(author, t, "TREE_MEMBERS")
    assert _add(author, t, c["id"], p).status_code == 201
    r = _add(author, t, c["id"], p)
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_item"


def test_selected_members_grants_and_deletion(owner, tree, member_factory):
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    asha = member_factory(["VIEWER"], name="Asha")
    c = _collection(author, t)
    p = _photo(author, t, "TREE_MEMBERS")
    _add(author, t, c["id"], p)
    mid = _mid(owner, t, asha)
    r = _share(author, t, c["id"], "SELECTED_MEMBERS", members=[{"membership_id": mid}])
    assert r.status_code == 200, r.text
    assert {a["display_name"] for a in r.json()["audience"]} == {"Author", "Asha"}
    assert _sees(asha, t, c["id"]) and not _sees(owner, t, c["id"])
    assert c["id"] not in str(owner.get(f"/trees/{t}/grants").json())
    # removing Asha deletes her grant; re-inviting her brings nothing back
    assert owner.delete(f"/trees/{t}/members/{mid}").status_code == 200
    join_tree(owner, asha, t, ["VIEWER"])
    assert not _sees(asha, t, c["id"])
    # deleting the collection keeps the photo and removes the collection's grants
    mid2 = _mid(owner, t, asha)
    assert (
        _share(author, t, c["id"], "SELECTED_MEMBERS", members=[{"membership_id": mid2}]).status_code == 200
    )
    assert author.delete(f"/trees/{t}/collections/{c['id']}").status_code == 200
    assert author.get(f"/trees/{t}/documents/{p}").status_code == 200
    with owner_session() as db:
        assert db.scalars(select(AccessGrant).where(AccessGrant.resource_id == c["id"])).all() == []


def test_collections_are_never_public_and_need_a_branch(owner, tree):
    t = tree["id"]
    r = owner.post(f"/trees/{t}/collections", json={"title": "x", "privacy_level": "PUBLIC_DECEASED_ONLY"})
    assert r.status_code == 422
    r = owner.post(f"/trees/{t}/collections", json={"title": "x", "privacy_level": "FAMILY_BRANCH"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "branch_required"
    r = owner.post(f"/trees/{t}/collections", json={"title": "x", "privacy_level": "CUSTOM"})
    assert r.status_code == 422


def test_audit_log_hides_private_traditions_too(owner, tree, member_factory):
    """Regression (increment 2): audit entries about a private tradition named it to admins."""
    t = tree["id"]
    author = member_factory(["CONTRIBUTOR"], name="Author")
    e = author.post(
        f"/trees/{t}/traditions", json={"kind": "recipe", "title": "Secret", "privacy_level": "ONLY_ME"}
    ).json()
    items = owner.get(f"/trees/{t}/audit").json()["items"]
    assert e["id"] not in str(items)
