from __future__ import annotations

import uuid

from app.api.schemas import ApiModel
from app.models.enums import GrantResource, PrivacyLevel
from app.modules.trees.schemas import GrantOut


class SharingOut(ApiModel):
    """A record's audience and grants, for its content owner only (ADR-0027 §3)."""

    resource_type: GrantResource
    resource_id: uuid.UUID
    privacy_level: PrivacyLevel
    audience_branch_id: uuid.UUID | None
    owner_membership_id: uuid.UUID | None
    pending_owner_membership_id: uuid.UUID | None
    grants: list[GrantOut]


class OwnershipOfferIn(ApiModel):
    user_id: uuid.UUID  # a member of this tree


class OwnershipOfferOut(ApiModel):
    """A record whose owner offered it to the viewer (ADR-0027 §2)."""

    resource_type: GrantResource
    resource_id: uuid.UUID
    title: str
