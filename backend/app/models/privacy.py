from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import ClaimStatus, ConsentBasis


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
    __table_args__ = (tree_unique("profile_claim"), tree_fk(["person_id"], "person"))

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE")
    )
    status: Mapped[ClaimStatus] = mapped_column(
        enum_column(ClaimStatus), default=ClaimStatus.REQUESTED, server_default=ClaimStatus.REQUESTED.value
    )
    message: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
