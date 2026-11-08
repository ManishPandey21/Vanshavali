"""Master data: extensible vocabularies (ADR-0018).

``vocabulary`` and ``vocabulary_term`` are global reference data loaded from versioned packs
(``app/modules/masterdata/packs``); they hold nothing about any family. A family's own entries
live in the tree-scoped ``tree_vocabulary_term`` (row-level security).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, TreeScopedMixin, enum_column, tree_unique
from app.models.enums import OfferStatus, VocabularyTermStatus


class Vocabulary(TimestampMixin, Base):
    __tablename__ = "vocabulary"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(String(120))
    allows_custom: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


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
    # offered to the common suggestion lists (ADR-0026 §4); who offered stays private to operators
    offer_status: Mapped[OfferStatus] = mapped_column(
        enum_column(OfferStatus), default=OfferStatus.NONE, server_default=OfferStatus.NONE.value
    )
    offered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    offered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    offer_note: Mapped[str | None] = mapped_column(String(500))
    offer_temple: Mapped[str | None] = mapped_column(String(200))
    # the global term this entry became once promoted by a code-reviewed pack change
    promoted_code: Mapped[str | None] = mapped_column(String(80))
