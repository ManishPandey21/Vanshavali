from __future__ import annotations

import uuid

from app.api.schemas import ApiModel
from app.models.enums import GrantResource


class OwnershipOfferIn(ApiModel):
    user_id: uuid.UUID  # a member of this tree


class OwnershipOut(ApiModel):
    """A record's owner and any pending transfer, for its owner (ADR-0027 §2)."""

    resource_type: GrantResource
    resource_id: uuid.UUID
    owner_membership_id: uuid.UUID | None
    pending_owner_membership_id: uuid.UUID | None


class OwnershipOfferOut(ApiModel):
    """A record whose owner offered it to the viewer."""

    resource_type: GrantResource
    resource_id: uuid.UUID
    title: str
