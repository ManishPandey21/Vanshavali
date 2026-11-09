"""Per-record sharing and ownership (ADR-0027 §2, §3).

Shareable records are documents and tradition entries. Everything here is for the record's
content owner, except accepting or declining a transfer, which is for the member it was offered to.
Records the caller has no role on answer 404, so nothing reveals that a private record exists.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import is_record_owner
from app.core import audit
from app.core.errors import NotFound, Unprocessable
from app.models import AccessGrant, Document, TraditionEntry, TreeMembership
from app.models.enums import GrantResource
from app.modules.sharing.schemas import OwnershipOfferOut, SharingOut
from app.modules.trees.schemas import GrantOut

_MODELS: dict[GrantResource, Any] = {
    GrantResource.DOCUMENT: Document,
    GrantResource.TRADITION: TraditionEntry,
}


def _record(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> Any:
    model = _MODELS.get(GrantResource(resource_type))
    if model is None or not ctx.is_member or ctx.public:
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


def sharing(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> SharingOut:
    r = _owned(ctx, resource_type, resource_id)
    grants = ctx.db.scalars(
        select(AccessGrant)
        .where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.resource_type == resource_type,
            AccessGrant.resource_id == r.id,
        )
        .order_by(AccessGrant.granted_at, AccessGrant.id)
    )
    return SharingOut(
        resource_type=resource_type,
        resource_id=r.id,
        privacy_level=r.privacy_level,
        audience_branch_id=r.audience_branch_id if isinstance(r, Document) else r.branch_id,
        owner_membership_id=r.owner_membership_id,
        pending_owner_membership_id=r.pending_owner_membership_id,
        grants=[GrantOut.model_validate(g) for g in grants],
    )


def _audit(ctx: TreeContext, action: str, resource_type: GrantResource, r: Any, **details: Any) -> None:
    audit.log(
        ctx, action, target_type=GrantResource(resource_type).value, target_id=r.id, details=details or None
    )


def offer(
    ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID, user_id: uuid.UUID
) -> SharingOut:
    """The owner offers the record to another member, who must accept (§2)."""
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
    return sharing(ctx, resource_type, resource_id)


def _pending_for_me(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> Any:
    r = _record(ctx, resource_type, resource_id)
    if ctx.membership is None or r.pending_owner_membership_id != ctx.membership.id:
        raise NotFound("Record not found")
    return r


def accept(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> None:
    r = _pending_for_me(ctx, resource_type, resource_id)
    me = r.pending_owner_membership_id  # the caller's membership (checked above)
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


def withdraw_offer(ctx: TreeContext, resource_type: GrantResource, resource_id: uuid.UUID) -> None:
    """The owner cancels an offer, or the member it was offered to declines it."""
    r = _record(ctx, resource_type, resource_id)
    me = ctx.membership.id if ctx.membership is not None else None
    if (
        me is None
        or r.pending_owner_membership_id is None
        or me not in (r.owner_membership_id, r.pending_owner_membership_id)
    ):
        raise NotFound("Record not found")
    declined = me == r.pending_owner_membership_id
    r.pending_owner_membership_id = None
    ctx.db.flush()
    _audit(
        ctx, "record.ownership_declined" if declined else "record.ownership_offer_cancelled", resource_type, r
    )


def offers_for_me(ctx: TreeContext) -> list[OwnershipOfferOut]:
    if ctx.membership is None:
        return []
    out: list[OwnershipOfferOut] = []
    docs = ctx.db.scalars(
        select(Document).where(
            Document.tree_id == ctx.tree_id,
            Document.pending_owner_membership_id == ctx.membership.id,
            Document.deleted_at.is_(None),
        )
    )
    out += [
        OwnershipOfferOut(resource_type=GrantResource.DOCUMENT, resource_id=d.id, title=d.title) for d in docs
    ]
    entries = ctx.db.scalars(
        select(TraditionEntry).where(
            TraditionEntry.tree_id == ctx.tree_id,
            TraditionEntry.pending_owner_membership_id == ctx.membership.id,
            TraditionEntry.withdrawn_at.is_(None),
        )
    )
    out += [
        OwnershipOfferOut(resource_type=GrantResource.TRADITION, resource_id=e.id, title=e.title)
        for e in entries
    ]
    return out
