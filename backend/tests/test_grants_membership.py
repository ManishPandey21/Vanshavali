"""ADR-0027 §3: grants belong to memberships, and only manageable grants are listed (finding A7)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AccessGrant, TreeMembership
from tests.conftest import join_tree, new_tree, owner_session
from tests.doc_fixtures import png_bytes, text_image, upload


def _png(label: str = "Family photo, Varanasi 1952") -> bytes:
    return png_bytes(text_image([label], width=900))


def _grant(client, tree_id: str, user_id: str, resource_id: str, resource_type: str = "document"):  # type: ignore[no-untyped-def]
    return client.post(
        f"/trees/{tree_id}/grants",
        json={
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "permission": "view",
        },
    )


def _membership_id(tree_id: str, user_id: str) -> uuid.UUID:
    with owner_session() as db:
        mid = db.scalar(
            select(TreeMembership.id).where(
                TreeMembership.tree_id == tree_id, TreeMembership.user_id == user_id
            )
        )
        assert mid is not None
        return mid


def test_a_grant_is_stored_against_the_grantees_membership(owner, tree, member_factory):
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png", privacy_level="CUSTOM").json()
    viewer = member_factory(["VIEWER"])
    g = _grant(owner, t, viewer.user["id"], doc["id"])
    assert g.status_code == 201, g.text
    with owner_session() as db:
        row = db.get(AccessGrant, g.json()["id"])
        assert row is not None
        assert row.membership_id == _membership_id(t, viewer.user["id"])
        assert str(row.user_id) == viewer.user["id"]  # kept for one release, never used for access
    assert viewer.get(f"/trees/{t}/documents/{doc['id']}").status_code == 200


def test_removing_the_membership_deletes_its_grants_in_the_database(owner, tree, member_factory):
    """The cascade is the database's, not the service's: deleting the row is enough."""
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png", privacy_level="CUSTOM").json()
    viewer = member_factory(["VIEWER"])
    assert _grant(owner, t, viewer.user["id"], doc["id"]).status_code == 201
    mid = _membership_id(t, viewer.user["id"])
    with owner_session() as db:
        m = db.get(TreeMembership, mid)
        db.delete(m)
        db.commit()
        assert db.scalars(select(AccessGrant).where(AccessGrant.membership_id == mid)).all() == []


def test_a_grant_cannot_name_a_membership_of_another_tree(owner, tree, member_factory):
    t = tree["id"]
    other = new_tree(owner, "Other tree")
    viewer = member_factory(["VIEWER"])
    join_tree(owner, viewer, other["id"], ["VIEWER"])
    doc = upload(owner, t, _png(), mime="image/png", privacy_level="CUSTOM").json()
    foreign_membership = _membership_id(other["id"], viewer.user["id"])
    with owner_session() as db:
        db.add(
            AccessGrant(
                tree_id=uuid.UUID(t),
                membership_id=foreign_membership,  # composite FK (tree_id, membership_id)
                user_id=uuid.UUID(viewer.user["id"]),
                resource_type="document",
                resource_id=uuid.UUID(doc["id"]),
                permission="view",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_grants_are_only_given_to_members_of_this_tree(owner, tree, make_client):
    t = tree["id"]
    doc = upload(owner, t, _png(), mime="image/png", privacy_level="CUSTOM").json()
    stranger = make_client()
    stranger.register(name="Stranger")
    new_tree(stranger, "Stranger's tree")
    assert _grant(owner, t, stranger.user["id"], doc["id"]).status_code == 404


def test_grants_on_records_the_caller_cannot_see_are_not_revealed(owner, tree, member_factory):
    """A7: a privacy manager sees, creates and revokes grants only on records visible to them."""
    t = tree["id"]
    contributor = member_factory(["CONTRIBUTOR"], name="Uploader")
    admin = member_factory(["FAMILY_ADMIN"], name="Admin")
    viewer = member_factory(["VIEWER"], name="Viewer")
    private = upload(contributor, t, _png(), mime="image/png", privacy_level="PRIVATE_SELF").json()
    shared = upload(
        owner, t, _png("Wedding, Prayagraj 1961"), mime="image/png", privacy_level="CUSTOM"
    ).json()
    assert admin.get(f"/trees/{t}/documents/{private['id']}").status_code == 404  # premise

    hidden = _grant(owner, t, viewer.user["id"], private["id"])  # the owner is the archive custodian
    assert hidden.status_code == 201, hidden.text
    visible = _grant(owner, t, viewer.user["id"], shared["id"])
    assert visible.status_code == 201, visible.text

    listed = {g["id"] for g in admin.get(f"/trees/{t}/grants").json()}
    assert visible.json()["id"] in listed
    assert hidden.json()["id"] not in listed
    assert admin.delete(f"/trees/{t}/grants/{hidden.json()['id']}").status_code == 404
    assert _grant(admin, t, viewer.user["id"], private["id"]).status_code == 404
    assert _grant(admin, t, viewer.user["id"], str(uuid.uuid4())).status_code == 404  # same answer

    assert hidden.json()["id"] in {g["id"] for g in owner.get(f"/trees/{t}/grants").json()}
    assert viewer.get(f"/trees/{t}/grants").status_code == 403
