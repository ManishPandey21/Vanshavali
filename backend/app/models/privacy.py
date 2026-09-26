from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import ClaimKind, ClaimStatus, ConsentBasis, PrivacyLevel, Role


class ConsentRecord(TreeScopedMixin, Base):
    """PRS §31 consent ledger. Rows are never deleted; withdrawal sets withdrawn_at."""

    __tablename__ = "consent_record"
    __table_args__ = (
        tree_unique("consent_record"),
        tree_fk(["subject_person_id"], "person"),
        tree_fk(["evidence_document_id"], "document", ondelete="SET NULL"),
        Index("ix_consent_subject", "tree_id", "subject_person_id"),
    )

    subject_person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    granted_by_name: Mapped[str] = mapped_column(String(200))
    authority_basis: Mapped[ConsentBasis] = mapped_column(enum_column(ConsentBasis))
    purpose: Mapped[str] = mapped_column(String(300))
    data_categories: Mapped[list[str]] = mapped_column(ARRAY(String(60)))
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)


class ProfileClaim(TreeScopedMixin, Base):
    """PRS §29 claim-your-profile workflow."""

    __tablename__ = "profile_claim"
    __table_args__ = (
        tree_unique("profile_claim"),
        tree_fk(["person_id"], "person"),
        tree_fk(["invite_id"], "profile_claim_invite", ondelete="SET NULL"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE")
    )
    kind: Mapped[ClaimKind] = mapped_column(
        enum_column(ClaimKind), default=ClaimKind.CLAIM, server_default=ClaimKind.CLAIM.value
    )
    status: Mapped[ClaimStatus] = mapped_column(
        enum_column(ClaimStatus), default=ClaimStatus.REQUESTED, server_default=ClaimStatus.REQUESTED.value
    )
    message: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    # Set when the claim came from a shareable invite (ADR-0011): the claimant's own notice and
    # consent, turned into a consent_record only if an admin approves the claim.
    invite_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    consent_version: Mapped[str | None] = mapped_column(String(40))
    consent_language: Mapped[str | None] = mapped_column(String(10))
    consent_sha256: Mapped[str | None] = mapped_column(String(64))
    consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # Removal requests hide the profile at once; this is the level to restore if an admin declines.
    restore_privacy_level: Mapped[PrivacyLevel | None] = mapped_column(
        enum_column(PrivacyLevel, "restore_privacy_level")
    )


class FamilyDataAttestation(TreeScopedMixin, Base):
    """ADR-0011: a user's confirmation before adding family members to a tree.

    An accountability record for the person entering data, **not** the relatives' consent.
    Rows are never deleted; withdrawal sets ``withdrawn_at``.
    """

    __tablename__ = "family_data_attestation"
    __table_args__ = (
        tree_unique("family_data_attestation"),
        Index("ix_family_data_attestation_user", "tree_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE")
    )
    statement_version: Mapped[str] = mapped_column(String(40))
    language: Mapped[str] = mapped_column(String(10))
    statement_sha256: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileClaimInvite(TreeScopedMixin, Base):
    """ADR-0011: single-use bearer link asking a relative to claim their profile.

    Accepting it only files a ``profile_claim``; it never grants tree access by itself.
    """

    __tablename__ = "profile_claim_invite"
    __table_args__ = (
        tree_unique("profile_claim_invite"),
        UniqueConstraint("token_hash", name="uq_profile_claim_invite_token_hash"),
        tree_fk(["person_id"], "person"),
        tree_fk(["branch_id"], "family_branch", ondelete="SET NULL"),
        Index("ix_profile_claim_invite_person", "tree_id", "person_id"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    token_hash: Mapped[str] = mapped_column(String(64))
    offered_role: Mapped[Role] = mapped_column(enum_column(Role, "claim_invite_role"))
    # The inviter's branch scope; a membership created on approval never gets a wider scope.
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # "This isn't me": the link reached the wrong person. Nothing else changes.
    declined_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
