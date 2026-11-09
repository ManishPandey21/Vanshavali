"""Per-record sharing and ownership transfer (ADR-0027 §2, §3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.models.enums import GrantResource
from app.modules.sharing import service
from app.modules.sharing.schemas import OwnershipOfferIn, OwnershipOfferOut, SharingOut

router = APIRouter(tags=["sharing"])

_RECORD = "/trees/{tree_id}/records/{resource_type}/{resource_id}"


@router.get(f"{_RECORD}/sharing", response_model=SharingOut)
def get_sharing(resource_type: GrantResource, resource_id: uuid.UUID, ctx: TreeCtx) -> SharingOut:
    """The record's audience and grants. Its content owner only; anyone else gets 404."""
    return service.sharing(ctx, resource_type, resource_id)


@router.post(f"{_RECORD}/ownership-offer", response_model=SharingOut)
def offer_ownership(
    resource_type: GrantResource, resource_id: uuid.UUID, body: OwnershipOfferIn, ctx: TreeCtx
) -> SharingOut:
    """Offer the record to another member; they become the owner when they accept."""
    return service.offer(ctx, resource_type, resource_id, body.user_id)


@router.delete(f"{_RECORD}/ownership-offer", response_model=Message)
def withdraw_ownership_offer(resource_type: GrantResource, resource_id: uuid.UUID, ctx: TreeCtx) -> Message:
    """The owner cancels the offer, or the member it was offered to declines it."""
    service.withdraw_offer(ctx, resource_type, resource_id)
    return Message(message="Offer withdrawn")


@router.post(f"{_RECORD}/ownership-offer/accept", response_model=Message)
def accept_ownership(resource_type: GrantResource, resource_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.accept(ctx, resource_type, resource_id)
    return Message(message="You now own this")


@router.get("/trees/{tree_id}/ownership-offers", response_model=list[OwnershipOfferOut])
def my_ownership_offers(ctx: TreeCtx) -> list[OwnershipOfferOut]:
    """Records whose owners offered them to the caller."""
    return service.offers_for_me(ctx)
