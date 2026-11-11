"""Family calendar (ADR-0022): calendar feeds and cached calendar days."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base


class CalendarFeed(Base):
    """A member's private ICS feed for one tree (ADR-0022 §7).

    Resolved by its token before any tree is known (like an invitation), so it is protected by the
    service layer, not row-level security. Only the SHA-256 of the token is stored.
    """

    __tablename__ = "calendar_feed"
    __table_args__ = (
        Index(
            "uq_calendar_feed_active",
            "tree_id",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    tree_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tree.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    include_names: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class PanchangDay(Base):
    """One computed day at one (coarse) place: global reference data with no family data in it.

    Written by the operator CLI (``app.cli.calendar compute``); read-only to the application role.
    """

    __tablename__ = "panchang_day"

    place_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    sunrise: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    sunset: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    tithi_at_sunrise: Mapped[int] = mapped_column(SmallInteger)
    tithis: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    amanta_masa: Mapped[int] = mapped_column(SmallInteger)
    is_adhik: Mapped[bool] = mapped_column(Boolean)
    engine_version: Mapped[str] = mapped_column(String(60))
