"""Transferring a shareable record to another member (ADR-0027 §2).

Shareable records are documents, tradition entries and photo collections. The owner offers a record to another
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
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models import Document, PhotoCollection, TraditionEntry, TreeMembership
from app.models.enums import GrantResource
from app.modules.ownership.schemas import OwnershipOfferOut, OwnershipOut

_MODELS: dict[GrantResource, Any] = {
    GrantResource.DOCUMENT: Document,
    GrantResource.TRADITION: TraditionEntry,
    GrantResource.COLLECTION: PhotoCollection,
}


def _live(model: Any) -> Any:
    """The SQL condition for a record that has not been deleted or withdrawn."""
    if model is Document:
        return Document.deleted_at.is_(None)
    if model is TraditionEntry:
        return TraditionEntry.withdrawn_at.is_(None)
    return PhotoCollection.id.is_not(None)  # collections are deleted outright


def _record(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> Any:
    """The record, locked for this transaction (``SELECT … FOR UPDATE``).

    Every ownership change and every takedown suspension (``takedown.service.suspend``) locks the
    record row first, so they are serialised: whichever commits first, the other sees its result
    (ADR-0027 §8.2 detail 9, the owner's decision of 9 Nov 2026).
    """
    model = _MODELS.get(GrantResource(resource_type))
    if model is None or ctx.public or ctx.membership_id is None:
        raise NotFound("Record not found")
    r = ctx.db.scalar(
        select(model)
        .where(model.tree_id == ctx.tree_id, model.id == resource_id, _live(model))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if r is None:
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


def _not_suspended(r: Any) -> None:
    """ADR-0027 §8.2 detail 9: a suspended record cannot be offered (its owner already knows it is
    suspended, so the owner is told why)."""
    if getattr(r, "suspended_at", None) is not None:
        raise Conflict("This record is suspended; its ownership cannot change now", code="record_suspended")


def cancel_offer_for_suspension(ctx: TreeContext, resource_type: GrantResource, r: Any) -> bool:
    """Called by a suspension, with the record already locked: any pending offer is cancelled in the
    same transaction. Audited as the system (no actor, no reason), like nothing else about the
    takedown; the member it was offered to is not told (an owner's cancellation tells nobody either).
    A fresh offer from the owner is needed after a lift."""
    if r.pending_owner_membership_id is None:
        return False
    r.pending_owner_membership_id = None
    ctx.db.flush()
    audit.record(
        ctx.db,
        action="record.ownership_offer_cancelled",
        actor_user_id=None,
        tree_id=ctx.tree_id,
        target_type=GrantResource(resource_type).value,
        target_id=r.id,
        details={"by": "system"},
    )
    return True


def offer(
    ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID, user_id: uuid.UUID
) -> OwnershipOut:
    r = _owned(ctx, resource_type, resource_id)
    _not_suspended(r)
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
    # a suspension cancels the offer, so a suspended record never has one; the check is kept so the
    # answer is the same 404 as "no offer" whatever happens, never a hint of the suspension
    if r.pending_owner_membership_id is None or r.pending_owner_membership_id != me or r.suspended_at:
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
    out: list[OwnershipOfferOut] = []
    for resource_type, model in _MODELS.items():
        rows: Any = ctx.db.scalars(
            select(model)
            .where(
                model.tree_id == ctx.tree_id,
                model.pending_owner_membership_id == me,
                model.suspended_at.is_(None),  # never list a suspended record (ADR-0027 §8.2)
                _live(model),
            )
            .order_by(model.created_at, model.id)
        )
        out += [OwnershipOfferOut(resource_type=resource_type, resource_id=r.id, title=r.title) for r in rows]
    return out
