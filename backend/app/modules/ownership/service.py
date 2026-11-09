"""Transferring a shareable record to another member (ADR-0027 §2).

Shareable records are documents and tradition entries. The owner offers a record to another
member, who becomes the owner only when they accept. The owner can cancel the offer; the member
can decline it. Nobody else can transfer, claim or accept a record, so an orphaned record (its
owner left) stays with its grantees. Every step is audited without titles or contents (§11).
Anyone who is neither the owner nor the member offered the record gets 404.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import is_record_owner
from app.core import audit
from app.core.errors import NotFound, Unprocessable
from app.models import Document, TraditionEntry, TreeMembership
from app.models.enums import GrantResource
from app.modules.ownership.schemas import OwnershipOfferOut, OwnershipOut

_MODELS: dict[GrantResource, Any] = {
    GrantResource.DOCUMENT: Document,
    GrantResource.TRADITION: TraditionEntry,
}


def _record(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> Any:
    model = _MODELS.get(GrantResource(resource_type))
    if model is None or ctx.public or ctx.membership_id is None:
        raise NotFound("Record not found")
    r = ctx.db.scalar(select(model).where(model.tree_id == ctx.tree_id, model.id == resource_id))
    live = r is not None and (r.deleted_at is None if model is Document else r.withdrawn_at is None)
    if not live:
        raise NotFound("Record not found")
    return r


def _owned(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> Any:
    r = _record(ctx, resource_type, resource_id)
    if not is_record_owner(ctx, r.owner_membership_id):
        raise NotFound("Record not found")
    return r


def _out(resource_type: GrantResource, r: Any) -> OwnershipOut:
    return OwnershipOut(
        resource_type=resource_type,
        resource_id=r.id,
        owner_membership_id=r.owner_membership_id,
        pending_owner_membership_id=r.pending_owner_membership_id,
    )


def _audit(ctx: TreeContext, action: str, resource_type: GrantResource, r: Any, **details: Any) -> None:
    audit.log(
        ctx, action, target_type=GrantResource(resource_type).value, target_id=r.id, details=details or None
    )


def offer(
    ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID, user_id: uuid.UUID
) -> OwnershipOut:
    r = _owned(ctx, resource_type, resource_id)
    target = ctx.db.scalar(
        select(TreeMembership).where(TreeMembership.tree_id == ctx.tree_id, TreeMembership.user_id == user_id)
    )
    if target is None:
        raise NotFound("Ownership can only be offered to a member of this tree")
    if target.id == r.owner_membership_id:
        raise Unprocessable("You already own this", code="already_owner")
    r.pending_owner_membership_id = target.id
    ctx.db.flush()
    _audit(ctx, "record.ownership_offered", resource_type, r, to_membership=str(target.id))
    return _out(resource_type, r)


def accept(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> OwnershipOut:
    r = _record(ctx, resource_type, resource_id)
    me = ctx.membership_id
    if r.pending_owner_membership_id is None or r.pending_owner_membership_id != me:
        raise NotFound("Record not found")
    previous = r.owner_membership_id
    r.owner_membership_id = me
    r.pending_owner_membership_id = None
    ctx.db.flush()
    _audit(
        ctx,
        "record.ownership_transferred",
        resource_type,
        r,
        from_membership=str(previous) if previous else None,
        to_membership=str(me),
    )
    return _out(resource_type, r)


def withdraw_offer(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> None:
    """The owner cancels the offer, or the member it was offered to declines it."""
    r = _record(ctx, resource_type, resource_id)
    me = ctx.membership_id
    if r.pending_owner_membership_id is None or me not in (
        r.owner_membership_id,
        r.pending_owner_membership_id,
    ):
        raise NotFound("Record not found")
    declined = me == r.pending_owner_membership_id
    r.pending_owner_membership_id = None
    ctx.db.flush()
    _audit(
        ctx, "record.ownership_declined" if declined else "record.ownership_offer_cancelled", resource_type, r
    )


def offers_for_me(ctx: TreeContext) -> list[OwnershipOfferOut]:
    me = ctx.membership_id
    if me is None or ctx.public:
        return []
    docs = ctx.db.scalars(
        select(Document).where(
            Document.tree_id == ctx.tree_id,
            Document.pending_owner_membership_id == me,
            Document.deleted_at.is_(None),
        )
    )
    entries = ctx.db.scalars(
        select(TraditionEntry).where(
            TraditionEntry.tree_id == ctx.tree_id,
            TraditionEntry.pending_owner_membership_id == me,
            TraditionEntry.withdrawn_at.is_(None),
        )
    )
    return [
        *(
            OwnershipOfferOut(resource_type=GrantResource.DOCUMENT, resource_id=d.id, title=d.title)
            for d in docs
        ),
        *(
            OwnershipOfferOut(resource_type=GrantResource.TRADITION, resource_id=e.id, title=e.title)
            for e in entries
        ),
    ]
