from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import JobStatus


class ImportJob(TreeScopedMixin, Base):
    __tablename__ = "import_job"
    __table_args__ = (tree_unique("import_job"), tree_fk(["document_id"], "document", ondelete="SET NULL"))

    format: Mapped[str] = mapped_column(String(20), default="gedcom")
    status: Mapped[JobStatus] = mapped_column(enum_column(JobStatus), default=JobStatus.PENDING)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    original_filename: Mapped[str | None] = mapped_column(String(400))
    # immutable encrypted copy of the uploaded file (object store key; ADR-0008 "keep the original")
    original_storage_key: Mapped[str | None] = mapped_column(String(500))
    detected_version: Mapped[str | None] = mapped_column(String(20))
    detected_encoding: Mapped[str | None] = mapped_column(String(40))
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    staged: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    decisions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    committed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ExportJob(TreeScopedMixin, Base):
    __tablename__ = "export_job"
    __table_args__ = (tree_unique("export_job"),)

    kind: Mapped[str] = mapped_column(String(20))  # gedcom | archive
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[JobStatus] = mapped_column(enum_column(JobStatus), default=JobStatus.PENDING)
    storage_key: Mapped[str | None] = mapped_column(String(500))
    filename: Mapped[str | None] = mapped_column(String(300))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class GedcomExtension(TreeScopedMixin, Base):
    """Unknown/unsupported GEDCOM structures preserved verbatim for round-tripping (ADR-0008)."""

    __tablename__ = "gedcom_extension"
    __table_args__ = (
        tree_unique("gedcom_extension"),
        tree_fk(["person_id"], "person"),
        tree_fk(["import_job_id"], "import_job", ondelete="SET NULL"),
        Index("ix_gedcom_extension_person", "tree_id", "person_id"),
    )

    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    record_type: Mapped[str] = mapped_column(String(20))
    tag: Mapped[str] = mapped_column(String(80))
    uri: Mapped[str | None] = mapped_column(String(500))
    payload: Mapped[str] = mapped_column(Text)  # raw GEDCOM lines, levels relative to the structure
