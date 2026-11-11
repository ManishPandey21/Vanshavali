from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, enum_column


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200))
    preferred_language: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    # which kinship words this person sees (ADR-0026 §6); separate from the UI language
    kinship_lang: Mapped[str | None] = mapped_column(String(16))
    kinship_region: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    password_changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # TOTP secret, encrypted with the SYSTEM data key; MFA is active only when mfa_enabled_at is set.
    mfa_secret_enc: Mapped[str | None] = mapped_column(String(400))
    mfa_enabled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the user proves control of the mailbox (verification link or password reset).
    # Sign-in and invitation acceptance require it (ADR-0005).
    email_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Set for accounts created with a temporary password (dev/demo seeding). While set, the session
    # may only change the password or sign out; everything else answers 403 password_change_required.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class ExternalIdentity(Base):
    """A sign-in identity from an external OpenID Connect provider, linked to one account (ADR-0012).

    Matched by the provider's stable subject id, never by email: an email is only used once, to link
    a new identity to an existing account under the rules in ADR-0012.
    """

    __tablename__ = "external_identity"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(255))
    email_at_link: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


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
    # ADR-0028 §7: set only when this session was opened with password + TOTP (never by Google or
    # an email link), and when the holder last re-entered a TOTP code (step-up). Platform
    # capabilities check both on every request; nothing else reads them.
    mfa_verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_step_up_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class AuthTokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"  # noqa: S105 - enum label, not a secret


class AuthToken(Base):
    """Single-use emailed token (verification, password reset). Only the SHA-256 is stored."""

    __tablename__ = "auth_token"
    __table_args__ = (Index("ix_auth_token_user_purpose", "user_id", "purpose"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE")
    )
    purpose: Mapped[AuthTokenPurpose] = mapped_column(enum_column(AuthTokenPurpose, "auth_token_purpose"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlatformCapability(StrEnum):
    """Platform permissions held outside any family tree (ADR-0028 §7). Deny by default."""

    MASTER_DATA_ADMIN = "master_data.admin"


class PlatformCapabilityGrant(Base):
    """One named person holding one platform capability (ADR-0028 §7).

    Written only by the operator CLI as the schema owner; read-only to the application role
    (``READ_ONLY_TABLES``), so nothing reachable from the API can grant a capability. Grants are
    never deleted: revocation sets ``revoked_at`` and keeps the record.
    """

    __tablename__ = "platform_capability_grant"
    __table_args__ = (
        Index(
            "uq_platform_capability_grant_active",
            "user_id",
            "capability",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    # RESTRICT: accounts are anonymised on closure, never deleted, so the grant history stays whole
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), index=True
    )
    capability: Mapped[PlatformCapability] = mapped_column(enum_column(PlatformCapability))
    # the person behind the account (named accounts only) and why they hold it
    holder_name: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    # the operator who ran the CLI (free text: the CLI runs on the server, outside any web session)
    granted_by: Mapped[str] = mapped_column(String(200))
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(200))
    revoke_reason: Mapped[str | None] = mapped_column(Text)
