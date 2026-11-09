from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import TreeCtx
from app.api.schemas import Message, Page, decode_cursor, encode_cursor
from app.core.errors import Unprocessable
from app.models.enums import EventSignificance, LifeEventCategory, RecordPrivacyLevel
from app.modules.documents.router import _parse_date, _read_capped
from app.modules.genealogy.schemas import EventOut
from app.modules.lifeevents import service
from app.modules.lifeevents.schemas import EventMediaLinkIn, EventMediaOut, EventMediaUpdate

router = APIRouter(prefix="/trees/{tree_id}", tags=["life-events"])


@router.get("/life-events", response_model=Page[EventOut])
def list_life_events(
    ctx: TreeCtx,
    person_id: uuid.UUID | None = None,
    category: Annotated[list[LifeEventCategory] | None, Query()] = None,
    significance: Annotated[list[EventSignificance] | None, Query()] = None,
    important_only: bool = False,
    from_year: int | None = Query(default=None, ge=1, le=9999),
    to_year: int | None = Query(default=None, ge=1, le=9999),
    geotagged: bool | None = None,
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[EventOut]:
    """Events visible to the caller across the tree, oldest first (undated last)."""
    offset = decode_cursor(cursor)
    f = service.EventFilters(
        person_id=person_id,
        categories=category,
        significance=significance,
        important_only=important_only,
        from_year=from_year,
        to_year=to_year,
        geotagged=geotagged,
        q=q,
    )
    items, more = service.list_events(ctx, f, offset, limit)
    return Page(items=items, next_cursor=encode_cursor(offset + limit) if more else None)


@router.get("/events/{event_id}/media", response_model=list[EventMediaOut])
def event_album(event_id: uuid.UUID, ctx: TreeCtx) -> list[EventMediaOut]:
    return service.album(ctx, event_id)


def _one(ctx: TreeCtx, event_id: uuid.UUID, media_id: uuid.UUID) -> EventMediaOut:
    return next(m for m in service.album(ctx, event_id) if m.id == media_id)


@router.post("/events/{event_id}/media", response_model=EventMediaOut, status_code=status.HTTP_201_CREATED)
def upload_event_photo(
    event_id: uuid.UUID,
    ctx: TreeCtx,
    file: Annotated[UploadFile, File(description="A photo (JPEG, PNG, WebP, HEIC, …)")],
    caption: Annotated[str | None, Form(max_length=500)] = None,
    title: Annotated[str | None, Form(max_length=400)] = None,
    taken_date: Annotated[str | None, Form(description="GenealogicalDate as JSON")] = None,
    is_cover: Annotated[bool, Form()] = False,
    person_ids: Annotated[list[uuid.UUID] | None, Form(description="people shown in the photo")] = None,
    privacy_level: Annotated[RecordPrivacyLevel | None, Form()] = None,
    audience_branch_id: Annotated[uuid.UUID | None, Form()] = None,
    allow_download: Annotated[bool | None, Form()] = None,
) -> EventMediaOut:
    ids = person_ids or []
    if len(ids) > 50:
        raise Unprocessable("Tag at most 50 people in one photo")
    date = _parse_date(taken_date)
    data = _read_capped(file)
    m = service.upload_photo(
        ctx,
        event_id,
        data=data,
        filename=file.filename,
        title=title,
        caption=caption,
        taken_date=date,
        is_cover=is_cover,
        person_ids=ids,
        privacy_level=privacy_level,
        audience_branch_id=audience_branch_id,
        allow_download=allow_download,
    )
    return _one(ctx, event_id, m.id)


@router.post(
    "/events/{event_id}/media/link", response_model=EventMediaOut, status_code=status.HTTP_201_CREATED
)
def link_event_photo(event_id: uuid.UUID, body: EventMediaLinkIn, ctx: TreeCtx) -> EventMediaOut:
    m = service.link_photo(ctx, event_id, body)
    return _one(ctx, event_id, m.id)


@router.patch("/events/{event_id}/media/{media_id}", response_model=EventMediaOut)
def update_event_photo(
    event_id: uuid.UUID, media_id: uuid.UUID, body: EventMediaUpdate, ctx: TreeCtx
) -> EventMediaOut:
    service.update_media(ctx, event_id, media_id, body)
    return _one(ctx, event_id, media_id)


@router.delete("/events/{event_id}/media/{media_id}", response_model=Message)
def remove_event_photo(event_id: uuid.UUID, media_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.remove_media(ctx, event_id, media_id)
    return Message(message="Photo removed from the event (it stays in the document vault)")


@router.get("/people/{person_id}/photos", response_model=list[EventMediaOut])
def person_event_photos(person_id: uuid.UUID, ctx: TreeCtx) -> list[EventMediaOut]:
    """Photos from the albums of this person's events."""
    return service.person_photos(ctx, person_id)
