"""Ownership transfer of documents and tradition entries (ADR-0027 §2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.models.enums import GrantResource
from app.modules.ownership import service
from app.modules.ownership.schemas import OwnershipOfferIn, OwnershipOfferOut, OwnershipOut

router = APIRouter(tags=["ownership"])

_OFFER = "/trees/{tree_id}/records/{resource_type}/{resource_id}/ownership-offer"


@router.post(_OFFER, response_model=OwnershipOut)
def offer_ownership(
    resource_type: GrantResource, resource_id: uuid.UUID, body: OwnershipOfferIn, ctx: TreeCtx
) -> OwnershipOut:
    """The owner offers the record to another member, who becomes the owner when they accept."""
    return service.offer(ctx, resource_type, resource_id, body.user_id)


@router.delete(_OFFER, response_model=Message)
def withdraw_ownership_offer(resource_type: GrantResource, resource_id: uuid.UUID, ctx: TreeCtx) -> Message:
    """The owner cancels the offer, or the member it was offered to declines it."""
    service.withdraw_offer(ctx, resource_type, resource_id)
    return Message(message="Offer withdrawn")


@router.post(f"{_OFFER}/accept", response_model=OwnershipOut)
def accept_ownership(resource_type: GrantResource, resource_id: uuid.UUID, ctx: TreeCtx) -> OwnershipOut:
    return service.accept(ctx, resource_type, resource_id)


@router.get("/trees/{tree_id}/ownership-offers", response_model=list[OwnershipOfferOut])
def my_ownership_offers(ctx: TreeCtx) -> list[OwnershipOfferOut]:
    """Records whose owners offered them to the caller."""
    return service.offers_for_me(ctx)
