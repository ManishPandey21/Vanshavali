"""Storage maintenance: purge expired soft-deleted documents and sweep orphaned objects (ADR-0004 §7).

Both routines work tree by tree with the tree bound for row-level security, so they run correctly
as the restricted application role. They also work as the table owner. Entry point:
``python -m app.cli.maintenance``.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.db import bind_tree, get_sessionmaker
from app.core.storage import StorageError, get_store
from app.models import (
    Document,
    DocumentDerivative,
    DocumentLink,
    DocumentMetadataVersion,
    ExportJob,
    ExtractionProposal,
    ImportJob,
    Tree,
)

log = logging.getLogger(__name__)


def _tree_ids(db: Session) -> list[uuid.UUID]:
    return list(db.scalars(select(Tree.id)))


# ---------------------------------------------------------------- retention purge
def purge_deleted_documents(*, now: dt.datetime | None = None, older_than_days: int | None = None) -> int:
    """Permanently remove documents soft-deleted more than ``older_than_days`` ago.

    Removes the encrypted original and all derivatives (every stored version), then deletes the
    document row with its links, metadata history and extraction proposals. Citations, astrology
    profiles, consent records and import jobs keep their rows; their document reference becomes NULL
    (FK ``ON DELETE SET NULL``). Canonical facts that were accepted from a proposal keep their audit
    trail. Each purge is audited without the title, which may itself be sensitive.
    """
    now = now or dt.datetime.now(dt.UTC)
    days = get_settings().document_purge_after_days if older_than_days is None else older_than_days
    cutoff = now - dt.timedelta(days=days)
    store = get_store()
    purged = 0
    maker = get_sessionmaker()
    with maker() as db:
        trees = _tree_ids(db)
    for tree_id in trees:
        with maker() as db:
            bind_tree(db, tree_id)
            docs = db.scalars(
                select(Document).where(
                    Document.tree_id == tree_id,
                    Document.deleted_at.is_not(None),
                    Document.deleted_at < cutoff,
                )
            ).all()
            for doc in docs:
                derivs = db.scalars(
                    select(DocumentDerivative).where(
                        DocumentDerivative.tree_id == tree_id, DocumentDerivative.document_id == doc.id
                    )
                ).all()
                keys = [doc.storage_key, *(d.storage_key for d in derivs)]
                for model in (DocumentDerivative, DocumentLink, DocumentMetadataVersion, ExtractionProposal):
                    db.execute(
                        delete(model).where(model.tree_id == tree_id, model.document_id == doc.id)  # type: ignore[attr-defined]
                    )
                audit.record(
                    db,
                    action="document.purged",
                    actor_user_id=None,
                    tree_id=tree_id,
                    target_type="document",
                    target_id=doc.id,
                    details={"deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None},
                )
                db.delete(doc)
                db.flush()
                # Remove objects only once the rows are gone in this transaction; if storage fails the
                # transaction rolls back, and the next run retries (purge is idempotent).
                for key in keys:
                    store.purge(key)
                db.commit()
                purged += 1
    if purged:
        log.info("retention purge removed %d document(s)", purged)
    return purged


# ---------------------------------------------------------------- orphan sweep
@dataclass
class SweepResult:
    scanned: int = 0
    orphaned: list[str] = field(default_factory=list)
    too_recent: int = 0
    deleted: int = 0


def _tree_of(key: str) -> uuid.UUID | None:
    # Every key the app writes is "<CLASS>/<tree_id>/...".
    parts = key.split("/")
    if len(parts) < 3:
        return None
    try:
        return uuid.UUID(parts[1])
    except ValueError:
        return None


def _referenced_keys(db: Session, tree_id: uuid.UUID) -> set[str]:
    refs: set[str] = set()
    refs.update(db.scalars(select(Document.storage_key).where(Document.tree_id == tree_id)))
    refs.update(
        db.scalars(select(DocumentDerivative.storage_key).where(DocumentDerivative.tree_id == tree_id))
    )
    refs.update(
        k for k in db.scalars(select(ImportJob.original_storage_key).where(ImportJob.tree_id == tree_id)) if k
    )
    refs.update(k for k in db.scalars(select(ExportJob.storage_key).where(ExportJob.tree_id == tree_id)) if k)
    return refs


def sweep_orphaned_objects(
    *, delete_objects: bool = False, min_age_hours: int = 24, now: dt.datetime | None = None
) -> SweepResult:
    """Find stored objects that no database row references; optionally delete them.

    Objects younger than ``min_age_hours`` are never touched: an upload writes the object before its
    transaction commits. Keys that don't follow the app's layout are reported but never deleted.
    Dry run by default.
    """
    now = now or dt.datetime.now(dt.UTC)
    min_age = dt.timedelta(hours=min_age_hours)
    store = get_store()
    result = SweepResult()
    by_tree: dict[uuid.UUID | None, list[tuple[str, dt.datetime]]] = {}
    for key, modified in store.iter_objects():
        result.scanned += 1
        by_tree.setdefault(_tree_of(key), []).append((key, modified))
    maker = get_sessionmaker()
    with maker() as db:
        existing = set(_tree_ids(db))
    for tree_id, objects in by_tree.items():
        if tree_id is None:
            for key, _ in objects:
                log.warning("orphan sweep: unrecognised key layout, left in place: %s", key)
            continue
        refs: set[str] = set()
        if tree_id in existing:
            with maker() as db:
                bind_tree(db, tree_id)
                refs = _referenced_keys(db, tree_id)
        for key, modified in objects:
            if key in refs:
                continue
            if now - modified < min_age:
                result.too_recent += 1
                continue
            result.orphaned.append(key)
            if delete_objects:
                try:
                    store.purge(key)
                    result.deleted += 1
                except StorageError:
                    log.exception("orphan sweep: could not delete %s", key)
    return result
