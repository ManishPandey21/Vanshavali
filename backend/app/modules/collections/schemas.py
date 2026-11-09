from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field

from app.api.schemas import ApiModel
from app.models.enums import RecordPrivacyLevel
from app.modules.documents.schemas import DocumentOut


class CollectionIn(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    # new collections are Only me unless the owner chooses (ADR-0027 §9); never public
    privacy_level: RecordPrivacyLevel = RecordPrivacyLevel.ONLY_ME
    audience_branch_id: uuid.UUID | None = None


class CollectionUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)


class CollectionItemIn(ApiModel):
    document_id: uuid.UUID
    caption: str | None = Field(default=None, max_length=500)
    is_cover: bool = False


class CollectionItemUpdate(ApiModel):
    caption: str | None = Field(default=None, max_length=500)
    is_cover: bool | None = None


class CollectionItemOut(ApiModel):
    id: uuid.UUID
    document_id: uuid.UUID
    caption: str | None
    is_cover: bool
    sort_order: int
    document: DocumentOut
    # owner only: can everyone who sees the collection also see this photo? (ADR-0027 §6 warning)
    shared_with_collection_audience: bool | None = None


class CollectionSummaryOut(ApiModel):
    id: uuid.UUID
    title: str
    description: str | None
    privacy_level: RecordPrivacyLevel
    item_count: int  # the photos this viewer may see
    cover_document_id: uuid.UUID | None  # a cover this viewer may see
    is_owner: bool
    can_edit_sharing: bool
    updated_at: dt.datetime


class CollectionOut(CollectionSummaryOut):
    items: list[CollectionItemOut] = []
    # owner only: how many photos some of the collection's audience cannot see
    items_not_shared: int | None = None
