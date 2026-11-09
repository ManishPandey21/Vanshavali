"""OCR text, extraction proposals and their review (ADR-0009).

OCR text and proposals are document *content*: they follow the document's content rules (vault
permission / explicit download grant), not just metadata visibility.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select

from app.authz import records
from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Conflict, Unprocessable
from app.models import Document, ExtractionProposal
from app.models.enums import ProcessingStatus, ProposalStatus
from app.modules.documents import access
from app.modules.extraction import fields as F
from app.modules.extraction.apply import apply_proposal, time_source_for
from app.modules.extraction.masking import mask_value
from app.modules.extraction.pipeline import load_ocr_text
from app.modules.extraction.schemas import (
    OcrLineOut,
    OcrPageOut,
    OcrTextOut,
    ProposalOut,
    ReprocessOut,
    ReviewIn,
)
from app.modules.genealogy import lookup

VALUE_LABEL = {
    ProposalStatus.PENDING: "extracted",
    ProposalStatus.ACCEPTED: "source-verified",  # value accepted exactly as the document states it
    ProposalStatus.EDITED: "user-confirmed",
    ProposalStatus.REJECTED: "rejected",
}


def proposal_out(p: ExtractionProposal) -> ProposalOut:
    return ProposalOut.model_validate(p).model_copy(update={"value_label": VALUE_LABEL[p.status]})


def _content_doc(ctx: TreeContext, document_id: uuid.UUID) -> Document:
    doc = access.get_document(ctx, document_id)
    access.require_content(ctx, doc)
    return doc


def ocr_text(ctx: TreeContext, document_id: uuid.UUID) -> OcrTextOut:
    doc = _content_doc(ctx, document_id)
    result = load_ocr_text(ctx.db, doc) if doc.ocr_status == ProcessingStatus.COMPLETED else None
    audit.log(ctx, "document.ocr_text_viewed", target_type="document", target_id=doc.id)
    if result is None:
        return OcrTextOut(document_id=doc.id, status=doc.ocr_status, engine=doc.ocr_engine)
    return OcrTextOut(
        document_id=doc.id,
        status=doc.ocr_status,
        engine=result.engine_label,
        confidence=result.confidence,
        text=result.text,
        pages=[
            OcrPageOut(
                page=pg.page,
                lines=[
                    OcrLineOut(line_no=ln.line_no, text=ln.text, confidence=ln.confidence) for ln in pg.lines
                ],
            )
            for pg in result.pages
        ],
    )


def list_proposals(
    ctx: TreeContext, document_id: uuid.UUID, status: ProposalStatus | None = None
) -> list[ProposalOut]:
    doc = _content_doc(ctx, document_id)
    stmt = select(ExtractionProposal).where(
        ExtractionProposal.tree_id == ctx.tree_id, ExtractionProposal.document_id == doc.id
    )
    if status is not None:
        stmt = stmt.where(ExtractionProposal.status == status)
    rows = ctx.db.scalars(stmt.order_by(ExtractionProposal.created_at, ExtractionProposal.id)).all()
    # SEC-13: proposals carry document content (DOB, registration numbers) — reads are audited like OCR text
    audit.log(
        ctx,
        "document.proposals_viewed",
        target_type="document",
        target_id=doc.id,
        details={"count": len(rows)},
    )
    return [proposal_out(p) for p in rows]


def reprocess(ctx: TreeContext, document_id: uuid.UUID) -> ReprocessOut:
    ctx.require(Permission.DOCUMENT_MANAGE)
    doc = _content_doc(ctx, document_id)
    records.require_owner_for_private(access.is_owner(ctx, doc), doc.privacy_level)
    from app.modules.documents.previews import supports_preview
    from app.modules.documents.service import schedule_processing

    doc.preview_status = (
        ProcessingStatus.PENDING if supports_preview(doc.mime_type) else ProcessingStatus.SKIPPED
    )
    if supports_preview(doc.mime_type):
        doc.ocr_status = ProcessingStatus.PENDING
        doc.extraction_status = ProcessingStatus.PENDING
    audit.log(ctx, "document.reprocess_requested", target_type="document", target_id=doc.id)
    schedule_processing(ctx, doc, force_ocr=True)
    pending = ctx.db.scalar(
        select(func.count())
        .select_from(ExtractionProposal)
        .where(
            ExtractionProposal.tree_id == ctx.tree_id,
            ExtractionProposal.document_id == doc.id,
            ExtractionProposal.status == ProposalStatus.PENDING,
        )
    )
    return ReprocessOut(
        document_id=doc.id,
        preview_status=doc.preview_status,
        ocr_status=doc.ocr_status,
        extraction_status=doc.extraction_status,
        pending_proposals=int(pending or 0),
    )


def review(ctx: TreeContext, proposal_id: uuid.UUID, body: ReviewIn) -> ExtractionProposal:
    ctx.require(Permission.EXTRACTION_REVIEW)
    p = lookup.get_in_tree(ctx, ExtractionProposal, proposal_id, "Proposal")
    doc = _content_doc(ctx, p.document_id)
    records.require_owner_for_private(access.is_owner(ctx, doc), doc.privacy_level)
    if p.status != ProposalStatus.PENDING:
        raise Conflict("This proposal has already been reviewed", code="already_reviewed")
    now = dt.datetime.now(dt.UTC)
    if body.action == "reject":
        p.status = ProposalStatus.REJECTED
    else:
        if body.action == "accept":
            value = p.proposed_value
        else:
            value = F.coerce(p.field, body.value, time_source=time_source_for(p))
        value = mask_value(value)
        if value is None:
            raise Unprocessable("This proposal has no value to apply")
        applied = apply_proposal(
            ctx,
            p,
            doc,
            value,
            now=now,
            target_person_id=body.target_person_id,
            target_property_id=body.target_property_id,
            target_parcel_id=body.target_parcel_id,
        )
        p.status = ProposalStatus.ACCEPTED if body.action == "accept" else ProposalStatus.EDITED
        p.final_value = value
        p.applied_target_type = applied.target_type
        p.applied_target_id = applied.target_id
    p.reviewed_by = ctx.user_id
    p.reviewed_at = now
    p.review_note = body.note
    p.updated_by = ctx.user_id
    ctx.db.flush()
    audit.log(
        ctx,
        "extraction.proposal_reviewed",
        target_type="document",
        target_id=doc.id,
        details={
            "proposal_id": str(p.id),
            "field": p.field,
            "action": body.action,
            "applied_target_type": p.applied_target_type,
        },
    )
    return p
