from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field

from app.api.schemas import ApiModel, SharedPrivacyLevel
from app.core.dates import GenealogicalDate
from app.models.enums import CitationTarget, Confidence, PrivacyLevel, SourceType


class TraditionIn(ApiModel):
    """Traditional genealogy record details (Bahi / Panda / temple register; PRS §20)."""

    tradition_type: str = Field(
        pattern="^(bahi|panda_register|temple_register|community_register|family_book|other)$"
    )
    custodian: str | None = Field(default=None, max_length=200)
    pilgrimage_place: str | None = Field(default=None, max_length=200)
    volume: str | None = Field(default=None, max_length=60)
    page: str | None = Field(default=None, max_length=60)
    family_origin_place: str | None = Field(default=None, max_length=200)
    verification_status: str | None = Field(default=None, max_length=60)


class SourceIn(ApiModel):
    source_type: SourceType = SourceType.OTHER
    title: str = Field(min_length=1, max_length=400)
    issuing_authority: str | None = Field(default=None, max_length=300)
    repository: str | None = Field(default=None, max_length=300)
    record_number: str | None = Field(default=None, max_length=200)
    date: GenealogicalDate | None = None
    place_id: uuid.UUID | None = None
    place_text: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=1000, pattern=r"^https?://")
    document_id: uuid.UUID | None = None
    transcription: str | None = Field(default=None, max_length=100000)
    translation: str | None = Field(default=None, max_length=100000)
    notes: str | None = Field(default=None, max_length=20000)
    tradition: TraditionIn | None = None
    privacy_level: SharedPrivacyLevel = PrivacyLevel.TREE_MEMBERS


class SourceUpdate(ApiModel):
    source_type: SourceType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=400)
    issuing_authority: str | None = None
    repository: str | None = None
    record_number: str | None = None
    date: GenealogicalDate | None = None
    place_id: uuid.UUID | None = None
    place_text: str | None = None
    url: str | None = Field(default=None, pattern=r"^https?://")
    transcription: str | None = None
    translation: str | None = None
    notes: str | None = None
    tradition: TraditionIn | None = None
    privacy_level: SharedPrivacyLevel | None = None


class SourceOut(ApiModel):
    id: uuid.UUID
    source_type: SourceType
    title: str
    issuing_authority: str | None
    repository: str | None
    record_number: str | None
    date: dict[str, Any] | None
    place_id: uuid.UUID | None
    place_text: str | None
    url: str | None
    document_id: uuid.UUID | None
    transcription: str | None
    translation: str | None
    notes: str | None
    tradition: dict[str, Any] | None
    privacy_level: SharedPrivacyLevel
    citation_count: int = 0
    created_at: dt.datetime


class CitationIn(ApiModel):
    source_id: uuid.UUID
    target_type: CitationTarget
    target_id: uuid.UUID
    page_or_image: str | None = Field(default=None, max_length=200)
    text_excerpt: str | None = Field(default=None, max_length=20000)
    accessed_date: dt.date | None = None
    confidence: Confidence = Confidence.UNKNOWN


class CitationOut(ApiModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_title: str | None = None
    target_type: CitationTarget
    target_id: uuid.UUID
    page_or_image: str | None
    text_excerpt: str | None
    accessed_date: dt.date | None
    confidence: Confidence
    created_by: uuid.UUID | None
    created_at: dt.datetime
