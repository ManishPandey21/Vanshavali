from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    EvidenceMixin,
    ProvenanceMixin,
    TreeScopedMixin,
    enum_column,
    tree_fk,
    tree_unique,
)
from app.models.enums import AssertionSubject, PrivacyLevel, ValueStatus


class Assertion(TreeScopedMixin, EvidenceMixin, ProvenanceMixin, Base):
    """A claim about a person or branch attribute (heritage and other facts; ADR-0003).

    Several assertions per (subject, attribute) may coexist; at most one is preferred. Values are
    only ever created by explicit user input or reviewed extraction — never inferred.
    """

    __tablename__ = "assertion"
    __table_args__ = (
        tree_unique("assertion"),
        tree_fk(["person_id"], "person"),
        tree_fk(["branch_id"], "family_branch"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        CheckConstraint(
            "(subject_type = 'person' AND person_id IS NOT NULL AND branch_id IS NULL) OR "
            "(subject_type = 'branch' AND branch_id IS NOT NULL AND person_id IS NULL)",
            name="subject_matches",
        ),
        Index("ix_assertion_subject", "tree_id", "person_id", "branch_id", "attribute"),
    )

    subject_type: Mapped[AssertionSubject] = mapped_column(enum_column(AssertionSubject))
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attribute: Mapped[str] = mapped_column(String(60))
    value_text: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[Any | None] = mapped_column(JSONB)
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    value_status: Mapped[ValueStatus] = mapped_column(
        enum_column(ValueStatus), default=ValueStatus.KNOWN, server_default=ValueStatus.KNOWN.value
    )
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    privacy_level: Mapped[PrivacyLevel | None] = mapped_column(enum_column(PrivacyLevel), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
