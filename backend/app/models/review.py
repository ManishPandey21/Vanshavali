"""Change proposals, revision history and in-app notifications (ADR-0021).

All tree-scoped with row-level security. Targets are referenced by type and id without foreign
keys: history must outlive a deleted record (only erasure removes it), and a proposal whose target
disappears simply becomes stale.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import (
    ChangeProposalStatus,
    NotificationKind,
    ProposalKind,
    ProposalOp,
    ReviewTarget,
)


class ChangeProposal(TreeScopedMixin, Base):
    __tablename__ = "change_proposal"
    __table_args__ = (
        tree_unique("change_proposal"),
        tree_fk(["supersedes_id"], "change_proposal", ondelete="SET NULL"),
        Index("ix_change_proposal_status", "tree_id", "status", "created_at"),
        Index("ix_change_proposal_person", "tree_id", "person_id"),
    )

    proposer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[ProposalKind] = mapped_column(enum_column(ProposalKind), default=ProposalKind.CHANGE)
    status: Mapped[ChangeProposalStatus] = mapped_column(
        enum_column(ChangeProposalStatus, "change_proposal_status"),
        default=ChangeProposalStatus.DRAFT,
        server_default=ChangeProposalStatus.DRAFT.value,
    )
    rationale: Mapped[str] = mapped_column(Text, default="", server_default="")
    # the person the proposal is mainly about (for "1 change awaiting review" on their page)
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # a challenge names the fact it disputes
    target_type: Mapped[ReviewTarget | None] = mapped_column(
        enum_column(ReviewTarget, "challenge_target_type"), nullable=True
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ChangeProposalItem(TreeScopedMixin, Base):
    __tablename__ = "change_proposal_item"
    __table_args__ = (
        tree_unique("change_proposal_item"),
        tree_fk(["proposal_id"], "change_proposal"),
        Index("ix_change_proposal_item_proposal", "tree_id", "proposal_id"),
        Index("ix_change_proposal_item_target", "tree_id", "target_type", "target_id"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    target_type: Mapped[ReviewTarget] = mapped_column(enum_column(ReviewTarget))
    op: Mapped[ProposalOp] = mapped_column(enum_column(ProposalOp))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # empty for a create
    # the person a create belongs to (a new name or vital), or a relationship's first person
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    patch: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    # "<type>:<id>" -> revision the item was proposed against (ADR-0021 §3, §5)
    base_revisions: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict, server_default="{}")


class ProposalCitation(TreeScopedMixin, Base):
    __tablename__ = "proposal_citation"
    __table_args__ = (
        tree_unique("proposal_citation"),
        tree_fk(["proposal_id"], "change_proposal"),
        tree_fk(["source_id"], "source"),
        Index("ix_proposal_citation_proposal", "tree_id", "proposal_id"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(String(500))


class ProposalComment(TreeScopedMixin, Base):
    __tablename__ = "proposal_comment"
    __table_args__ = (
        tree_unique("proposal_comment"),
        tree_fk(["proposal_id"], "change_proposal"),
        Index("ix_proposal_comment_proposal", "tree_id", "proposal_id", "created_at"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    body: Mapped[str] = mapped_column(Text)


class RecordRevision(TreeScopedMixin, Base):
    """One change to one record: only the fields that changed, before and after (ADR-0021 §3).

    Holds values, unlike the audit log: read only through per-field redaction, erased with the
    person, never exported.
    """

    __tablename__ = "record_revision"
    __table_args__ = (
        tree_unique("record_revision"),
        Index("ix_record_revision_record", "tree_id", "record_type", "record_id", "revision"),
        Index("ix_record_revision_person", "tree_id", "person_id", "created_at"),
        Index("ix_record_revision_person_b", "tree_id", "person_b_id"),
    )

    record_type: Mapped[ReviewTarget] = mapped_column(enum_column(ReviewTarget))
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer)
    op: Mapped[ProposalOp] = mapped_column(enum_column(ProposalOp))
    # the person(s) the record belongs to: owner of a name/claim, a relationship's two people,
    # the principal of a vital; used for a person's history and for erasure
    person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    person_b_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class UserNotification(TreeScopedMixin, Base):
    """An in-app notification: ids and a kind only, never names or values (ADR-0021 §7)."""

    __tablename__ = "user_notification"
    __table_args__ = (
        tree_unique("user_notification"),
        Index("ix_user_notification_user", "tree_id", "user_id", "read_at", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[NotificationKind] = mapped_column(enum_column(NotificationKind))
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
