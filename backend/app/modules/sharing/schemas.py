"""Request and response bodies of the Visibility & Sharing API, the same for every record type."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.models.enums import RecordPrivacyLevel

SharingAccess = Literal["owner", "selected", "branch", "family", "role"]


class SharingMemberIn(ApiModel):
    membership_id: uuid.UUID
    can_download: bool = False


class SharingUpdate(ApiModel):
    """The whole sharing setting of a record. ``members`` replaces the record's explicit grants."""

    privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None = None
    allow_download: bool = False
    members: list[SharingMemberIn] = Field(default=[], max_length=500)
    # a change that lets anyone new see or download the record must be confirmed (ADR-0027 §9)
    confirm_wider: bool = False


class SharingMemberOut(ApiModel):
    membership_id: uuid.UUID
    display_name: str
    access: SharingAccess
    can_download: bool


class SharingCeilingOut(ApiModel):
    """The widest audience the people tagged in the record allow."""

    max_level: RecordPrivacyLevel
    branch_ids: list[uuid.UUID] = []


class SharingOut(ApiModel):
    privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None
    allow_download: bool
    is_owner: bool
    has_owner: bool
    can_edit: bool
    can_widen: bool
    legacy: bool  # CUSTOM or PRIVATE_SELF: also seen by admins or the tree owner
    ceiling: SharingCeilingOut | None
    members: list[SharingMemberOut]  # the explicitly selected members (owner and managers only)
    audience: list[SharingMemberOut]  # everyone who can see it, computed by the server
