from __future__ import annotations

import datetime as dt
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from app.api.schemas import ApiModel
from app.models.enums import DeliveryStatus, NotificationChannel, ReminderKind, ReminderRecurrence


def _lead(v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if not v or len(v) > 6:
        raise ValueError("choose between 1 and 6 lead times")
    if any(d < 0 or d > 365 for d in v):
        raise ValueError("lead times are 0 to 365 days before the date")
    return sorted(set(v))


def _channels(v: list[NotificationChannel] | None) -> list[NotificationChannel] | None:
    if v is None:
        return v
    if not v:
        raise ValueError("choose at least one channel")
    return list(dict.fromkeys(v))


class ChannelsOut(ApiModel):
    email: bool
    sms: bool
    whatsapp: bool


class PreferenceIn(ApiModel):
    enabled: bool
    channels: list[NotificationChannel] = [NotificationChannel.EMAIL]
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    send_hour: int = Field(default=8, ge=0, le=23)
    default_lead_days: list[int] = [0]

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown IANA time zone") from exc
        return v

    @field_validator("default_lead_days")
    @classmethod
    def _v_lead(cls, v: list[int]) -> list[int]:
        return _lead(v) or [0]

    @field_validator("channels")
    @classmethod
    def _v_channels(cls, v: list[NotificationChannel]) -> list[NotificationChannel]:
        return _channels(v) or []


class PreferenceOut(ApiModel):
    enabled: bool
    channels: list[NotificationChannel]
    timezone: str
    send_hour: int
    default_lead_days: list[int]
    exists: bool = True


class ReminderIn(ApiModel):
    event_id: uuid.UUID
    kind: ReminderKind | None = None  # default from the event type
    recurrence: ReminderRecurrence | None = None  # default from the kind
    lead_days: list[int] | None = None  # default: the tree preference
    channels: list[NotificationChannel] | None = None  # default: the tree preference
    note: str | None = Field(default=None, max_length=300)

    @field_validator("lead_days")
    @classmethod
    def _v_lead(cls, v: list[int] | None) -> list[int] | None:
        return _lead(v)

    @field_validator("channels")
    @classmethod
    def _v_channels(cls, v: list[NotificationChannel] | None) -> list[NotificationChannel] | None:
        return _channels(v)


class ReminderUpdate(ApiModel):
    recurrence: ReminderRecurrence | None = None
    lead_days: list[int] | None = None
    channels: list[NotificationChannel] | None = None
    note: str | None = Field(default=None, max_length=300)
    active: bool | None = None

    @field_validator("lead_days")
    @classmethod
    def _v_lead(cls, v: list[int] | None) -> list[int] | None:
        return _lead(v)

    @field_validator("channels")
    @classmethod
    def _v_channels(cls, v: list[NotificationChannel] | None) -> list[NotificationChannel] | None:
        return _channels(v)


class ReminderOut(ApiModel):
    id: uuid.UUID
    event_id: uuid.UUID
    kind: ReminderKind
    recurrence: ReminderRecurrence
    lead_days: list[int]
    channels: list[NotificationChannel]
    note: str | None
    active: bool
    next_fire_at: dt.datetime | None
    last_fired_at: dt.datetime | None
    created_at: dt.datetime
    label: str | None = None
    person_id: uuid.UUID | None = None
    person_name: str | None = None
    next_occurrence: dt.date | None = None
    # false when the event (or its full date) is no longer visible to you: nothing will be sent
    deliverable: bool = True


class UpcomingOut(ApiModel):
    event_id: uuid.UUID
    kind: ReminderKind
    occurrence_date: dt.date
    days_until: int
    label: str
    person_id: uuid.UUID | None = None
    display_name: str | None = None
    anniversary: int | None = None  # e.g. 75 for a 75th birth anniversary, when the year is visible
    reminder_id: uuid.UUID | None = None


class DeliveryOut(ApiModel):
    id: uuid.UUID
    reminder_id: uuid.UUID | None
    event_id: uuid.UUID | None
    channel: NotificationChannel
    occurrence_date: dt.date
    lead_days: int
    scheduled_for: dt.datetime
    status: DeliveryStatus
    attempts: int
    next_attempt_at: dt.datetime | None
    last_error_code: str | None
    provider: str | None
    sent_at: dt.datetime | None
    cancelled_reason: str | None
    is_test: bool
    label: str | None = None


class ContactIn(ApiModel):
    channel: NotificationChannel
    address: str = Field(min_length=8, max_length=20, description="E.164 phone number, e.g. +919876543210")

    @field_validator("address")
    @classmethod
    def _e164(cls, v: str) -> str:
        import re

        v = re.sub(r"[\s\-()]", "", v)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", v):
            raise ValueError("use the international format, e.g. +919876543210")
        return v


class ContactOut(ApiModel):
    id: uuid.UUID
    channel: NotificationChannel
    address_hint: str
    verified: bool
    created_at: dt.datetime


class VerifyIn(ApiModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
