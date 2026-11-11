"""Family calendar API (ADR-0022 §10)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Path, Query, Response

from app.api.deps import DbDep, TreeCtx
from app.modules.calendar import service
from app.modules.calendar.schemas import (
    CalendarOut,
    CalendarSettingsIn,
    CalendarSettingsOut,
    ConvertIn,
    ConvertOut,
    FeedIn,
    FeedOut,
)

router = APIRouter(tags=["calendar"])


@router.get("/trees/{tree_id}/calendar-settings", response_model=CalendarSettingsOut)
def get_calendar_settings(ctx: TreeCtx) -> CalendarSettingsOut:
    """The family's calendar convention and observance city, and what is available."""
    return service.get_calendar_settings(ctx)


@router.put("/trees/{tree_id}/calendar-settings", response_model=CalendarSettingsOut)
def set_calendar_settings(body: CalendarSettingsIn, ctx: TreeCtx) -> CalendarSettingsOut:
    """Chosen by a tree admin; never inferred from a surname, place or community."""
    return service.set_calendar_settings(ctx, body)


@router.get("/trees/{tree_id}/calendar", response_model=CalendarOut)
def family_calendar(
    ctx: TreeCtx,
    start: dt.date = Query(alias="from"),
    end: dt.date = Query(alias="to"),
) -> CalendarOut:
    """Birthdays, anniversaries and remembrance days you may see in full, by Gregorian date and,
    for an offered convention, by tithi."""
    return service.calendar(ctx, start, end)


@router.post("/trees/{tree_id}/calendar/convert", response_model=ConvertOut)
def convert(body: ConvertIn, ctx: TreeCtx) -> ConvertOut:
    """A suggested Gregorian date for a tithi date with a samvat year; nothing is stored."""
    return service.convert(ctx, body)


@router.get("/trees/{tree_id}/calendar-feed", response_model=FeedOut)
def feed_status(ctx: TreeCtx) -> FeedOut:
    return service.feed_status(ctx)


@router.post("/trees/{tree_id}/calendar-feed", response_model=FeedOut)
def create_feed(body: FeedIn, ctx: TreeCtx) -> FeedOut:
    """Create or replace your private calendar feed; its URL is shown only now."""
    return service.create_feed(ctx, body.include_names)


@router.delete("/trees/{tree_id}/calendar-feed", response_model=FeedOut)
def revoke_feed(ctx: TreeCtx) -> FeedOut:
    return service.revoke_feed(ctx)


@router.get(
    "/calendar-feeds/{token}.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}},
)
def feed(
    db: DbDep, token: str = Path(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
) -> Response:
    """A member's calendar feed. The token is the credential; every fetch is evaluated as the member."""
    body = service.feed_ics(db, token)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
    )
