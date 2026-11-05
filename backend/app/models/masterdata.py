"""Master data: extensible vocabularies (ADR-0018).

``vocabulary`` and ``vocabulary_term`` are global reference data loaded from versioned packs
(``app/modules/masterdata/packs``); they hold nothing about any family. A family's own entries
live in the tree-scoped ``tree_vocabulary_term`` (row-level security).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, TreeScopedMixin, enum_column, tree_unique
from app.models.enums import (
    VocabularyChangeAction,
    VocabularyChangeStatus,
    VocabularyTermManagedBy,
    VocabularyTermStatus,
)


class Vocabulary(TimestampMixin, Base):
    __tablename__ = "vocabulary"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(String(120))
    allows_custom: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # ADR-0025: console grouping, whether admins may add/retire terms (closed sets), and a counter
    # bumped on every published change so clients can tell their cached list is out of date
    category: Mapped[str] = mapped_column(String(40), default="other", server_default="other")
    fixed_membership: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class VocabularyTerm(TimestampMixin, Base):
    __tablename__ = "vocabulary_term"
    __table_args__ = (UniqueConstraint("vocabulary_key", "code", name="uq_vocabulary_term_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    vocabulary_key: Mapped[str] = mapped_column(
        String(40), ForeignKey("vocabulary.key", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(80))
    labels: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list, server_default="{}")
    scope: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list, server_default="{}")
    parent_code: Mapped[str | None] = mapped_column(String(80))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    source_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[VocabularyTermStatus] = mapped_column(
        enum_column(VocabularyTermStatus),
        default=VocabularyTermStatus.DRAFT,
        server_default=VocabularyTermStatus.DRAFT.value,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # ADR-0025: optimistic concurrency, pack vs console ownership, successor of a retired term
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    managed_by: Mapped[VocabularyTermManagedBy] = mapped_column(
        enum_column(VocabularyTermManagedBy),
        default=VocabularyTermManagedBy.PACK,
        server_default=VocabularyTermManagedBy.PACK.value,
    )
    successor_code: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )


class VocabularyChange(Base):
    """A proposed change to one global term, and after publication its permanent history (ADR-0025).

    ``previous`` is the term as it was when the change was proposed (empty for a new term) and
    ``proposed`` the complete set of editable fields after the change. Global reference data only:
    nothing here describes a family.
    """

    __tablename__ = "vocabulary_change"
    __table_args__ = (
        Index("ix_vocabulary_change_vocabulary_status", "vocabulary_key", "status"),
        Index("ix_vocabulary_change_term", "vocabulary_key", "term_code"),
        # at most one open change per term
        Index(
            "uq_vocabulary_change_one_pending",
            "vocabulary_key",
            "term_code",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    vocabulary_key: Mapped[str] = mapped_column(String(40), ForeignKey("vocabulary.key", ondelete="CASCADE"))
    term_code: Mapped[str] = mapped_column(String(80))
    action: Mapped[VocabularyChangeAction] = mapped_column(enum_column(VocabularyChangeAction))
    status: Mapped[VocabularyChangeStatus] = mapped_column(
        enum_column(VocabularyChangeStatus),
        default=VocabularyChangeStatus.PENDING,
        server_default=VocabularyChangeStatus.PENDING.value,
    )
    # the term revision the change was prepared against (None for a new term)
    base_revision: Mapped[int | None] = mapped_column(Integer)
    previous: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    proposed: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    reason: Mapped[str] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text)
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    proposed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class TreeVocabularyTerm(TreeScopedMixin, Base):
    """A family's own entry ("Add my own"), visible only inside its tree."""

    __tablename__ = "tree_vocabulary_term"
    __table_args__ = (
        tree_unique("tree_vocabulary_term"),
        UniqueConstraint("tree_id", "vocabulary_key", "code", name="uq_tree_vocabulary_term_code"),
    )

    vocabulary_key: Mapped[str] = mapped_column(String(40), ForeignKey("vocabulary.key", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(90))
    label: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list, server_default="{}")
