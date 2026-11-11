"""Reports and suspensions of shareable records (ADR-0027 §8.2, takedown).

A report is about one record (a document, a tradition entry or a photo collection) and holds a
reason and the reporter's own note, never the record's content. A suspension hides the record from
everyone but its owner until it is lifted; the owner may appeal once. The record itself carries
``suspended_at`` so every access check can see it without another query.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import (
    AppealStatus,
    DecisionReason,
    GrantResource,
    ReportReason,
    ReportStatus,
    SuspensionStatus,
)


class RecordReport(TreeScopedMixin, Base):
    __tablename__ = "record_report"
    __table_args__ = (
        tree_unique("record_report"),
        tree_fk(["reporter_membership_id"], "tree_membership", ondelete="SET NULL"),
        CheckConstraint("char_length(note) <= 500", name="note_length"),
        Index("ix_record_report_resource", "tree_id", "resource_type", "resource_id"),
        Index("ix_record_report_status", "tree_id", "status"),
    )

    reference: Mapped[str] = mapped_column(String(12), unique=True)
    resource_type: Mapped[GrantResource] = mapped_column(enum_column(GrantResource, "report_resource"))
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[ReportReason] = mapped_column(enum_column(ReportReason))
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    # protected: never shown to the record's owner or in any notice (ADR-0027 §8.2 detail 1)
    reporter_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[ReportStatus] = mapped_column(
        enum_column(ReportStatus), default=ReportStatus.OPEN, server_default=ReportStatus.OPEN.value
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[DecisionReason | None] = mapped_column(
        enum_column(DecisionReason, "report_review_reason")
    )


class RecordSuspension(TreeScopedMixin, Base):
    __tablename__ = "record_suspension"
    __table_args__ = (
        tree_unique("record_suspension"),
        tree_fk(["report_id"], "record_report"),
        CheckConstraint("char_length(appeal_note) <= 1000", name="appeal_note_length"),
        CheckConstraint("char_length(decision_note) <= 1000", name="decision_note_length"),
        # at most one suspension in effect per record
        Index(
            "uq_record_suspension_active",
            "tree_id",
            "resource_type",
            "resource_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_record_suspension_appeal_due", "tree_id", "appeal_status", "appeal_due_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    resource_type: Mapped[GrantResource] = mapped_column(enum_column(GrantResource, "suspension_resource"))
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    suspended_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[SuspensionStatus] = mapped_column(
        enum_column(SuspensionStatus),
        default=SuspensionStatus.ACTIVE,
        server_default=SuspensionStatus.ACTIVE.value,
    )
    appeal_status: Mapped[AppealStatus] = mapped_column(
        enum_column(AppealStatus), default=AppealStatus.NONE, server_default=AppealStatus.NONE.value
    )
    appeal_note: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    appealed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    appeal_due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[DecisionReason | None] = mapped_column(enum_column(DecisionReason))
    decision_note: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    sole_reviewer: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
