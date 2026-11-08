"""Family traditions archive (ADR-0026 §7). Members only; never on public trees."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import TreeCtx
from app.api.schemas import Message, decode_cursor, encode_cursor
from app.models.enums import TraditionKind
from app.modules.traditions import service
from app.modules.traditions.schemas import (
    TraditionEntryIn,
    TraditionEntryUpdate,
    TraditionOut,
    TraditionRevisionOut,
    TraditionsOut,
)

router = APIRouter(prefix="/trees/{tree_id}", tags=["traditions"])


@router.get("/traditions", response_model=TraditionsOut)
def list_traditions(
    ctx: TreeCtx,
    kind: TraditionKind | None = None,
    person_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    q: str = Query(default="", max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> TraditionsOut:
    """Entries the reader may see, newest first; ``q`` searches titles and text in any script."""
    offset = decode_cursor(cursor)
    items, more = service.list_entries(
        ctx, kind=kind, person_id=person_id, branch_id=branch_id, q=q, offset=offset, limit=limit
    )
    return TraditionsOut(items=items, next_cursor=encode_cursor(offset + limit) if more else None)


@router.post("/traditions", response_model=TraditionOut, status_code=status.HTTP_201_CREATED)
def create_tradition(body: TraditionEntryIn, ctx: TreeCtx) -> TraditionOut:
    return service.entry_out(ctx, service.create_entry(ctx, body))


@router.get("/traditions/{entry_id}", response_model=TraditionOut)
def get_tradition(entry_id: uuid.UUID, ctx: TreeCtx) -> TraditionOut:
    return service.entry_out(ctx, service.get_entry(ctx, entry_id))


@router.patch("/traditions/{entry_id}", response_model=TraditionOut)
def update_tradition(entry_id: uuid.UUID, body: TraditionEntryUpdate, ctx: TreeCtx) -> TraditionOut:
    """Edit an entry. Someone else's entry follows the tree's review policy (409 review_required:
    send it as a proposed change)."""
    return service.entry_out(ctx, service.update_entry(ctx, entry_id, body))


@router.delete("/traditions/{entry_id}", response_model=Message)
def withdraw_tradition(entry_id: uuid.UUID, ctx: TreeCtx) -> Message:
    """Withdraw an entry (author or tree admin); its history is kept."""
    service.withdraw_entry(ctx, entry_id)
    return Message(message="Tradition withdrawn")


@router.get("/traditions/{entry_id}/history", response_model=list[TraditionRevisionOut])
def tradition_history(entry_id: uuid.UUID, ctx: TreeCtx) -> list[TraditionRevisionOut]:
    return service.history(ctx, entry_id)
