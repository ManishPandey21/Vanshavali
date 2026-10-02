from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate
from app.modules.documents.schemas import DocumentOut


class TaggedPerson(ApiModel):
    person_id: uuid.UUID
    display_name: str


class EventMediaOut(ApiModel):
    id: uuid.UUID
    event_id: uuid.UUID
    document_id: uuid.UUID
    caption: str | None
    taken_date: dict[str, Any] | None
    taken_date_display: str | None = None
    is_cover: bool
    sort_order: int
    created_at: dt.datetime
    document: DocumentOut
    people: list[TaggedPerson] = []


class EventMediaLinkIn(ApiModel):
    """Add a photo that is already in the vault to the event's album."""

    document_id: uuid.UUID
    caption: str | None = Field(default=None, max_length=500)
    taken_date: GenealogicalDate | None = None
    is_cover: bool = False
    person_ids: list[uuid.UUID] = Field(default=[], max_length=50)


class EventMediaUpdate(ApiModel):
    caption: str | None = Field(default=None, max_length=500)
    taken_date: GenealogicalDate | None = None
    is_cover: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    add_person_ids: list[uuid.UUID] = Field(default=[], max_length=50)
