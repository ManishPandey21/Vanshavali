from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate
from app.models.enums import (
    DocumentCategory,
    DocumentLinkTarget,
    ProcessingStatus,
    RecordPrivacyLevel,
    ScanStatus,
    StorageClass,
)


class DocumentLinkIn(ApiModel):
    target_type: DocumentLinkTarget
    target_id: uuid.UUID
    note: str | None = Field(default=None, max_length=300)


class DocumentLinkOut(ApiModel):
    id: uuid.UUID
    target_type: DocumentLinkTarget
    target_id: uuid.UUID
    note: str | None
    created_at: dt.datetime


class DocumentOut(ApiModel):
    id: uuid.UUID
    category: DocumentCategory
    storage_class: StorageClass
    title: str
    description: str | None
    original_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    document_date: dict[str, Any] | None
    language: str | None
    script: str | None
    issuing_authority: str | None
    privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None = None
    allow_download: bool = True
    scan_status: ScanStatus
    page_count: int | None
    ocr_status: ProcessingStatus
    extraction_status: ProcessingStatus
    preview_status: ProcessingStatus
    metadata_version: int
    created_by: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
    deleted_at: dt.datetime | None
    links: list[DocumentLinkOut] = []
    can_access_content: bool = False  # thumbnail, preview, playback, OCR text
    can_download: bool = False  # the original file and exports (ADR-0027 §4)
    is_owner: bool = False
    can_edit_sharing: bool = False
    # false on a private record for anyone but its owner: they may read, never change (ADR-0027 §10)
    can_change: bool = True
    variants: list[str] = []  # variants the viewer may fetch: original, preview, thumbnail, stream
    has_ocr_text: bool = False
    pending_proposals: int = 0


class DocumentUpdate(ApiModel):
    """Metadata edit. Every change snapshots the previous metadata; original bytes never change."""

    title: str | None = Field(default=None, min_length=1, max_length=400)
    description: str | None = Field(default=None, max_length=20000)
    category: DocumentCategory | None = None
    privacy_level: RecordPrivacyLevel | None = None
    document_date: GenealogicalDate | None = None
    language: str | None = Field(default=None, max_length=16)
    script: str | None = Field(default=None, max_length=20)
    issuing_authority: str | None = Field(default=None, max_length=300)


class MetadataVersionOut(ApiModel):
    version: int
    snapshot: dict[str, Any]
    created_by: uuid.UUID | None
    created_at: dt.datetime
    current: bool = False


class DownloadUrlOut(ApiModel):
    url: str
    expires_at: dt.datetime
    variant: str


# ---------------------------------------------------------------- Visibility & Sharing (ADR-0027)
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
