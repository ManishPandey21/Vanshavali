"""OCR → masked OCR-text derivative → extraction proposals (ADR-0009). Never writes canonical data."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.storage import get_store
from app.models import Document, DocumentLink, ExtractionProposal
from app.models.enums import DerivativeKind, DocumentLinkTarget, ProcessingStatus, ProposalStatus
from app.modules.extraction.extractors import extractor_for
from app.modules.extraction.masking import mask_aadhaar, mask_value
from app.modules.extraction.ocr import OcrError, OcrLine, OcrPage, OcrResult, run_ocr

OCR_TEXT_MIME = "application/json"


def masked(result: OcrResult) -> OcrResult:
    return OcrResult(
        pages=[
            OcrPage(p.page, [OcrLine(ln.line_no, mask_aadhaar(ln.text), ln.confidence) for ln in p.lines])
            for p in result.pages
        ],
        engine=result.engine,
        version=result.version,
    )


def load_ocr_text(db: Session, doc: Document) -> OcrResult | None:
    from app.modules.documents.service import derivative

    d = derivative(db, doc, DerivativeKind.OCR_TEXT)
    if d is None:
        return None
    return OcrResult.from_json(json.loads(get_store().get(d.storage_key)))


def linked_subjects(db: Session, doc: Document) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """The single linked person / property, if exactly one of each kind is linked."""
    rows = db.execute(
        select(DocumentLink.target_type, DocumentLink.target_id).where(
            DocumentLink.tree_id == doc.tree_id,
            DocumentLink.document_id == doc.id,
            DocumentLink.target_type.in_([DocumentLinkTarget.PERSON, DocumentLinkTarget.PROPERTY]),
        )
    ).all()
    persons = {tid for tt, tid in rows if tt == DocumentLinkTarget.PERSON}
    props = {tid for tt, tid in rows if tt == DocumentLinkTarget.PROPERTY}
    return (
        next(iter(persons)) if len(persons) == 1 else None,
        next(iter(props)) if len(props) == 1 else None,
    )


def _key(field: str, value: Any) -> str:
    return f"{field}:{json.dumps(value, sort_keys=True, ensure_ascii=False)}"


def ocr_and_extract(db: Session, doc: Document, data: bytes) -> None:
    from app.modules.documents.service import put_derivative

    doc.ocr_status = ProcessingStatus.RUNNING
    db.flush()
    try:
        raw = run_ocr(data, doc.mime_type)
    except OcrError as exc:
        doc.ocr_status = ProcessingStatus.FAILED
        doc.ocr_error = str(exc)[:500]
        doc.extraction_status = ProcessingStatus.SKIPPED
        return
    result = masked(raw)  # Aadhaar numbers never reach storage
    payload = json.dumps(result.to_json(), ensure_ascii=False).encode()
    put_derivative(db, doc, DerivativeKind.OCR_TEXT, payload, OCR_TEXT_MIME, engine=result.engine_label[:120])
    doc.ocr_status = ProcessingStatus.COMPLETED
    doc.ocr_engine = result.engine_label[:120]
    doc.ocr_error = None
    doc.page_count = doc.page_count or len(result.pages)

    extractor = extractor_for(doc.category)
    if extractor is None:
        doc.extraction_status = ProcessingStatus.NOT_REQUESTED
        return
    doc.extraction_status = ProcessingStatus.RUNNING
    drafts = extractor.extract(result)
    # a re-run replaces unreviewed proposals; reviewed ones are history and stay
    db.execute(
        delete(ExtractionProposal).where(
            ExtractionProposal.tree_id == doc.tree_id,
            ExtractionProposal.document_id == doc.id,
            ExtractionProposal.status == ProposalStatus.PENDING,
        )
    )
    reviewed = {
        _key(f, v)
        for f, v in db.execute(
            select(ExtractionProposal.field, ExtractionProposal.proposed_value).where(
                ExtractionProposal.tree_id == doc.tree_id, ExtractionProposal.document_id == doc.id
            )
        ).all()
    }
    person_id, property_id = linked_subjects(db, doc)
    for d in drafts:
        value = mask_value(d.value)
        if _key(d.field, value) in reviewed:
            continue
        db.add(
            ExtractionProposal(
                tree_id=doc.tree_id,
                document_id=doc.id,
                subject_person_id=person_id,
                subject_property_id=property_id,
                extractor=extractor.name,
                extractor_version=extractor.version,
                engine=result.engine_label[:120],
                field=d.field,
                label=d.label,
                proposed_value=value,
                display_value=mask_aadhaar(d.display)[:2000],
                confidence=d.confidence,
                source_location=d.location,
            )
        )
    doc.extraction_status = ProcessingStatus.COMPLETED
    db.flush()
