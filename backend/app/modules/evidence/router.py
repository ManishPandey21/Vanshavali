from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import TreeCtx
from app.api.schemas import Message, Page, decode_cursor, encode_cursor
from app.authz.permissions import Permission
from app.core import audit
from app.models import Citation, Source
from app.models.enums import CitationTarget, SourceType
from app.modules.evidence import service
from app.modules.evidence.schemas import CitationIn, CitationOut, SourceIn, SourceOut, SourceUpdate
from app.modules.genealogy import lookup

router = APIRouter(prefix="/trees/{tree_id}", tags=["evidence"])


def _source_out(ctx, s: Source) -> SourceOut:  # type: ignore[no-untyped-def]
    return SourceOut.model_validate(s).model_copy(
        update={"citation_count": service.citation_count(ctx, s.id)}
    )


@router.get("/sources", response_model=Page[SourceOut])
def list_sources(
    ctx: TreeCtx,
    q: str | None = Query(default=None, max_length=200),
    source_type: SourceType | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[SourceOut]:
    offset = decode_cursor(cursor)
    stmt = select(Source).where(Source.tree_id == ctx.tree_id)
    if q:
        stmt = stmt.where(Source.title.ilike(f"%{q}%"))
    if source_type:
        stmt = stmt.where(Source.source_type == source_type)
    rows = [
        s for s in ctx.db.scalars(stmt.order_by(Source.created_at.desc())) if service.can_view_source(ctx, s)
    ]
    page = rows[offset : offset + limit]
    return Page(
        items=[_source_out(ctx, s) for s in page],
        next_cursor=encode_cursor(offset + limit) if len(rows) > offset + limit else None,
    )


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(body: SourceIn, ctx: TreeCtx) -> SourceOut:
    return _source_out(ctx, service.create_source(ctx, body))


@router.get("/sources/{source_id}", response_model=SourceOut)
def get_source(source_id: uuid.UUID, ctx: TreeCtx) -> SourceOut:
    return _source_out(ctx, service.get_source(ctx, source_id))


@router.patch("/sources/{source_id}", response_model=SourceOut)
def update_source(source_id: uuid.UUID, body: SourceUpdate, ctx: TreeCtx) -> SourceOut:
    return _source_out(ctx, service.update_source(ctx, source_id, body))


@router.post("/citations", response_model=CitationOut, status_code=status.HTTP_201_CREATED)
def add_citation(body: CitationIn, ctx: TreeCtx) -> CitationOut:
    c = service.add_citation(ctx, body)
    s = service.get_source(ctx, c.source_id)
    return CitationOut.model_validate(c).model_copy(update={"source_title": s.title})


@router.get("/citations", response_model=list[CitationOut])
def list_citations(ctx: TreeCtx, target_type: CitationTarget, target_id: uuid.UUID) -> list[CitationOut]:
    return [
        CitationOut.model_validate(c).model_copy(update={"source_title": s.title})
        for c, s in service.citations_for(ctx, target_type, target_id)
    ]


@router.delete("/citations/{citation_id}", response_model=Message)
def delete_citation(citation_id: uuid.UUID, ctx: TreeCtx) -> Message:
    ctx.require(Permission.SOURCE_WRITE)
    c = lookup.get_in_tree(ctx, Citation, citation_id, "Citation")
    service.get_source(ctx, c.source_id)
    ctx.db.delete(c)
    audit.log(ctx, "citation.removed", target_type=c.target_type.value, target_id=c.target_id)
    return Message(message="Citation removed")
