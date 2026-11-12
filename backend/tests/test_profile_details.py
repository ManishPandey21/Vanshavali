from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import event, select

from app.core.db import get_engine
from app.models import PersonAddress, PersonContactMethod, PersonDetailRevision
from tests.conftest import join_tree, new_tree, owner_session
from tests.helpers import create_person


def address_body(**extra):  # type: ignore[no-untyped-def]
    body = {
        "purpose": "current_residence",
        "status": "current",
        "is_primary_current": True,
        "locality": "Mylapore",
        "sub_district": "Chennai South",
        "district": "Chennai",
        "state": "Tamil Nadu",
        "country_code": "IN",
        "postal_code": "600004",
        "street": "12 Secret Street",
        "landmark": "Near Kapaleeshwarar Temple",
        "gram_panchayat": "As recorded panchayat",
        "post_office": "Mylapore HO",
    }
    body.update(extra)
    return body


def test_address_crud_encrypts_sensitive_payload_and_keeps_revision_history(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Meena")
    created = owner.post(f"/trees/{tree['id']}/people/{person['id']}/addresses", json=address_body())
    assert created.status_code == 201, created.text
    address = created.json()
    assert address["street"] == "12 Secret Street"
    assert address["revision"] == 1
    source = owner.post(
        f"/trees/{tree['id']}/sources",
        json={"title": "Municipal address register", "source_type": "civil_record"},
    ).json()
    citation = owner.post(
        f"/trees/{tree['id']}/citations",
        json={"source_id": source["id"], "target_type": "address", "target_id": address["id"]},
    )
    assert citation.status_code == 201, citation.text

    changed = owner.patch(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/{address['id']}",
        json={"revision": 1, "street": "14 New Secret Street", "reason": "House renumbered"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2

    history = owner.get(f"/trees/{tree['id']}/people/{person['id']}/addresses/{address['id']}/history")
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert [item["operation"] for item in items] == ["created", "updated"]
    assert items[1]["before"]["street"] == "12 Secret Street"
    assert items[1]["after"]["street"] == "14 New Secret Street"

    with owner_session() as db:
        row = db.scalar(select(PersonAddress).where(PersonAddress.id == address["id"]))
        revisions = db.scalars(
            select(PersonDetailRevision).where(PersonDetailRevision.record_id == address["id"])
        ).all()
        stored = row.payload_enc + "".join(
            (r.before_enc or "") + (r.after_enc or "") + (r.reason_enc or "") for r in revisions
        )
        assert "Secret Street" not in stored
        assert "600004" not in stored
        assert "House renumbered" not in stored


def test_address_move_is_atomic_idempotent_and_preserves_other_current_addresses(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Kavya")
    first = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json=address_body(idempotency_key="first"),
    ).json()
    owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json=address_body(is_primary_current=False, street="Second home", idempotency_key="second"),
    )
    body = {
        "revision": first["revision"],
        "idempotency_key": "m" * 100,
        "valid_until": {"precision": "exact", "year": 2026, "month": 11, "day": 12},
        "new_address": address_body(street="44 Destination Road", idempotency_key=None),
    }
    moved = owner.post(f"/trees/{tree['id']}/people/{person['id']}/addresses/{first['id']}/move", json=body)
    repeated = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/{first['id']}/move", json=body
    )
    assert moved.status_code == repeated.status_code == 200
    assert moved.json()["new_address"]["id"] == repeated.json()["new_address"]["id"]
    listed = owner.get(f"/trees/{tree['id']}/people/{person['id']}/addresses").json()["items"]
    assert len([a for a in listed if a["status"] == "current"]) == 2
    assert next(a for a in listed if a["id"] == first["id"])["status"] == "former"


def test_address_rejects_reversed_definite_period_and_stale_revision(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Anita")
    bad = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json=address_body(
            valid_from={"precision": "exact", "year": 2025, "month": 1, "day": 1},
            valid_until={"precision": "exact", "year": 2024, "month": 1, "day": 1},
        ),
    )
    assert bad.status_code == 422
    address = owner.post(f"/trees/{tree['id']}/people/{person['id']}/addresses", json=address_body()).json()
    stale = owner.patch(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/{address['id']}",
        json={"revision": 99, "locality": "Adyar"},
    )
    assert stale.status_code == 409

    dated = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json=address_body(
            is_primary_current=False,
            valid_from={"precision": "exact", "year": 2025, "month": 1, "day": 1},
        ),
    ).json()
    reversed_move = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses/{dated['id']}/move",
        json={
            "revision": dated["revision"],
            "idempotency_key": "bad-move",
            "valid_until": {"precision": "exact", "year": 2024, "month": 1, "day": 1},
            "new_address": address_body(is_primary_current=False),
        },
    )
    assert reversed_move.status_code == 422
    assert reversed_move.json()["error"]["code"] == "invalid_period"


def test_contacts_are_masked_by_default_revealed_explicitly_and_preferred_is_unique(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Ravi")
    first = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "email", "value": "ravi@example.com", "is_preferred": True},
    )
    assert first.status_code == 201, first.text
    second = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "email", "value": "work@example.com", "is_preferred": True},
    )
    assert second.status_code == 201, second.text
    listed = owner.get(f"/trees/{tree['id']}/people/{person['id']}/contacts").json()["items"]
    assert all("value" not in item for item in listed)
    assert sum(item["is_preferred"] for item in listed) == 1
    assert next(item for item in listed if item["id"] == second.json()["id"])["hint"] == "w***@example.com"
    reveal = owner.get(f"/trees/{tree['id']}/people/{person['id']}/contacts/{second.json()['id']}/reveal")
    assert reveal.json()["value"] == "work@example.com"
    first_history = owner.get(
        f"/trees/{tree['id']}/people/{person['id']}/contacts/{first.json()['id']}/history"
    )
    history_items = first_history.json()["items"]
    assert [item["operation"] for item in history_items] == [
        "created",
        "preferred_reassigned",
    ]
    assert history_items[-1]["after"]["is_preferred"] is False
    assert history_items[0]["after"]["value"] == "r***@example.com"
    with owner_session() as db:
        stored = db.scalar(
            select(PersonContactMethod.value_enc).where(PersonContactMethod.id == second.json()["id"])
        )
        assert "work@example.com" not in stored


def test_contacts_validate_kind_specific_values(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Renu")
    invalid = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "email", "value": "not-an-email"},
    )
    arbitrary_url = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "instagram", "value": "http://evil.example/profile"},
    )
    assert invalid.status_code == 422
    assert arbitrary_url.status_code == 422

    telegram = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "telegram", "value": "@family_builder"},
    )
    assert telegram.status_code == 201, telegram.text
    revealed = owner.get(f"/trees/{tree['id']}/people/{person['id']}/contacts/{telegram.json()['id']}/reveal")
    assert revealed.json()["profile_url"] == "https://t.me/family_builder"

    invalid_telegram = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "telegram", "value": "@family.builder"},
    )
    assert invalid_telegram.status_code == 422
    invalid_instagram = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "instagram", "value": f"@{'a' * 31}"},
    )
    assert invalid_instagram.status_code == 422


def test_whatsapp_copy_is_explicit_and_prompts_after_mobile_changes(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Copy Contact")
    mobile = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "mobile", "value": "+919876543210", "language": "hi"},
    ).json()
    whatsapp = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={
            "kind": "whatsapp",
            "value": "+919876543210",
            "copied_from_contact_id": mobile["id"],
            "copied_from_revision": mobile["revision"],
        },
    )
    assert whatsapp.status_code == 201, whatsapp.text
    assert whatsapp.json()["copy_outdated"] is False

    metadata_edit = owner.patch(
        f"/trees/{tree['id']}/people/{person['id']}/contacts/{whatsapp.json()['id']}",
        json={"revision": whatsapp.json()["revision"], "purpose": "family updates"},
    )
    assert metadata_edit.status_code == 200, metadata_edit.text
    assert metadata_edit.json()["copied_from_contact_id"] == mobile["id"]

    changed = owner.patch(
        f"/trees/{tree['id']}/people/{person['id']}/contacts/{mobile['id']}",
        json={"revision": mobile["revision"], "value": "+919999999999"},
    ).json()
    listed = owner.get(f"/trees/{tree['id']}/people/{person['id']}/contacts").json()["items"]
    copied = next(item for item in listed if item["id"] == whatsapp.json()["id"])
    assert copied["copy_outdated"] is True

    refreshed = owner.patch(
        f"/trees/{tree['id']}/people/{person['id']}/contacts/{copied['id']}",
        json={
            "revision": copied["revision"],
            "copied_from_contact_id": mobile["id"],
            "copied_from_revision": changed["revision"],
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["copy_outdated"] is False
    reveal = owner.get(f"/trees/{tree['id']}/people/{person['id']}/contacts/{copied['id']}/reveal")
    assert reveal.json()["value"] == "+919999999999"


def test_contact_page_batches_copy_source_revision_lookup(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Batch Contact")
    mobile = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "mobile", "value": "+919876543210"},
    ).json()
    for purpose in ("family", "events"):
        created = owner.post(
            f"/trees/{tree['id']}/people/{person['id']}/contacts",
            json={
                "kind": "whatsapp",
                "value": "+919876543210",
                "purpose": purpose,
                "copied_from_contact_id": mobile["id"],
                "copied_from_revision": mobile["revision"],
            },
        )
        assert created.status_code == 201, created.text

    contact_selects: list[str] = []

    def capture_contact_selects(  # type: ignore[no-untyped-def]
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "person_contact_method" in statement:
            contact_selects.append(statement)

    engine = get_engine()
    event.listen(engine, "before_cursor_execute", capture_contact_selects)
    try:
        response = owner.get(f"/trees/{tree['id']}/people/{person['id']}/contacts")
    finally:
        event.remove(engine, "before_cursor_execute", capture_contact_selects)

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 3
    assert len(contact_selects) == 2  # page query + one batched source-revision query


def test_detail_lists_are_paginated_and_create_idempotency_is_scoped(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Leela")
    first = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json=address_body(is_primary_current=False, idempotency_key="same-request"),
    )
    repeated = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json=address_body(is_primary_current=False, idempotency_key="same-request"),
    )
    owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json=address_body(is_primary_current=False, idempotency_key="another-request"),
    )
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]

    page = owner.get(f"/trees/{tree['id']}/people/{person['id']}/addresses?limit=1")
    assert page.status_code == 200
    assert len(page.json()["items"]) == 1
    assert page.json()["next_cursor"]
    next_page = owner.get(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        params={"limit": 1, "cursor": page.json()["next_cursor"]},
    )
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["id"] != page.json()["items"][0]["id"]


def test_concurrent_creates_preserve_idempotency_primary_and_preferred_invariants(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Concurrent")

    def together(*calls):  # type: ignore[no-untyped-def]
        ready = threading.Barrier(len(calls))

        def invoke(call):  # type: ignore[no-untyped-def]
            ready.wait(timeout=10)
            return call()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            return [future.result(timeout=20) for future in [pool.submit(invoke, call) for call in calls]]

    path = f"/trees/{tree['id']}/people/{person['id']}/addresses"
    same = lambda: owner.post(
        path,
        json=address_body(is_primary_current=False, idempotency_key="concurrent-retry"),
    )
    repeated = together(same, same)
    assert all(response.status_code == 201 for response in repeated), [r.text for r in repeated]
    assert len({response.json()["id"] for response in repeated}) == 1

    primary = together(
        lambda: owner.post(path, json=address_body(idempotency_key="primary-a", street="A")),
        lambda: owner.post(path, json=address_body(idempotency_key="primary-b", street="B")),
    )
    assert all(response.status_code == 201 for response in primary), [r.text for r in primary]
    addresses = owner.get(path).json()["items"]
    assert sum(item["is_primary_current"] for item in addresses) == 1

    contact_path = f"/trees/{tree['id']}/people/{person['id']}/contacts"
    preferred = together(
        lambda: owner.post(
            contact_path,
            json={"kind": "email", "value": "a@example.com", "is_preferred": True},
        ),
        lambda: owner.post(
            contact_path,
            json={"kind": "email", "value": "b@example.com", "is_preferred": True},
        ),
    )
    assert all(response.status_code == 201 for response in preferred), [r.text for r in preferred]
    contacts = owner.get(contact_path).json()["items"]
    assert sum(item["is_preferred"] for item in contacts) == 1

    legacy = together(
        lambda: owner.patch(
            f"/trees/{tree['id']}/people/{person['id']}",
            json={"residential_address": "Legacy address A"},
        ),
        lambda: owner.patch(
            f"/trees/{tree['id']}/people/{person['id']}",
            json={"residential_address": "Legacy address B"},
        ),
    )
    assert all(response.status_code == 200 for response in legacy), [r.text for r in legacy]
    with owner_session() as db:
        rows = db.scalars(
            select(PersonAddress).where(
                PersonAddress.person_id == person["id"],
                PersonAddress.legacy_imported.is_(True),
                PersonAddress.withdrawn_at.is_(None),
            )
        ).all()
        assert len(rows) == 1


def test_private_address_and_contact_are_not_disclosed_to_viewer(owner, tree, make_client):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Private", status="living")
    owner.post(f"/trees/{tree['id']}/people/{person['id']}/addresses", json=address_body())
    owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/contacts",
        json={"kind": "mobile", "value": "+919876543210"},
    )
    viewer = make_client()
    viewer.register()
    join_tree(owner, viewer, tree["id"], ["VIEWER"])
    assert viewer.get(f"/trees/{tree['id']}/people/{person['id']}/addresses").status_code == 403
    assert viewer.get(f"/trees/{tree['id']}/people/{person['id']}/contacts").status_code == 403

    contributor = make_client()
    contributor.register()
    join_tree(owner, contributor, tree["id"], ["CONTRIBUTOR"])
    denied_write = contributor.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses", json=address_body()
    )
    assert denied_write.status_code == 403

    other_tree = new_tree(owner, "Other family")
    other_person = create_person(owner, other_tree["id"], "Other tree person")
    assert owner.get(f"/trees/{tree['id']}/people/{other_person['id']}/addresses").status_code == 404


def test_address_requires_identifying_detail(owner, tree):  # type: ignore[no-untyped-def]
    person = create_person(owner, tree["id"], "Blank Address")
    blank = owner.post(
        f"/trees/{tree['id']}/people/{person['id']}/addresses",
        json={"purpose": "other", "status": "current", "country_code": "IN"},
    )
    assert blank.status_code == 422
