from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import EmailStr, Field

from app.api.schemas import ApiModel
from app.models.enums import GrantPermission, GrantResource, PrivacyLevel, PublicMode, ReviewPolicy, Role


class TreeCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class TreeUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    public_mode: PublicMode | None = None
    default_person_privacy: PrivacyLevel | None = None


class TreeOut(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    slug: str
    public_mode: PublicMode
    default_person_privacy: PrivacyLevel
    # which changes need family review (ADR-0021 §1)
    review_policy: ReviewPolicy = ReviewPolicy.OFF
    created_at: dt.datetime
    my_roles: list[Role] = []
    my_permissions: list[str] = []
    my_branch_id: uuid.UUID | None = None
    my_linked_person_id: uuid.UUID | None = None


class MemberOut(ApiModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    roles: list[Role]
    branch_id: uuid.UUID | None
    linked_person_id: uuid.UUID | None
    created_at: dt.datetime


class MemberUpdate(ApiModel):
    roles: list[Role] | None = Field(default=None, min_length=1)
    branch_id: uuid.UUID | None = None
    linked_person_id: uuid.UUID | None = None
    clear_branch: bool = False
    clear_linked_person: bool = False


class InvitationCreate(ApiModel):
    email: EmailStr
    roles: list[Role] = Field(min_length=1)
    branch_id: uuid.UUID | None = None


class InvitationOut(ApiModel):
    id: uuid.UUID
    email: str
    roles: list[Role]
    branch_id: uuid.UUID | None
    expires_at: dt.datetime
    accepted_at: dt.datetime | None
    revoked_at: dt.datetime | None
    created_at: dt.datetime
    # Only returned once, at creation (email delivery is a console outbox in this release).
    invite_url: str | None = None
    token: str | None = None


class InvitationPreview(ApiModel):
    tree_id: uuid.UUID
    tree_name: str
    roles: list[Role]
    email: str
    expired: bool


class GrantCreate(ApiModel):
    user_id: uuid.UUID
    resource_type: GrantResource
    resource_id: uuid.UUID
    permission: GrantPermission
    expires_at: dt.datetime | None = None


class GrantOut(ApiModel):
    id: uuid.UUID
    user_id: uuid.UUID
    resource_type: GrantResource
    resource_id: uuid.UUID
    permission: GrantPermission
    expires_at: dt.datetime | None
    granted_at: dt.datetime


class AuditEventOut(ApiModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None = None
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    summary: str | None
    details: dict[str, Any]
    created_at: dt.datetime
