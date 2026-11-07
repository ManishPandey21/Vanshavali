"""Declarative base, shared column helpers and tree-scoping conventions (ADR-0002)."""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.core.ids import uuid7
from app.models.enums import Confidence, EvidenceStatus, ProvenanceOrigin, ReviewState

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def enum_column(enum_cls: type[StrEnum], name: str | None = None) -> Enum:
    """Portable string enum with a CHECK constraint; values (not names) are stored."""
    return Enum(
        enum_cls,
        name=name or f"{enum_cls.__name__.lower()}",
        native_enum=False,
        create_constraint=True,
        length=40,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


def tree_fk(
    columns: list[str], target_table: str, *, ondelete: str = "CASCADE", name: str | None = None
) -> ForeignKeyConstraint:
    """Composite FK ``(tree_id, <col>) -> <target>(tree_id, id)`` so rows never cross trees.

    ``ondelete`` applies to the whole constraint. For nullable references use ``SET NULL`` with a
    column list so only the reference column is cleared (PostgreSQL 15+).
    """
    kwargs: dict[str, Any] = {}
    if ondelete == "SET NULL":
        # only null the reference column, never tree_id
        ondelete = f"SET NULL ({columns[0]})"
    return ForeignKeyConstraint(
        ["tree_id", *columns],
        [f"{target_table}.tree_id", f"{target_table}.id"],
        ondelete=ondelete,
        name=name,
        **kwargs,
    )


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TreeScopedMixin(TimestampMixin):
    """Primary key + tree_id + audit columns. Subclasses must include ``tree_unique()`` in __table_args__."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)

    @declared_attr
    def tree_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(UUID(as_uuid=True), ForeignKey("tree.id", ondelete="CASCADE"), index=True)

    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
        )

    @declared_attr
    def updated_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
        )


def tree_unique(table: str) -> UniqueConstraint:
    return UniqueConstraint("tree_id", "id", name=f"uq_{table}_tree_id_id")


class EvidenceMixin:
    evidence_status: Mapped[EvidenceStatus] = mapped_column(
        enum_column(EvidenceStatus),
        default=EvidenceStatus.USER_ASSERTION,
        server_default=EvidenceStatus.USER_ASSERTION.value,
    )
    confidence: Mapped[Confidence] = mapped_column(
        enum_column(Confidence), default=Confidence.UNKNOWN, server_default=Confidence.UNKNOWN.value
    )


class ProvenanceMixin:
    """PRS §35: where an auto-extracted/calculated/imported value came from and who confirmed it."""

    prov_origin: Mapped[ProvenanceOrigin] = mapped_column(
        enum_column(ProvenanceOrigin),
        default=ProvenanceOrigin.MANUAL,
        server_default=ProvenanceOrigin.MANUAL.value,
    )
    prov_algorithm: Mapped[str | None] = mapped_column(String(120))
    prov_model_version: Mapped[str | None] = mapped_column(String(80))
    prov_source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    prov_source_location: Mapped[str | None] = mapped_column(Text)
    prov_extracted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    prov_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    prov_confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewMixin:
    """Revision counter and family review state (ADR-0021 §3, §6).

    ``revision`` is incremented by every change to the record's facts (``app.modules.review.revisions``
    does this in one flush hook for every write path). ``review_state`` is family review, never
    evidence: any later change sets it back to ``unreviewed``.
    """

    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    review_state: Mapped[ReviewState] = mapped_column(
        enum_column(ReviewState),
        default=ReviewState.UNREVIEWED,
        server_default=ReviewState.UNREVIEWED.value,
    )
    review_state_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    review_state_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
