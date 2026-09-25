from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Date, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import CitationTarget, Confidence, PrivacyLevel, SourceType


class Source(TreeScopedMixin, Base):
    __tablename__ = "source"
    __table_args__ = (
        tree_unique("source"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        tree_fk(["document_id"], "document", ondelete="SET NULL"),
    )

    source_type: Mapped[SourceType] = mapped_column(enum_column(SourceType), default=SourceType.OTHER)
    title: Mapped[str] = mapped_column(String(400))
    issuing_authority: Mapped[str | None] = mapped_column(String(300))
    repository: Mapped[str | None] = mapped_column(String(300))
    record_number: Mapped[str | None] = mapped_column(String(200))
    date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    place_text: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(1000))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    transcription: Mapped[str | None] = mapped_column(Text)
    translation: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Traditional genealogy record details (PRS §20): tradition_type, custodian, pilgrimage_place,
    # volume, page, family_origin_place, verification_status.
    tradition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    privacy_level: Mapped[PrivacyLevel] = mapped_column(
        enum_column(PrivacyLevel),
        default=PrivacyLevel.TREE_MEMBERS,
        server_default=PrivacyLevel.TREE_MEMBERS.value,
    )


class Citation(TreeScopedMixin, Base):
    """Links a Source to one claim. target_type/target_id is validated by the service in-tree."""

    __tablename__ = "citation"
    __table_args__ = (
        tree_unique("citation"),
        tree_fk(["source_id"], "source"),
        Index("ix_citation_target", "tree_id", "target_type", "target_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_type: Mapped[CitationTarget] = mapped_column(enum_column(CitationTarget))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    page_or_image: Mapped[str | None] = mapped_column(String(200))
    text_excerpt: Mapped[str | None] = mapped_column(Text)
    accessed_date: Mapped[dt.date | None] = mapped_column(Date)
    confidence: Mapped[Confidence] = mapped_column(
        enum_column(Confidence), default=Confidence.UNKNOWN, server_default=Confidence.UNKNOWN.value
    )
