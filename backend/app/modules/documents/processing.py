"""Background processing for an uploaded document: previews, then OCR + extraction proposals.

Runs in the RQ worker (or inline when ``JOB_MODE=sync``) with its own DB session. Failures are
recorded on the document's status columns; error messages never include document content.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.storage import StorageError, get_store
from app.models import Document
from app.models.enums import DerivativeKind, ProcessingStatus
from app.modules.documents.previews import render_previews, supports_preview

log = logging.getLogger(__name__)


def process_document(document_id: str, tree_id: str, force_ocr: bool = False) -> None:
    from app.modules.documents.service import put_derivative, wants_ocr
    from app.modules.extraction.pipeline import ocr_and_extract

    with get_sessionmaker()() as db:
        doc = db.scalar(
            select(Document).where(
                Document.tree_id == uuid.UUID(tree_id), Document.id == uuid.UUID(document_id)
            )
        )
        if doc is None or doc.deleted_at is not None:
            return
        try:
            data = get_store().get(doc.storage_key)
        except StorageError:
            log.error("document %s: original could not be read from storage", doc.id)
            doc.preview_status = ProcessingStatus.FAILED
            if doc.ocr_status == ProcessingStatus.PENDING:
                doc.ocr_status = ProcessingStatus.FAILED
                doc.ocr_error = "The stored original could not be read"
            db.commit()
            return

        # ---- previews
        if supports_preview(doc.mime_type):
            doc.preview_status = ProcessingStatus.RUNNING
            db.flush()
            try:
                for r in render_previews(data, doc.mime_type):
                    put_derivative(db, doc, DerivativeKind(r.kind), r.data, r.mime, engine="pillow")
                doc.preview_status = ProcessingStatus.COMPLETED
            except Exception as exc:  # corrupt/unsupported image data must not break the pipeline
                log.warning("document %s: preview failed (%s)", doc.id, type(exc).__name__)
                db.rollback()
                reloaded = db.get(Document, doc.id)
                if reloaded is None:  # document removed meanwhile; nothing left to process
                    return
                doc = reloaded
                doc.preview_status = ProcessingStatus.FAILED
        else:
            doc.preview_status = ProcessingStatus.SKIPPED
        db.commit()

        # ---- OCR + extraction
        if wants_ocr(doc) or (force_ocr and supports_preview(doc.mime_type)):
            try:
                ocr_and_extract(db, doc, data)
                db.commit()
            except Exception as exc:
                log.warning("document %s: OCR/extraction failed (%s)", doc.id, type(exc).__name__)
                db.rollback()
                reloaded = db.get(Document, doc.id)
                if reloaded is None:
                    return
                doc = reloaded
                doc.ocr_status = ProcessingStatus.FAILED
                doc.ocr_error = f"Processing failed ({type(exc).__name__})"
                doc.extraction_status = ProcessingStatus.FAILED
                db.commit()
