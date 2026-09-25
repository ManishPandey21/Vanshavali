from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import TreeCtx
from app.models.enums import ProposalStatus
from app.modules.extraction import service
from app.modules.extraction.schemas import OcrTextOut, ProposalOut, ReprocessOut, ReviewIn

router = APIRouter(prefix="/trees/{tree_id}", tags=["extraction"])


@router.get("/documents/{document_id}/ocr-text", response_model=OcrTextOut)
def ocr_text(document_id: uuid.UUID, ctx: TreeCtx) -> OcrTextOut:
    return service.ocr_text(ctx, document_id)


@router.get("/documents/{document_id}/proposals", response_model=list[ProposalOut])
def list_proposals(
    document_id: uuid.UUID, ctx: TreeCtx, status: ProposalStatus | None = None
) -> list[ProposalOut]:
    return service.list_proposals(ctx, document_id, status)


@router.post("/documents/{document_id}/reprocess", response_model=ReprocessOut)
def reprocess(document_id: uuid.UUID, ctx: TreeCtx) -> ReprocessOut:
    return service.reprocess(ctx, document_id)


@router.post("/extraction-proposals/{proposal_id}/review", response_model=ProposalOut)
def review(proposal_id: uuid.UUID, body: ReviewIn, ctx: TreeCtx) -> ProposalOut:
    """Accept, edit or reject one proposal. Only this endpoint turns extracted values into facts."""
    return service.proposal_out(service.review(ctx, proposal_id, body))
