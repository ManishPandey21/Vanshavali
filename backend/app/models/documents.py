from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import (
    DerivativeKind,
    DocumentCategory,
    DocumentLinkTarget,
    ProcessingStatus,
    ProposalStatus,
    RecordPrivacyLevel,
    ScanStatus,
    StorageClass,
)


class Document(TreeScopedMixin, Base):
    __tablename__ = "document"
    __table_args__ = (
        tree_unique("document"),
        # Not unique: identical files may exist independently when one is hidden from the uploader
        # (SEC-10). Duplicate uploads of *visible* files are refused in the service layer.
        Index("ix_document_tree_checksum", "tree_id", "checksum_sha256"),
        # ADR-0027 §2: the content owner is a membership; leaving the tree orphans the record
        tree_fk(["owner_membership_id"], "tree_membership", ondelete="SET NULL"),
        tree_fk(["pending_owner_membership_id"], "tree_membership", ondelete="SET NULL"),
        tree_fk(["audience_branch_id"], "family_branch", ondelete="SET NULL"),
    )

    category: Mapped[DocumentCategory] = mapped_column(enum_column(DocumentCategory))
    storage_class: Mapped[StorageClass] = mapped_column(enum_column(StorageClass))
    title: Mapped[str] = mapped_column(String(400))
    description: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(400))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    encryption_key_id: Mapped[str] = mapped_column(String(40))
    document_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    language: Mapped[str | None] = mapped_column(String(16))
    script: Mapped[str | None] = mapped_column(String(20))
    issuing_authority: Mapped[str | None] = mapped_column(String(300))
    privacy_level: Mapped[RecordPrivacyLevel] = mapped_column(enum_column(RecordPrivacyLevel, "privacylevel"))
    # ADR-0027: who owns the record, which branch "Selected branch" means, and whether viewers may
    # also download the original (view = metadata, thumbnail, preview, playback)
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # ADR-0027 §2: a member the owner offered the record to, until they accept or decline
    pending_owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    audience_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    allow_download: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    retention_policy: Mapped[str] = mapped_column(String(40), default="retain", server_default="retain")
    scan_status: Mapped[ScanStatus] = mapped_column(enum_column(ScanStatus), default=ScanStatus.PENDING)
    scan_engine: Mapped[str | None] = mapped_column(String(80))
    page_count: Mapped[int | None] = mapped_column(Integer)
    ocr_status: Mapped[ProcessingStatus] = mapped_column(
        enum_column(ProcessingStatus, "ocr_status"), default=ProcessingStatus.NOT_REQUESTED
    )
    ocr_engine: Mapped[str | None] = mapped_column(String(120))
    ocr_error: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[ProcessingStatus] = mapped_column(
        enum_column(ProcessingStatus, "extraction_status"), default=ProcessingStatus.NOT_REQUESTED
    )
    preview_status: Mapped[ProcessingStatus] = mapped_column(
        enum_column(ProcessingStatus, "preview_status"), default=ProcessingStatus.NOT_REQUESTED
    )
    metadata_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DocumentMetadataVersion(TreeScopedMixin, Base):
    __tablename__ = "document_metadata_version"
    __table_args__ = (
        tree_unique("document_metadata_version"),
        tree_fk(["document_id"], "document"),
        UniqueConstraint("document_id", "version", name="uq_document_metadata_version"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class DocumentDerivative(TreeScopedMixin, Base):
    __tablename__ = "document_derivative"
    __table_args__ = (
        tree_unique("document_derivative"),
        tree_fk(["document_id"], "document"),
        UniqueConstraint("document_id", "kind", "page", name="uq_document_derivative"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[DerivativeKind] = mapped_column(enum_column(DerivativeKind))
    page: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    storage_key: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    engine: Mapped[str | None] = mapped_column(String(120))


class DocumentLink(TreeScopedMixin, Base):
    __tablename__ = "document_link"
    __table_args__ = (
        tree_unique("document_link"),
        tree_fk(["document_id"], "document"),
        UniqueConstraint("document_id", "target_type", "target_id", name="uq_document_link"),
        Index("ix_document_link_target", "tree_id", "target_type", "target_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_type: Mapped[DocumentLinkTarget] = mapped_column(enum_column(DocumentLinkTarget))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(String(300))


class ExtractionProposal(TreeScopedMixin, Base):
    """OCR/AI output — a proposal only (ADR-0009). Never read as canonical data."""

    __tablename__ = "extraction_proposal"
    __table_args__ = (
        tree_unique("extraction_proposal"),
        tree_fk(["document_id"], "document"),
        tree_fk(["subject_person_id"], "person", ondelete="SET NULL"),
        tree_fk(["subject_property_id"], "property", ondelete="SET NULL"),
        Index("ix_extraction_proposal_doc", "tree_id", "document_id", "status"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    subject_person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    extractor: Mapped[str] = mapped_column(String(80))
    extractor_version: Mapped[str] = mapped_column(String(40))
    engine: Mapped[str | None] = mapped_column(String(120))
    field: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200))
    proposed_value: Mapped[Any] = mapped_column(JSONB)
    display_value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.0)
    source_location: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[ProposalStatus] = mapped_column(
        enum_column(ProposalStatus),
        default=ProposalStatus.PENDING,
        server_default=ProposalStatus.PENDING.value,
    )
    final_value: Mapped[Any | None] = mapped_column(JSONB)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    applied_target_type: Mapped[str | None] = mapped_column(String(40))
    applied_target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class EventMedia(TreeScopedMixin, Base):
    """A photo in an event's album (ADR-0015). The photo itself is an ordinary vault document;
    people shown in it are ``document_link`` rows to ``person``."""

    __tablename__ = "event_media"
    __table_args__ = (
        tree_unique("event_media"),
        tree_fk(["event_id"], "event"),
        tree_fk(["document_id"], "document"),
        UniqueConstraint("event_id", "document_id", name="uq_event_media"),
        Index("ix_event_media_event", "tree_id", "event_id", "sort_order"),
        # at most one cover photo per event
        Index(
            "uq_event_media_cover",
            "event_id",
            unique=True,
            postgresql_where=text("is_cover"),
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    caption: Mapped[str | None] = mapped_column(String(500))
    taken_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
