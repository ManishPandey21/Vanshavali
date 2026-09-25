from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import select

from app.api.deps import TreeCtx
from app.api.schemas import ApiModel
from app.authz.permissions import Permission
from app.models import MergeRecord
from app.modules.merge import service

router = APIRouter(prefix="/trees/{tree_id}/merges", tags=["merge"])


class MergeIn(ApiModel):
    survivor_id: uuid.UUID
    merged_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=2000)


class MergeOut(ApiModel):
    id: uuid.UUID
    survivor_id: uuid.UUID
    merged_id: uuid.UUID
    reason: str | None
    change_count: int
    created_by: uuid.UUID | None
    created_at: dt.datetime
    reverted_at: dt.datetime | None


def _out(r: MergeRecord) -> MergeOut:
    return MergeOut(
        id=r.id,
        survivor_id=r.survivor_id,
        merged_id=r.merged_id,
        reason=r.reason,
        change_count=len(r.changes or []),
        created_by=r.created_by,
        created_at=r.created_at,
        reverted_at=r.reverted_at,
    )


@router.get("/preview")
def preview(ctx: TreeCtx, survivor: uuid.UUID = Query(), merged: uuid.UUID = Query()) -> dict[str, Any]:
    ctx.require(Permission.TREE_MANAGE)
    return service.preview(ctx, survivor, merged)


@router.post("", response_model=MergeOut, status_code=status.HTTP_201_CREATED)
def merge(body: MergeIn, ctx: TreeCtx) -> MergeOut:
    return _out(service.merge(ctx, body.survivor_id, body.merged_id, body.reason))


@router.get("", response_model=list[MergeOut])
def list_merges(ctx: TreeCtx) -> list[MergeOut]:
    ctx.require(Permission.TREE_MANAGE)
    rows = ctx.db.scalars(
        select(MergeRecord).where(MergeRecord.tree_id == ctx.tree_id).order_by(MergeRecord.created_at.desc())
    )
    return [_out(r) for r in rows]


@router.post("/{merge_id}/revert", response_model=MergeOut)
def revert(merge_id: uuid.UUID, ctx: TreeCtx) -> MergeOut:
    return _out(service.revert(ctx, merge_id))
