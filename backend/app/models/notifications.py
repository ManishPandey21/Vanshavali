"""Event reminders and notification delivery (ADR-0016, docs/architecture/event-reminder-model.md)."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import (
    DeliveryStatus,
    NotificationChannel,
    ReminderDateRule,
    ReminderKind,
    ReminderRecurrence,
)


class NotificationContact(Base):
    """A user's SMS / WhatsApp number. User-level identity data (not tree data, so not under RLS):
    only the user can read or change it. The number is AES-GCM encrypted (SYSTEM key) and must be
    verified with a one-time code before anything is sent to it."""

    __tablename__ = "notification_contact"
    __table_args__ = (UniqueConstraint("user_id", "channel", name="uq_notification_contact"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(enum_column(NotificationChannel))
    address_enc: Mapped[str] = mapped_column(String(400))
    address_hint: Mapped[str] = mapped_column(String(40))  # masked, e.g. +91******3210
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    verify_code_hash: Mapped[str | None] = mapped_column(String(64))
    verify_expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    verify_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationPreference(TreeScopedMixin, Base):
    """One user's reminder settings for one tree (opt-in: nothing is sent while ``enabled`` is off)."""

    __tablename__ = "notification_preference"
    __table_args__ = (
        tree_unique("notification_preference"),
        UniqueConstraint("tree_id", "user_id", name="uq_notification_preference"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", server_default="Asia/Kolkata")
    send_hour: Mapped[int] = mapped_column(SmallInteger, default=8, server_default="8")
    default_lead_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=lambda: [0], server_default="{0}"
    )


class EventReminder(TreeScopedMixin, Base):
    """A user's subscription to reminders about one event."""

    __tablename__ = "event_reminder"
    __table_args__ = (
        tree_unique("event_reminder"),
        tree_fk(["event_id"], "event"),
        UniqueConstraint("event_id", "user_id", name="uq_event_reminder"),
        Index("ix_event_reminder_due", "tree_id", "active", "next_fire_at"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ReminderKind] = mapped_column(enum_column(ReminderKind))
    recurrence: Mapped[ReminderRecurrence] = mapped_column(enum_column(ReminderRecurrence))
    lead_days: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [0], server_default="{0}")
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}")
    note: Mapped[str | None] = mapped_column(String(300))
    # ADR-0022 §5: a lunar reminder follows the event's tithi, under a convention, at a place
    date_rule: Mapped[ReminderDateRule] = mapped_column(
        enum_column(ReminderDateRule),
        default=ReminderDateRule.SOLAR,
        server_default=ReminderDateRule.SOLAR.value,
    )
    convention: Mapped[str | None] = mapped_column(String(40))
    observance_city: Mapped[str | None] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    next_fire_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_fired_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(TreeScopedMixin, Base):
    """One attempt-tracked message for one occurrence of a reminder on one channel.

    Holds no message body and no address: only what is needed for status, retries and history.
    """

    __tablename__ = "notification_delivery"
    __table_args__ = (
        tree_unique("notification_delivery"),
        tree_fk(["reminder_id"], "event_reminder", ondelete="SET NULL"),
        tree_fk(["event_id"], "event", ondelete="SET NULL"),
        UniqueConstraint(
            "reminder_id", "channel", "occurrence_date", "lead_days", name="uq_notification_delivery_once"
        ),
        Index("ix_notification_delivery_user", "tree_id", "user_id", "scheduled_for"),
        Index("ix_notification_delivery_retry", "tree_id", "status", "next_attempt_at"),
    )

    reminder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(enum_column(NotificationChannel))
    occurrence_date: Mapped[dt.date] = mapped_column(Date)
    lead_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    scheduled_for: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[DeliveryStatus] = mapped_column(
        enum_column(DeliveryStatus),
        default=DeliveryStatus.PENDING,
        server_default=DeliveryStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    provider: Mapped[str | None] = mapped_column(String(40))
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_reason: Mapped[str | None] = mapped_column(String(80))
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
