from __future__ import annotations

from sqlalchemy import select

from app.models import FamilyAddress, FamilyAddressVersion, PersonAddress, TreeMembership
from tests.conftest import join_tree, new_tree, owner_session
from tests.helpers import create_person


def shared_body(**extra):  # type: ignore[no-untyped-def]
    body = {
        "label": "Iyer ancestral house",
        "privacy_level": "TREE_MEMBERS",
        "snapshot": {
            "as_recorded": "Iyer Illam, Agraharam Street",
            "street": "12 Agraharam Street",
            "locality": "Palakkad",
            "district": "Palakkad",
            "state": "Kerala",
            "country_code": "IN",
            "postal_code": "678001",
        },
    }
    body.update(extra)
    return body


def reuse_body(source_id: str, mode: str, **extra):  # type: ignore[no-untyped-def]
    body = {
        "source_kind": "family_address",
        "source_id": source_id,
        "source_version": 1,
        "mode": mode,
        "purpose": "ancestral_home",
        "status": "current",
    }
    body.update(extra)
    return body


def test_family_address_link_copy_correction_adoption_and_retirement(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Lakshmi")
    created = owner.post(f"/trees/{tree['id']}/family-addresses", json=shared_body())
    assert created.status_code == 201, created.text
    family = created.json()

    linked_response = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/reuse",
        json=reuse_body(family["id"], "link"),
    )
    copied_response = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/reuse",
        json=reuse_body(family["id"], "copy", is_primary_current=False, idempotency_key="copied-family-home"),
    )
    assert linked_response.status_code == copied_response.status_code == 201
    linked, copied = linked_response.json(), copied_response.json()
    assert linked["reuse_mode"] == "link"
    assert copied["reuse_mode"] == "copy"

    immutable = owner.patch(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/{linked['id']}",
        json={"revision": 1, "street": "Hidden mutation"},
    )
    assert immutable.status_code == 422
    changed_copy = owner.patch(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/{copied['id']}",
        json={"revision": 1, "street": "44 Independently edited road"},
    )
    assert changed_copy.status_code == 200, changed_copy.text
    assert changed_copy.json()["street"] == "44 Independently edited road"
    assert owner.get(f"/trees/{tree['id']}/family-addresses/{family['id']}").json()["snapshot"]["street"] == (
        "12 Agraharam Street"
    )

    corrected = owner.post(
        f"/trees/{tree['id']}/family-addresses/{family['id']}/versions",
        json={
            "revision": 1,
            "reason": "House number corrected",
            "snapshot": {**shared_body()["snapshot"], "street": "14 Agraharam Street"},
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["current_version"] == 2
    addresses = owner.get(f"/trees/{tree['id']}/people/{person['id']}/addresses").json()["items"]
    pinned = next(item for item in addresses if item["id"] == linked["id"])
    assert pinned["street"] == "12 Agraharam Street"
    assert pinned["family_update_available"] == 2

    affected = owner.get(f"/trees/{tree['id']}/family-addresses/{family['id']}/affected?target_version=2")
    assert affected.status_code == 200
    assert [item["address_id"] for item in affected.json()["items"]] == [linked["id"]]
    adopted = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/{linked['id']}/adopt-family-version",
        json={"revision": 1, "version": 2},
    )
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["street"] == "14 Agraharam Street"
    assert adopted.json()["family_update_available"] is None

    retired = owner.delete(
        f"/trees/{tree['id']}/family-addresses/{family['id']}?revision={corrected.json()['revision']}"
    )
    assert retired.status_code == 200, retired.text
    remaining = owner.get(f"/trees/{tree['id']}/people/{person['id']}/addresses").json()["items"]
    assert not {linked["id"], copied["id"]} & {item["id"] for item in remaining}


def test_family_address_sources_are_filtered_and_cross_tree_reuse_is_rejected(owner, tree):  # type: ignore[no-untyped-def]
    family = owner.post(f"/trees/{tree['id']}/family-addresses", json=shared_body()).json()
    sources = owner.get(f"/trees/{tree['id']}/family-addresses/sources?q=Palakkad")
    assert sources.status_code == 200
    assert [(item["source_kind"], item["source_id"]) for item in sources.json()["items"]] == [
        ("family_address", family["id"])
    ]
    assert all(item["source_kind"] != "my_address" for item in sources.json()["items"])

    other = new_tree(owner, "Other family")
    person = create_person(owner, other["id"], "Nila")
    cross_tree = owner.post(
        f"/trees/{other['id']}/people/{person['id']}/addresses/reuse",
        json=reuse_body(family["id"], "copy"),
    )
    assert cross_tree.status_code == 404


def test_selected_member_grants_and_controller_membership_removal_fail_closed(owner, tree, make_client):  # type: ignore[no-untyped-def]
    viewer = make_client()
    viewer.register(name="Selected relative")
    join_tree(owner, viewer, tree["id"], ["VIEWER"])
    selected = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json=shared_body(label="Selected address", privacy_level="SELECTED_MEMBERS"),
    ).json()
    assert viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"] == []
    with owner_session() as db:
        membership = db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == tree["id"],
                TreeMembership.user_id == viewer.user["id"],
            )
        )
        membership_id = str(membership.id)
    granted = owner.post(
        f"/trees/{tree['id']}/family-addresses/{selected['id']}/grants",
        json={"membership_id": membership_id},
    )
    assert granted.status_code == 201, granted.text
    assert selected["id"] in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    owner.delete(f"/trees/{tree['id']}/family-addresses/{selected['id']}/grants/{granted.json()['id']}")
    assert viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"] == []

    controller = make_client()
    controller.register(name="Address controller")
    join_tree(owner, controller, tree["id"], ["CONTRIBUTOR"])
    family = controller.post(
        f"/trees/{tree['id']}/family-addresses", json=shared_body(label="Controller-bound")
    ).json()
    target = create_person(owner, tree["id"], "Devika")
    derivative = owner.post(
        f"/trees/{tree['id']}/people/{target['id']}/addresses/reuse",
        json=reuse_body(family["id"], "copy"),
    ).json()
    with owner_session() as db:
        membership = db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == tree["id"],
                TreeMembership.user_id == controller.user["id"],
            )
        )
        db.delete(membership)
        db.commit()
    visible = owner.get(f"/trees/{tree['id']}/people/{target['id']}/addresses").json()["items"]
    assert derivative["id"] not in {item["id"] for item in visible}


def test_ancestral_assertion_is_the_reused_fact_and_preserves_recorded_name(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Anjali")
    place = owner.post(
        f"/trees/{tree['id']}/places",
        json={
            "canonical_name": "Kalpathy",
            "place_type": "village",
            "local_names": [{"name": "Kalpathi", "language": "ml", "script": "Latn"}],
            "historical_names": [{"name": "Old Kalpathy", "language": "en", "script": "Latn"}],
            "locality": "Kalpathy",
            "district": "Palakkad",
            "state": "Kerala",
        },
    )
    assert place.status_code == 201, place.text
    assertion = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/heritage",
        json={
            "attribute": "ancestral_village",
            "value_text": "Kalpathi (as recorded in 1912)",
            "place_id": place.json()["id"],
        },
    )
    assert assertion.status_code == 201, assertion.text
    target = create_person(owner, tree["id"], "Maya")
    sources = owner.get(f"/trees/{tree['id']}/family-addresses/sources?q=1912").json()["items"]
    ancestral = next(item for item in sources if item["source_kind"] == "ancestral_assertion")
    reused = owner.post(
        f"/trees/{tree['id']}/people/{target['id']}/addresses/reuse",
        json={
            "source_kind": "ancestral_assertion",
            "source_id": ancestral["source_id"],
            "mode": "copy",
            "purpose": "native_place",
            "status": "former",
        },
    )
    assert reused.status_code == 201, reused.text
    assert reused.json()["ancestral_assertion_id"] == assertion.json()["id"]
    assert reused.json()["as_recorded"] == "Kalpathi (as recorded in 1912)"
    assert reused.json()["place_id"] == place.json()["id"]
    removed = owner.delete(f"/trees/{tree['id']}/assertions/{assertion.json()['id']}")
    assert removed.status_code == 200, removed.text
    remaining = owner.get(f"/trees/{tree['id']}/people/{target['id']}/addresses").json()["items"]
    assert reused.json()["id"] not in {item["id"] for item in remaining}
    with owner_session() as db:
        tombstone = db.scalar(select(PersonAddress).where(PersonAddress.id == reused.json()["id"]))
        assert tombstone.withdrawn_at is not None
        assert tombstone.source_revoked_at is not None
        assert tombstone.locality is None


def test_ancestral_family_address_keeps_source_ceiling_and_correction_provenance(owner, tree, make_client):  # type: ignore[no-untyped-def]
    viewer = make_client()
    viewer.register(name="Ancestral-source viewer")
    join_tree(owner, viewer, tree["id"], ["VIEWER"])
    source_person = create_person(owner, tree["id"], "Private ancestor")
    assertion = owner.post(
        f"/trees/{tree['id']}/people/{source_person['id']}/heritage",
        json={
            "attribute": "ancestral_village",
            "value_text": "Private source village",
            "privacy_level": "PRIVATE_SELF",
        },
    ).json()
    created = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Ancestral-derived family address",
            "privacy_level": "TREE_MEMBERS",
            "ancestral_assertion_id": assertion["id"],
        },
    )
    assert created.status_code == 201, created.text
    family = created.json()
    assert family["sharing_released"] is False
    assert family["id"] not in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    corrected = owner.post(
        f"/trees/{tree['id']}/family-addresses/{family['id']}/versions",
        json={
            "revision": family["revision"],
            "reason": "Correct recorded spelling",
            "snapshot": {**shared_body()["snapshot"], "as_recorded": "Private village, corrected"},
        },
    )
    assert corrected.status_code == 200, corrected.text
    removed = owner.delete(f"/trees/{tree['id']}/assertions/{assertion['id']}")
    assert removed.status_code == 200, removed.text
    assert owner.get(f"/trees/{tree['id']}/family-addresses/{family['id']}").status_code == 404
    with owner_session() as db:
        versions = db.scalars(
            select(FamilyAddressVersion).where(FamilyAddressVersion.family_address_id == family["id"])
        ).all()
        assert len(versions) == 2
        assert all(version.source_ancestral_assertion_id is None for version in versions)
        assert all(version.locality is None for version in versions)


def test_person_erasure_and_branch_deletion_purge_ancestral_family_derivatives(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Ancestral source person")
    person_assertion = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/heritage",
        json={"attribute": "ancestral_village", "value_text": "Person source village"},
    ).json()
    person_family = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Person-assertion derivative",
            "privacy_level": "TREE_MEMBERS",
            "ancestral_assertion_id": person_assertion["id"],
        },
    ).json()
    erased = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/erase",
        json={"reason": "Erase ancestral source", "confirm": True},
    )
    assert erased.status_code == 200, erased.text
    assert owner.get(f"/trees/{tree['id']}/family-addresses/{person_family['id']}").status_code == 404

    branch = owner.post(f"/trees/{tree['id']}/branches", json={"name": "Deleted source branch"}).json()
    branch_assertion = owner.post(
        f"/trees/{tree['id']}/branches/{branch['id']}/heritage",
        json={"attribute": "ancestral_village", "value_text": "Branch source village"},
    ).json()
    branch_family = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Branch-assertion derivative",
            "privacy_level": "TREE_MEMBERS",
            "ancestral_assertion_id": branch_assertion["id"],
        },
    ).json()
    deleted = owner.delete(f"/trees/{tree['id']}/branches/{branch['id']}")
    assert deleted.status_code == 200, deleted.text
    assert owner.get(f"/trees/{tree['id']}/family-addresses/{branch_family['id']}").status_code == 404
    with owner_session() as db:
        versions = db.scalars(
            select(FamilyAddressVersion).where(
                FamilyAddressVersion.family_address_id.in_([person_family["id"], branch_family["id"]])
            )
        ).all()
        assert len(versions) == 2
        assert all(version.source_ancestral_assertion_id is None for version in versions)
        assert all(version.locality is None for version in versions)


def test_reused_sources_move_to_member_recent_group_and_are_reauthorized(owner, tree):  # type: ignore[no-untyped-def]
    target = create_person(owner, tree["id"], "Recent target")
    family = owner.post(
        f"/trees/{tree['id']}/family-addresses", json=shared_body(label="Recently reused home")
    ).json()
    before = owner.get(f"/trees/{tree['id']}/family-addresses/sources").json()["items"]
    assert next(item for item in before if item["source_id"] == family["id"])["group"] == "Family"
    reused = owner.post(
        f"/trees/{tree['id']}/people/{target['id']}/addresses/reuse",
        json=reuse_body(family["id"], "copy"),
    )
    assert reused.status_code == 201, reused.text
    after = owner.get(f"/trees/{tree['id']}/family-addresses/sources").json()["items"]
    recent = next(item for item in after if item["source_id"] == family["id"])
    assert recent["group"] == "Recent"
    owner.delete(f"/trees/{tree['id']}/family-addresses/{family['id']}?revision={family['revision']}")
    assert family["id"] not in {
        item["source_id"]
        for item in owner.get(f"/trees/{tree['id']}/family-addresses/sources").json()["items"]
    }


def test_person_erasure_purges_profile_and_family_address_copy_chains(owner, tree):  # type: ignore[no-untyped-def]
    source_person = create_person(owner, tree["id"], "Address source")
    target_person = create_person(owner, tree["id"], "Address recipient")
    with owner_session() as db:
        membership = db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == tree["id"],
                TreeMembership.user_id == owner.user["id"],
            )
        )
        membership.linked_person_id = source_person["id"]
        db.commit()
    source = owner.post(
        f"/trees/{tree['id']}/people/{source_person['id']}/addresses",
        json={
            "purpose": "current_residence",
            "status": "current",
            "is_primary_current": True,
            "street": "99 Erasure Lane",
            "locality": "Kochi",
            "state": "Kerala",
            "country_code": "IN",
        },
    ).json()
    direct_copy = owner.post(
        f"/trees/{tree['id']}/people/{target_person['id']}/addresses/reuse",
        json={
            "source_kind": "my_address",
            "source_id": source["id"],
            "mode": "copy",
            "purpose": "ancestral_home",
            "status": "former",
        },
    ).json()
    family = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Source-derived family home",
            "privacy_level": "TREE_MEMBERS",
            "source_person_id": source_person["id"],
            "source_person_address_id": source["id"],
        },
    ).json()
    corrected = owner.post(
        f"/trees/{tree['id']}/family-addresses/{family['id']}/versions",
        json={
            "revision": family["revision"],
            "reason": "Private correction reason",
            "snapshot": {
                "street": "101 Corrected Erasure Lane",
                "locality": "Kochi",
                "state": "Kerala",
                "country_code": "IN",
            },
        },
    )
    assert corrected.status_code == 200, corrected.text
    family_copy = owner.post(
        f"/trees/{tree['id']}/people/{target_person['id']}/addresses/reuse",
        json=reuse_body(family["id"], "copy", source_version=2, idempotency_key="family-erasure-copy"),
    ).json()

    erased = owner.post(
        f"/trees/{tree['id']}/people/{source_person['id']}/erase",
        json={"reason": "Source-owner erasure request", "confirm": True},
    )
    assert erased.status_code == 200, erased.text
    visible_ids = {
        item["id"]
        for item in owner.get(f"/trees/{tree['id']}/people/{target_person['id']}/addresses").json()["items"]
    }
    assert direct_copy["id"] not in visible_ids
    assert family_copy["id"] not in visible_ids
    assert owner.get(f"/trees/{tree['id']}/family-addresses/{family['id']}").status_code == 404
    with owner_session() as db:
        derivatives = db.scalars(
            select(PersonAddress).where(PersonAddress.id.in_([direct_copy["id"], family_copy["id"]]))
        ).all()
        assert len(derivatives) == 2
        assert all(row.withdrawn_at and row.source_revoked_at for row in derivatives)
        assert all(row.locality is None and row.state is None for row in derivatives)
        family_row = db.scalar(select(FamilyAddress).where(FamilyAddress.id == family["id"]))
        assert family_row.retired_at is not None
        versions = db.scalars(
            select(FamilyAddressVersion).where(FamilyAddressVersion.family_address_id == family["id"])
        ).all()
        assert len(versions) == 2
        assert all(version.locality is None and version.state is None for version in versions)
        assert all("Private correction reason" not in (version.reason_enc or "") for version in versions)


def test_withdrawing_person_address_revokes_family_derivatives(owner, tree, make_client):  # type: ignore[no-untyped-def]
    viewer = make_client()
    viewer.register(name="Person-source viewer")
    join_tree(owner, viewer, tree["id"], ["VIEWER"])
    source_person = create_person(owner, tree["id"], "Withdrawing source")
    target = create_person(owner, tree["id"], "Withdrawal target")
    with owner_session() as db:
        membership = db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == tree["id"],
                TreeMembership.user_id == owner.user["id"],
            )
        )
        membership.linked_person_id = source_person["id"]
        db.commit()
    source = owner.post(
        f"/trees/{tree['id']}/people/{source_person['id']}/addresses",
        json={
            "purpose": "current_residence",
            "status": "current",
            "is_primary_current": True,
            "street": "7 Revocation Road",
            "locality": "Pune",
            "country_code": "IN",
        },
    ).json()
    family = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Withdrawable shared home",
            "privacy_level": "TREE_MEMBERS",
            "source_person_id": source_person["id"],
            "source_person_address_id": source["id"],
        },
    ).json()
    assert family["sharing_released"] is False
    assert family["id"] not in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    derivative = owner.post(
        f"/trees/{tree['id']}/people/{target['id']}/addresses/reuse",
        json=reuse_body(family["id"], "copy"),
    ).json()
    removed = owner.delete(
        f"/trees/{tree['id']}/people/{source_person['id']}/addresses/{source['id']}?revision=1"
    )
    assert removed.status_code == 200, removed.text
    assert owner.get(f"/trees/{tree['id']}/family-addresses/{family['id']}").status_code == 404
    visible = owner.get(f"/trees/{tree['id']}/people/{target['id']}/addresses").json()["items"]
    assert derivative["id"] not in {item["id"] for item in visible}


def test_independent_re_sharing_requires_version_and_audience_bound_consent(owner, tree, make_client):  # type: ignore[no-untyped-def]
    viewer = make_client()
    viewer.register(name="Family viewer")
    join_tree(owner, viewer, tree["id"], ["VIEWER"])
    source = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json=shared_body(label="Private source", privacy_level="ONLY_ME"),
    ).json()
    linked_person = create_person(owner, tree["id"], "Controller")
    with owner_session() as db:
        membership = db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == tree["id"],
                TreeMembership.user_id == owner.user["id"],
            )
        )
        membership.linked_person_id = linked_person["id"]
        db.commit()
    copied = owner.post(
        f"/trees/{tree['id']}/people/{linked_person['id']}/addresses/reuse",
        json=reuse_body(source["id"], "copy"),
    ).json()
    destination_response = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Consent-bound copy",
            "privacy_level": "TREE_MEMBERS",
            "source_person_id": linked_person["id"],
            "source_person_address_id": copied["id"],
        },
    )
    assert destination_response.status_code == 201, destination_response.text
    destination = destination_response.json()
    assert destination["sharing_released"] is False
    assert destination["id"] not in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    consent = owner.post(
        f"/trees/{tree['id']}/family-addresses/{source['id']}/release-consents",
        json={
            "source_version": 1,
            "destination_family_address_id": destination["id"],
            "permitted_privacy_level": "TREE_MEMBERS",
            "purpose": "Share this copied address with the family",
            "notice_version": "address-release-v1",
        },
    )
    assert consent.status_code == 201, consent.text
    activated = owner.post(
        f"/trees/{tree['id']}/family-addresses/{destination['id']}/activate-sharing",
        json={"revision": destination["revision"], "consent_id": consent.json()["id"]},
    )
    assert activated.status_code == 200, activated.text
    assert destination["id"] in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    retired_source = owner.delete(
        f"/trees/{tree['id']}/family-addresses/{source['id']}?revision={source['revision']}"
    )
    assert retired_source.status_code == 200, retired_source.text
    assert destination["id"] not in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    withdrawn = owner.delete(f"/trees/{tree['id']}/family-addresses/release-consents/{consent.json()['id']}")
    assert withdrawn.status_code == 200
    assert destination["id"] not in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }


def test_source_grant_revocation_immediately_invalidates_released_derivative(owner, tree, make_client):  # type: ignore[no-untyped-def]
    controller = make_client()
    controller.register(name="Destination controller")
    join_tree(owner, controller, tree["id"], ["FAMILY_ADMIN"])
    viewer = make_client()
    viewer.register(name="Released reader")
    join_tree(owner, viewer, tree["id"], ["VIEWER"])
    controller_person = create_person(controller, tree["id"], "Destination profile")
    with owner_session() as db:
        membership = db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == tree["id"],
                TreeMembership.user_id == controller.user["id"],
            )
        )
        membership.linked_person_id = controller_person["id"]
        membership_id = str(membership.id)
        db.commit()
    source = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json=shared_body(label="Grant-bound source", privacy_level="SELECTED_MEMBERS"),
    ).json()
    grant = owner.post(
        f"/trees/{tree['id']}/family-addresses/{source['id']}/grants",
        json={"membership_id": membership_id},
    ).json()
    copied = controller.post(
        f"/trees/{tree['id']}/people/{controller_person['id']}/addresses/reuse",
        json=reuse_body(source["id"], "copy"),
    ).json()
    destination = controller.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Released destination",
            "privacy_level": "TREE_MEMBERS",
            "source_person_id": controller_person["id"],
            "source_person_address_id": copied["id"],
        },
    ).json()
    consent_body = {
        "source_version": 1,
        "destination_family_address_id": destination["id"],
        "permitted_privacy_level": "TREE_MEMBERS",
        "purpose": "Explicit release",
        "notice_version": "address-release-v1",
    }
    consent = owner.post(
        f"/trees/{tree['id']}/family-addresses/{source['id']}/release-consents",
        json=consent_body,
    ).json()
    activated = controller.post(
        f"/trees/{tree['id']}/family-addresses/{destination['id']}/activate-sharing",
        json={"revision": destination["revision"], "consent_id": consent["id"]},
    )
    assert activated.status_code == 200, activated.text
    assert destination["id"] in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    revoked = owner.delete(f"/trees/{tree['id']}/family-addresses/{source['id']}/grants/{grant['id']}")
    assert revoked.status_code == 200, revoked.text
    assert destination["id"] not in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    assert controller.get(f"/trees/{tree['id']}/family-addresses/{destination['id']}").status_code == 404


def test_copy_chain_preview_and_activation_require_every_source_controller(owner, tree, make_client):  # type: ignore[no-untyped-def]
    controller = make_client()
    controller.register(name="Middle controller")
    join_tree(owner, controller, tree["id"], ["FAMILY_ADMIN"])
    viewer = make_client()
    viewer.register(name="Newly added reader")
    join_tree(owner, viewer, tree["id"], ["VIEWER"])
    late_viewer = make_client()
    late_viewer.register(name="Late selected reader")
    join_tree(owner, late_viewer, tree["id"], ["VIEWER"])
    owner_person = create_person(owner, tree["id"], "Owner profile")
    controller_person = create_person(owner, tree["id"], "Controller profile")
    with owner_session() as db:
        memberships = {
            str(row.user_id): row
            for row in db.scalars(select(TreeMembership).where(TreeMembership.tree_id == tree["id"])).all()
        }
        owner_membership = memberships[str(owner.user["id"])]
        controller_membership = memberships[str(controller.user["id"])]
        owner_membership.linked_person_id = owner_person["id"]
        controller_membership.linked_person_id = controller_person["id"]
        owner_membership_id = str(owner_membership.id)
        controller_membership_id = str(controller_membership.id)
        viewer_membership_id = str(memberships[str(viewer.user["id"])].id)
        late_viewer_membership_id = str(memberships[str(late_viewer.user["id"])].id)
        db.commit()

    source = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json=shared_body(label="First controller source", privacy_level="SELECTED_MEMBERS"),
    ).json()
    source_grant = owner.post(
        f"/trees/{tree['id']}/family-addresses/{source['id']}/grants",
        json={"membership_id": controller_membership_id},
    )
    assert source_grant.status_code == 201, source_grant.text
    controller_copy = controller.post(
        f"/trees/{tree['id']}/people/{controller_person['id']}/addresses/reuse",
        json=reuse_body(source["id"], "copy"),
    )
    assert controller_copy.status_code == 201, controller_copy.text
    middle = controller.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Second controller copy",
            "privacy_level": "SELECTED_MEMBERS",
            "source_person_id": controller_person["id"],
            "source_person_address_id": controller_copy.json()["id"],
        },
    ).json()
    middle_grant = controller.post(
        f"/trees/{tree['id']}/family-addresses/{middle['id']}/grants",
        json={"membership_id": owner_membership_id},
    )
    assert middle_grant.status_code == 201, middle_grant.text
    owner_copy = owner.post(
        f"/trees/{tree['id']}/people/{owner_person['id']}/addresses/reuse",
        json=reuse_body(middle["id"], "copy"),
    )
    assert owner_copy.status_code == 201, owner_copy.text
    destination = owner.post(
        f"/trees/{tree['id']}/family-addresses",
        json={
            "label": "Family-wide destination",
            "privacy_level": "SELECTED_MEMBERS",
            "source_person_id": owner_person["id"],
            "source_person_address_id": owner_copy.json()["id"],
        },
    ).json()
    initial_grant = owner.post(
        f"/trees/{tree['id']}/family-addresses/{destination['id']}/grants",
        json={"membership_id": viewer_membership_id},
    )
    assert initial_grant.status_code == 201, initial_grant.text
    consent_body = {
        "source_version": 1,
        "destination_family_address_id": destination["id"],
        "permitted_privacy_level": "SELECTED_MEMBERS",
        "purpose": "Share the chained copy with the family",
        "notice_version": "address-release-v1",
    }
    preview = owner.post(
        f"/trees/{tree['id']}/family-addresses/{source['id']}/release-preview",
        json=consent_body,
    )
    assert preview.status_code == 200, preview.text
    assert "Newly added reader" in {reader["display_name"] for reader in preview.json()["additional_readers"]}
    assert set(preview.json()["required_controller_membership_ids"]) == {
        owner_membership_id,
        controller_membership_id,
    }

    source_consent = owner.post(
        f"/trees/{tree['id']}/family-addresses/{source['id']}/release-consents",
        json=consent_body,
    ).json()
    incomplete = owner.post(
        f"/trees/{tree['id']}/family-addresses/{destination['id']}/activate-sharing",
        json={"revision": destination["revision"], "consent_id": source_consent["id"]},
    )
    assert incomplete.status_code == 403
    middle_consent = controller.post(
        f"/trees/{tree['id']}/family-addresses/{middle['id']}/release-consents",
        json=consent_body,
    )
    assert middle_consent.status_code == 201, middle_consent.text
    activated = owner.post(
        f"/trees/{tree['id']}/family-addresses/{destination['id']}/activate-sharing",
        json={"revision": destination["revision"], "consent_id": source_consent["id"]},
    )
    assert activated.status_code == 200, activated.text
    assert destination["id"] in {
        item["id"] for item in viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    widened = owner.post(
        f"/trees/{tree['id']}/family-addresses/{destination['id']}/grants",
        json={"membership_id": late_viewer_membership_id},
    )
    assert widened.status_code == 201, widened.text
    assert destination["id"] not in {
        item["id"] for item in late_viewer.get(f"/trees/{tree['id']}/family-addresses").json()["items"]
    }
    stale_consent = owner.post(
        f"/trees/{tree['id']}/family-addresses/{destination['id']}/activate-sharing",
        json={"revision": activated.json()["revision"] + 1, "consent_id": source_consent["id"]},
    )
    assert stale_consent.status_code == 404


def test_family_address_versions_are_encrypted(owner, tree):  # type: ignore[no-untyped-def]
    created = owner.post(f"/trees/{tree['id']}/family-addresses", json=shared_body()).json()
    with owner_session() as db:
        version = db.scalar(
            select(FamilyAddressVersion).where(FamilyAddressVersion.family_address_id == created["id"])
        )
        assert "Agraharam" not in version.payload_enc
        assert "678001" not in version.payload_enc
    corrected = owner.post(
        f"/trees/{tree['id']}/family-addresses/{created['id']}/versions",
        json={
            "revision": created["revision"],
            "reason": "Secret municipal correction",
            "snapshot": {**shared_body()["snapshot"], "street": "14 Agraharam Street"},
        },
    )
    assert corrected.status_code == 200, corrected.text
    with owner_session() as db:
        version = db.scalar(
            select(FamilyAddressVersion).where(
                FamilyAddressVersion.family_address_id == created["id"],
                FamilyAddressVersion.version == 2,
            )
        )
        assert version.reason_enc is not None
        assert "Secret municipal correction" not in version.reason_enc
