"""Reference vocabularies: global typing-aid lists for searchable fields (ADR-0019).

Not tree data: no ``tree_id``, no row-level security, no personal data. Written only by the
``load_vocabularies`` command; the API is read-only. Records elsewhere store a term's ``code``
together with the text as recorded — a vocabulary never validates user input away.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    # cascade: terms of this vocabulary have a parent term in that vocabulary (district -> state)
    parent_vocabulary_code: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("vocabulary.code", ondelete="SET NULL")
    )
    version: Mapped[str] = mapped_column(String(40))
    source: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VocabularyTerm(Base):
    __tablename__ = "vocabulary_term"
    __table_args__ = (
        UniqueConstraint("vocabulary_code", "code", name="uq_vocabulary_term_code"),
        Index("ix_vocabulary_term_parent", "vocabulary_code", "parent_id"),
        Index(
            "ix_vocabulary_term_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    vocabulary_code: Mapped[str] = mapped_column(
        String(40), ForeignKey("vocabulary.code", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vocabulary_term.id", ondelete="SET NULL")
    )
    label: Mapped[str] = mapped_column(String(300))
    labels: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list, server_default="{}")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
