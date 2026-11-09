from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate
from app.models.enums import (
    DocumentCategory,
    DocumentLinkTarget,
    PrivacyLevel,
    ProcessingStatus,
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
    privacy_level: PrivacyLevel
    audience_branch_id: uuid.UUID | None = None
    owner_membership_id: uuid.UUID | None = None
    is_owner: bool = False  # the viewer is the content owner (ADR-0027 §2)
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
    can_access_content: bool = False
    variants: list[str] = []  # downloadable variants: original, preview, thumbnail
    has_ocr_text: bool = False
    pending_proposals: int = 0


class DocumentUpdate(ApiModel):
    """Metadata edit. Every change snapshots the previous metadata; original bytes never change."""

    title: str | None = Field(default=None, min_length=1, max_length=400)
    description: str | None = Field(default=None, max_length=20000)
    category: DocumentCategory | None = None
    privacy_level: PrivacyLevel | None = None
    audience_branch_id: uuid.UUID | None = None  # the branch a FAMILY_BRANCH document is shared with
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
