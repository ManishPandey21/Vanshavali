from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import (
    GrantPermission,
    GrantResource,
    NominationStatus,
    PrivacyLevel,
    PublicMode,
    ReviewPolicy,
)


class Tree(TimestampMixin, Base):
    __tablename__ = "tree"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    public_mode: Mapped[PublicMode] = mapped_column(
        enum_column(PublicMode), default=PublicMode.OFF, server_default=PublicMode.OFF.value
    )
    default_person_privacy: Mapped[PrivacyLevel] = mapped_column(
        enum_column(PrivacyLevel, "default_person_privacy"),
        default=PrivacyLevel.TREE_MEMBERS,
        server_default=PrivacyLevel.TREE_MEMBERS.value,
    )
    # which direct writes need family review (ADR-0021 §1); off = everything is written directly
    review_policy: Mapped[ReviewPolicy] = mapped_column(
        enum_column(ReviewPolicy),
        default=ReviewPolicy.OFF,
        server_default=ReviewPolicy.OFF.value,
    )
    # the tree's default kinship words (ADR-0026 §6); a member's own choice comes first
    kinship_lang: Mapped[str | None] = mapped_column(String(16))
    kinship_region: Mapped[str | None] = mapped_column(String(40))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class TreeMembership(TreeScopedMixin, Base):
    __tablename__ = "tree_membership"
    __table_args__ = (
        tree_unique("tree_membership"),
        UniqueConstraint("tree_id", "user_id", name="uq_tree_membership_tree_user"),
        CheckConstraint("cardinality(roles) > 0", name="roles_not_empty"),
        tree_fk(["branch_id"], "family_branch", ondelete="SET NULL"),
        tree_fk(["linked_person_id"], "person", ondelete="SET NULL"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    linked_person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class TreeInvitation(TreeScopedMixin, Base):
    __tablename__ = "tree_invitation"
    __table_args__ = (
        tree_unique("tree_invitation"),
        tree_fk(["branch_id"], "family_branch", ondelete="SET NULL"),
    )

    email: Mapped[str] = mapped_column(String(320))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class AccessGrant(TreeScopedMixin, Base):
    """Explicit share of one resource with one member (CUSTOM privacy, vault downloads)."""

    __tablename__ = "access_grant"
    __table_args__ = (
        tree_unique("access_grant"),
        UniqueConstraint(
            "tree_id", "user_id", "resource_type", "resource_id", "permission", name="uq_access_grant"
        ),
        Index("ix_access_grant_lookup", "tree_id", "resource_type", "resource_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE")
    )
    resource_type: Mapped[GrantResource] = mapped_column(enum_column(GrantResource))
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    permission: Mapped[GrantPermission] = mapped_column(enum_column(GrantPermission))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminNomination(TreeScopedMixin, Base):
    """A Family Admin's nomination of a member for Family Admin (ADR-0006 amendment of 9 Nov 2026).

    Never grants anything by itself: the nominee accepts, then an Owner approves through the normal
    role-change path. The reason is visible to Owners, Family Admins and the nominee while the
    nomination is open, and is erased when it closes; the audit log never holds it.
    """

    __tablename__ = "admin_nomination"
    __table_args__ = (
        tree_unique("admin_nomination"),
        tree_fk(["nominee_membership_id"], "tree_membership", ondelete="SET NULL"),
        CheckConstraint("char_length(reason) <= 500", name="reason_length"),
        # at most one open nomination per nominee
        Index(
            "uq_admin_nomination_open_nominee",
            "tree_id",
            "nominee_membership_id",
            unique=True,
            postgresql_where="status = 'open'",
        ),
        Index("ix_admin_nomination_status", "tree_id", "status", "expires_at"),
    )

    nominator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    nominee_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    nominee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[NominationStatus] = mapped_column(
        enum_column(NominationStatus),
        default=NominationStatus.OPEN,
        server_default=NominationStatus.OPEN.value,
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    nominee_accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
