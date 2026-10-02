from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbDep, TreeCtx
from app.api.schemas import Message, Page, decode_cursor, encode_cursor
from app.models.enums import NotificationChannel
from app.modules.notifications import channels as ch
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    ChannelsOut,
    ContactIn,
    ContactOut,
    DeliveryOut,
    PreferenceIn,
    PreferenceOut,
    ReminderIn,
    ReminderOut,
    ReminderUpdate,
    UpcomingOut,
    VerifyIn,
)

router = APIRouter(prefix="/trees/{tree_id}", tags=["reminders"])
user_router = APIRouter(tags=["reminders"])


# ---------------------------------------------------------------- per tree (always "mine")
@router.get("/notification-preferences", response_model=PreferenceOut)
def get_preferences(ctx: TreeCtx) -> PreferenceOut:
    return service.get_preferences(ctx)


@router.put("/notification-preferences", response_model=PreferenceOut)
def set_preferences(body: PreferenceIn, ctx: TreeCtx) -> PreferenceOut:
    return service.set_preferences(ctx, body)


@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(ctx: TreeCtx, event_id: uuid.UUID | None = None) -> list[ReminderOut]:
    """Your own reminders in this tree."""
    return service.list_reminders(ctx, event_id)


@router.post("/reminders", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(body: ReminderIn, ctx: TreeCtx) -> ReminderOut:
    return service.reminder_out(ctx, service.create_reminder(ctx, body))


@router.get("/reminders/upcoming", response_model=list[UpcomingOut])
def upcoming(
    ctx: TreeCtx,
    days: int = Query(default=30, ge=1, le=366),
    scope: str = Query(default="tree", pattern="^(tree|mine)$"),
) -> list[UpcomingOut]:
    """Upcoming birthdays, anniversaries and remembrance days you may see (``tree``), or only the
    events you have reminders for (``mine``)."""
    return service.upcoming(ctx, days, scope)


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
def update_reminder(reminder_id: uuid.UUID, body: ReminderUpdate, ctx: TreeCtx) -> ReminderOut:
    return service.reminder_out(ctx, service.update_reminder(ctx, reminder_id, body))


@router.delete("/reminders/{reminder_id}", response_model=Message)
def delete_reminder(reminder_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_reminder(ctx, reminder_id)
    return Message(message="Reminder removed")


@router.post("/reminders/{reminder_id}/test", response_model=list[DeliveryOut])
def test_reminder(reminder_id: uuid.UUID, ctx: TreeCtx) -> list[DeliveryOut]:
    """Send this reminder to yourself now on its channels (marked as a test; rate limited)."""
    return [DeliveryOut.model_validate(d) for d in service.send_test(ctx, reminder_id)]


@router.get("/notifications", response_model=Page[DeliveryOut])
def notification_history(
    ctx: TreeCtx, cursor: str | None = None, limit: int = Query(default=50, ge=1, le=200)
) -> Page[DeliveryOut]:
    """Your reminder deliveries in this tree, newest first (status, attempts, errors; no message text)."""
    offset = decode_cursor(cursor)
    items, more = service.history(ctx, limit, offset)
    return Page(items=items, next_cursor=encode_cursor(offset + limit) if more else None)


# ---------------------------------------------------------------- user level
@user_router.get("/notification-channels", response_model=ChannelsOut)
def notification_channels(user: CurrentUser) -> ChannelsOut:
    """Which reminder channels this server can deliver."""
    return ChannelsOut(**{c.value: ch.channel_available(c) for c in NotificationChannel})


@user_router.get("/me/notification-contacts", response_model=list[ContactOut])
def list_contacts(user: CurrentUser, db: DbDep) -> list[ContactOut]:
    return service.list_contacts(db, user)


@user_router.post("/me/notification-contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def add_contact(body: ContactIn, user: CurrentUser, db: DbDep) -> ContactOut:
    """Add (or replace) your phone number for SMS or WhatsApp; a 6-digit code is sent to it."""
    return service.contact_out(service.add_contact(db, user, body))


@user_router.post("/me/notification-contacts/{contact_id}/verify", response_model=ContactOut)
def verify_contact(contact_id: uuid.UUID, body: VerifyIn, user: CurrentUser, db: DbDep) -> ContactOut:
    return service.contact_out(service.verify_contact(db, user, contact_id, body.code))


@user_router.delete("/me/notification-contacts/{contact_id}", response_model=Message)
def delete_contact(contact_id: uuid.UUID, user: CurrentUser, db: DbDep) -> Message:
    service.delete_contact(db, user, contact_id)
    return Message(message="Contact removed; no more messages will be sent to it")
