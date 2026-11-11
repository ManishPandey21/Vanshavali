"""record takedown

Revision ID: d9b4f2c6a713
Revises: c7e3a1f5b829
Create Date: 2026-11-09

ADR-0027 §8.2 (takedown, detailed by the owner on 9 Nov 2026): `record_report` and
`record_suspension`, both tree-scoped with row-level security; `suspended_at` on document,
tradition_entry and photo_collection; seven takedown notification kinds. The downgrade deletes those
notices, both tables and the columns (a suspended record becomes visible again under its own
audience, which never changed while it was suspended).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "d9b4f2c6a713"
down_revision: str | None = "c7e3a1f5b829"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
NEW_RLS_TABLES = ("record_report", "record_suspension")
KINDS_BEFORE = (
    "'proposal_to_review', 'proposal_accepted', 'proposal_rejected', 'proposal_stale', "
    "'challenge_opened', 'challenge_upheld', 'challenge_dismissed', 'proposal_comment', "
    "'offer_accepted', 'offer_declined', "
    "'nomination_created', 'nomination_accepted', 'nomination_declined', 'nomination_approved', "
    "'nomination_rejected', 'nomination_expired', 'nomination_lapsed', "
    "'document_narrowed', 'tradition_narrowed'"
)
TAKEDOWN_KINDS = (
    "'record_reported', 'record_suspended', 'suspension_appealed', 'appeal_overdue', 'suspension_upheld', "
    "'suspension_lifted', 'report_reviewed'"
)
CHECK = "ck_user_notification_notificationkind"


def upgrade() -> None:
    op.create_table(
        "record_report",
        sa.Column("reference", sa.String(length=12), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("note", sa.String(length=500), server_default="", nullable=False),
        sa.Column("reporter_membership_id", sa.UUID(), nullable=True),
        sa.Column("reporter_user_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="open", nullable=False),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.String(length=40), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "reason IN ('abuse', 'harassment', 'privacy', 'intimate', 'copyright', 'other')",
            name=op.f("ck_record_report_reportreason"),
        ),
        sa.CheckConstraint(
            "resource_type IN ('person', 'document', 'property', 'tradition', 'collection')",
            name=op.f("ck_record_report_report_resource"),
        ),
        sa.CheckConstraint(
            "review_reason IN ('report_confirmed', 'mistaken_report', 'not_a_takedown_matter', 'owner_changed_the_record', 'other')",
            name=op.f("ck_record_report_report_review_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'dismissed', 'actioned')", name=op.f("ck_record_report_reportstatus")
        ),
        sa.CheckConstraint("char_length(note) <= 500", name=op.f("ck_record_report_note_length")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_record_report_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "reporter_membership_id"],
            ["tree_membership.tree_id", "tree_membership.id"],
            name=op.f("fk_record_report_tree_id_reporter_membership_id_tree_membership"),
            ondelete="SET NULL (reporter_membership_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_record_report_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_record_report_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_record_report")),
        sa.UniqueConstraint("reference", name=op.f("uq_record_report_reference")),
        sa.UniqueConstraint("tree_id", "id", name="uq_record_report_tree_id_id"),
    )
    op.create_index(
        "ix_record_report_resource",
        "record_report",
        ["tree_id", "resource_type", "resource_id"],
        unique=False,
    )
    op.create_index("ix_record_report_status", "record_report", ["tree_id", "status"], unique=False)
    op.create_index(op.f("ix_record_report_tree_id"), "record_report", ["tree_id"], unique=False)
    op.create_table(
        "record_suspension",
        sa.Column("report_id", sa.UUID(), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("suspended_by", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=40), server_default="active", nullable=False),
        sa.Column("appeal_status", sa.String(length=40), server_default="none", nullable=False),
        sa.Column("appeal_note", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("appealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("appeal_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(length=40), nullable=True),
        sa.Column("decision_note", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("sole_reviewer", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "appeal_status IN ('none', 'pending', 'upheld', 'lifted')",
            name=op.f("ck_record_suspension_appealstatus"),
        ),
        sa.CheckConstraint(
            "decision_reason IN ('report_confirmed', 'mistaken_report', 'not_a_takedown_matter', 'owner_changed_the_record', 'other')",
            name=op.f("ck_record_suspension_decisionreason"),
        ),
        sa.CheckConstraint(
            "resource_type IN ('person', 'document', 'property', 'tradition', 'collection')",
            name=op.f("ck_record_suspension_suspension_resource"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'lifted')", name=op.f("ck_record_suspension_suspensionstatus")
        ),
        sa.CheckConstraint(
            "char_length(appeal_note) <= 1000", name=op.f("ck_record_suspension_appeal_note_length")
        ),
        sa.CheckConstraint(
            "char_length(decision_note) <= 1000", name=op.f("ck_record_suspension_decision_note_length")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_record_suspension_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "report_id"],
            ["record_report.tree_id", "record_report.id"],
            name=op.f("fk_record_suspension_tree_id_report_id_record_report"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_record_suspension_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_record_suspension_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_record_suspension")),
        sa.UniqueConstraint("tree_id", "id", name="uq_record_suspension_tree_id_id"),
    )
    op.create_index(
        "ix_record_suspension_appeal_due",
        "record_suspension",
        ["tree_id", "appeal_status", "appeal_due_at"],
        unique=False,
    )
    op.create_index(op.f("ix_record_suspension_tree_id"), "record_suspension", ["tree_id"], unique=False)
    op.create_index(
        "uq_record_suspension_active",
        "record_suspension",
        ["tree_id", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.add_column("document", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("photo_collection", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tradition_entry", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint(op.f(CHECK), "user_notification", type_="check")
    op.create_check_constraint(
        op.f(CHECK), "user_notification", f"kind IN ({KINDS_BEFORE}, {TAKEDOWN_KINDS})"
    )
    for table in NEW_RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.execute(f"DELETE FROM user_notification WHERE kind IN ({TAKEDOWN_KINDS})")  # noqa: S608 - constants
    op.drop_constraint(op.f(CHECK), "user_notification", type_="check")
    op.create_check_constraint(op.f(CHECK), "user_notification", f"kind IN ({KINDS_BEFORE})")
    for table in NEW_RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
    op.drop_column("tradition_entry", "suspended_at")
    op.drop_column("photo_collection", "suspended_at")
    op.drop_column("document", "suspended_at")
    op.drop_index(
        "uq_record_suspension_active",
        table_name="record_suspension",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index(op.f("ix_record_suspension_tree_id"), table_name="record_suspension")
    op.drop_index("ix_record_suspension_appeal_due", table_name="record_suspension")
    op.drop_table("record_suspension")
    op.drop_index(op.f("ix_record_report_tree_id"), table_name="record_report")
    op.drop_index("ix_record_report_status", table_name="record_report")
    op.drop_index("ix_record_report_resource", table_name="record_report")
    op.drop_table("record_report")
