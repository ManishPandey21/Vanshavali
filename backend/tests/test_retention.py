"""Retention purge of soft-deleted documents and the orphaned-object sweep (ADR-0004 §7).

Both run through the ordinary (restricted, RLS-subject) application sessions, as they do in production.
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.storage import LocalObjectStore
from app.models import (
    AuditEvent,
    Document,
    DocumentDerivative,
    DocumentLink,
    DocumentMetadataVersion,
    ExtractionProposal,
    Source,
)
from app.modules.documents import retention
from tests.conftest import owner_session
from tests.doc_fixtures import png_bytes, text_image, upload
from tests.helpers import create_person

LATER = dt.datetime.now(dt.UTC) + dt.timedelta(days=31)


def _doc(owner, t, person_id, title="Birth certificate of Kamala"):  # type: ignore[no-untyped-def]
    r = upload(
        owner,
        t,
        png_bytes(text_image([title, "Registration No. 1234"], width=900)),
        filename="bc.png",
        mime="image/png",
        category="birth_certificate",
        title=title,
        link_target_type="person",
        link_target_id=person_id,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _keys(doc_id: str) -> list[str]:
    with owner_session() as db:
        doc = db.get(Document, uuid.UUID(doc_id))
        assert doc is not None
        derivs = db.scalars(
            select(DocumentDerivative.storage_key).where(DocumentDerivative.document_id == doc.id)
        )
        return [doc.storage_key, *derivs]


def _stored(key: str) -> bool:
    return (Path(get_settings().storage_local_path) / key).exists()


def test_purge_removes_expired_deleted_documents_only(owner, tree):
    t = tree["id"]
    person = create_person(owner, t, "Kamala")
    old = _doc(owner, t, person["id"])
    recent = _doc(owner, t, person["id"], title="Recent deletion")
    live = _doc(owner, t, person["id"], title="Still in use")
    src = owner.post(f"/trees/{t}/sources", json={"title": "Municipal register", "document_id": old["id"]})
    assert src.status_code == 201, src.text
    assert owner.patch(f"/trees/{t}/documents/{old['id']}", json={"title": "Renamed"}).status_code == 200
    old_keys = _keys(old["id"])
    assert all(_stored(k) for k in old_keys)

    assert owner.delete(f"/trees/{t}/documents/{old['id']}").status_code == 200
    assert owner.delete(f"/trees/{t}/documents/{recent['id']}").status_code == 200
    with owner_session() as db:  # backdate the first deletion past the retention window
        db.get(Document, uuid.UUID(old["id"])).deleted_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=40)  # type: ignore[union-attr]
        db.commit()

    assert retention.purge_deleted_documents() == 1
    assert retention.purge_deleted_documents() == 0  # idempotent

    oid = uuid.UUID(old["id"])
    with owner_session() as db:
        assert db.get(Document, oid) is None
        for model in (DocumentDerivative, DocumentLink, DocumentMetadataVersion, ExtractionProposal):
            assert db.scalars(select(model).where(model.document_id == oid)).all() == []  # type: ignore[attr-defined]
        source = db.get(Source, uuid.UUID(src.json()["id"]))
        assert source is not None and source.document_id is None  # the source survives, unlinked
        purged = db.scalars(select(AuditEvent).where(AuditEvent.action == "document.purged")).all()
        assert [e.target_id for e in purged] == [oid]
        assert "Birth certificate" not in str(purged[0].details) and purged[0].summary is None
        assert db.get(Document, uuid.UUID(recent["id"])) is not None
        assert db.get(Document, uuid.UUID(live["id"])) is not None
    assert not any(_stored(k) for k in old_keys)
    assert all(_stored(k) for k in _keys(recent["id"]))
    # the recently deleted document can still be restored
    assert owner.post(f"/trees/{t}/documents/{recent['id']}/restore").status_code == 200
    assert owner.get(f"/trees/{t}/documents/{live['id']}").status_code == 200


def test_purge_window_is_configurable(owner, tree):
    t = tree["id"]
    person = create_person(owner, t, "Kamala")
    doc = _doc(owner, t, person["id"])
    assert owner.delete(f"/trees/{t}/documents/{doc['id']}").status_code == 200
    assert retention.purge_deleted_documents() == 0
    assert retention.purge_deleted_documents(now=LATER) == 1
    assert owner.post(f"/trees/{t}/documents/{doc['id']}/restore").status_code == 404


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    store = LocalObjectStore(str(tmp_path))
    monkeypatch.setattr(retention, "get_store", lambda: store)
    return store


def _put(store: LocalObjectStore, key: str, age_hours: float) -> None:
    store.put_immutable(key, b"data", key_id="STANDARD")
    ts = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=age_hours)).timestamp()
    os.utime(Path(store.root) / key, (ts, ts))


def test_orphan_sweep_is_dry_run_by_default_and_spares_referenced_and_recent(owner, tree, isolated_store):
    t = tree["id"]
    person = create_person(owner, t, "Kamala")
    referenced = _keys(_doc(owner, t, person["id"])["id"])
    for key in referenced:
        _put(isolated_store, key, age_hours=48)
    stray = f"STANDARD/{t}/ab/{uuid.uuid4()}/original"
    fresh = f"STANDARD/{t}/ab/{uuid.uuid4()}/original"
    gone_tree = f"VAULT/{uuid.uuid4()}/cd/{uuid.uuid4()}/original"  # tree no longer exists
    foreign = "backups/manual-note.txt"  # not the app's layout: never touched
    _put(isolated_store, stray, 48)
    _put(isolated_store, fresh, 1)
    _put(isolated_store, gone_tree, 48)
    _put(isolated_store, foreign, 48)

    dry = retention.sweep_orphaned_objects()
    assert sorted(dry.orphaned) == sorted([stray, gone_tree])
    assert dry.too_recent == 1 and dry.deleted == 0
    assert isolated_store.exists(stray)

    done = retention.sweep_orphaned_objects(delete_objects=True)
    assert done.deleted == 2
    assert not isolated_store.exists(stray) and not isolated_store.exists(gone_tree)
    for key in [*referenced, fresh, foreign]:
        assert isolated_store.exists(key), key


def test_maintenance_cli(owner, tree, isolated_store, capsys):  # type: ignore[no-untyped-def]
    from app.cli.maintenance import main

    _put(isolated_store, f"STANDARD/{tree['id']}/ab/{uuid.uuid4()}/original", 48)
    assert main(["sweep-orphans"]) == 0
    assert "orphaned 1" in capsys.readouterr().out
    assert main(["purge-deleted-documents"]) == 0
    assert "purged 0 document(s)" in capsys.readouterr().out
