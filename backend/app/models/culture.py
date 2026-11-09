"""Cultural depth (ADR-0026): a family's own kinship words and its traditions archive.

All tables are tree-scoped with row-level security. Nothing here is inferred: a kinship word is
chosen from recorded edges and never sets them; a tradition is what a family member wrote.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ReviewMixin, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import RecordPrivacyLevel, TraditionKind, TraditionLinkTarget


class KinshipOverride(TreeScopedMixin, ReviewMixin, Base):
    """A family's own word for a kinship pattern ("Bhayo" for bhabhi), tree-wide or per branch (§6)."""

    __tablename__ = "kinship_override"
    __table_args__ = (
        tree_unique("kinship_override"),
        tree_fk(["branch_id"], "family_branch"),
        # one word per (pattern, language, branch); NULLS NOT DISTINCT makes the tree-wide row unique
        UniqueConstraint(
            "tree_id",
            "pattern",
            "lang",
            "branch_id",
            name="uq_kinship_override_pattern",
            postgresql_nulls_not_distinct=True,
        ),
    )

    pattern: Mapped[str] = mapped_column(String(200))
    lang: Mapped[str] = mapped_column(String(16))
    region: Mapped[str | None] = mapped_column(String(40))
    word: Mapped[str] = mapped_column(String(120))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class TraditionEntry(TreeScopedMixin, ReviewMixin, Base):
    """A ritual guide, custom, song, recipe or story a family keeps (§7). Never on public trees."""

    __tablename__ = "tradition_entry"
    __table_args__ = (
        tree_unique("tradition_entry"),
        tree_fk(["branch_id"], "family_branch", ondelete="SET NULL"),
        # ADR-0027 §2: the entry's owner is a membership; leaving the tree orphans the entry
        tree_fk(["owner_membership_id"], "tree_membership", ondelete="SET NULL"),
        Index("ix_tradition_entry_tree_kind", "tree_id", "kind"),
        Index(
            "ix_tradition_entry_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    kind: Mapped[TraditionKind] = mapped_column(enum_column(TraditionKind))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    language: Mapped[str | None] = mapped_column(String(16))
    script: Mapped[str | None] = mapped_column(String(16))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # a record audience (ADR-0027): Only me / Selected members / Selected branch (branch_id) / family
    privacy_level: Mapped[RecordPrivacyLevel] = mapped_column(
        enum_column(RecordPrivacyLevel, "tradition_privacy_level"),
        default=RecordPrivacyLevel.TREE_MEMBERS,
        server_default=RecordPrivacyLevel.TREE_MEMBERS.value,
    )
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    # ADR-0027 §8.2: set while a takedown suspension is in effect (hidden from all but its owner)
    suspended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class TraditionLink(TreeScopedMixin, Base):
    """A tradition's link to a person, event or place in the same tree."""

    __tablename__ = "tradition_link"
    __table_args__ = (
        tree_unique("tradition_link"),
        tree_fk(["tradition_id"], "tradition_entry"),
        UniqueConstraint("tradition_id", "target_type", "target_id", name="uq_tradition_link"),
        Index("ix_tradition_link_target", "tree_id", "target_type", "target_id"),
    )

    tradition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target_type: Mapped[TraditionLinkTarget] = mapped_column(enum_column(TraditionLinkTarget))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
