from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200))
    preferred_language: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    password_changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # TOTP secret, encrypted with the SYSTEM data key; MFA is active only when mfa_enabled_at is set.
    mfa_secret_enc: Mapped[str | None] = mapped_column(String(400))
    mfa_enabled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "user_session"
    __table_args__ = (Index("ix_user_session_user_active", "user_id", "revoked_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    idle_expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
