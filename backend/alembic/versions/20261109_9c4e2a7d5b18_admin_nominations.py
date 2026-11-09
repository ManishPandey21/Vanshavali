"""admin nominations

Revision ID: 9c4e2a7d5b18
Revises: 9c4f2a7d1e83
Create Date: 2026-11-09

ADR-0006 amendment of 9 Nov 2026: `admin_nomination`, tree-scoped with row-level security, at most
one open nomination per nominee (partial unique index); seven nomination notification kinds on
`user_notification`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "9c4e2a7d5b18"
down_revision: str | None = "9c4f2a7d1e83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
STATUSES = "'open', 'approved', 'declined_by_owner', 'declined_by_nominee', 'withdrawn', 'expired', 'lapsed'"
NOTIFICATION_KINDS_BEFORE = (
    "'proposal_to_review', 'proposal_accepted', 'proposal_rejected', 'proposal_stale', "
    "'challenge_opened', 'challenge_upheld', 'challenge_dismissed', 'proposal_comment', "
    "'offer_accepted', 'offer_declined'"
)
NOMINATION_KINDS = (
    "'nomination_created', 'nomination_accepted', 'nomination_declined', 'nomination_approved', "
    "'nomination_rejected', 'nomination_expired', 'nomination_lapsed'"
)
NOTIFICATION_CHECK = "ck_user_notification_notificationkind"


def upgrade() -> None:
    op.create_table(
        "admin_nomination",
        sa.Column("nominator_id", sa.UUID(), nullable=True),
        sa.Column("nominee_membership_id", sa.UUID(), nullable=True),
        sa.Column("nominee_user_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=40), server_default="open", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nominee_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(reason) <= 500", name=op.f("ck_admin_nomination_reason_length")),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_admin_nomination_nominationstatus")),
        sa.ForeignKeyConstraint(
            ["tree_id", "nominee_membership_id"],
            ["tree_membership.tree_id", "tree_membership.id"],
            name=op.f("fk_admin_nomination_tree_id_tree_membership"),
            ondelete="SET NULL (nominee_membership_id)",
        ),
        sa.ForeignKeyConstraint(
            ["nominator_id"],
            ["app_user.id"],
            name=op.f("fk_admin_nomination_nominator_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["nominee_user_id"],
            ["app_user.id"],
            name=op.f("fk_admin_nomination_nominee_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["app_user.id"],
            name=op.f("fk_admin_nomination_decided_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_admin_nomination_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_admin_nomination_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_admin_nomination_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_nomination")),
        sa.UniqueConstraint("tree_id", "id", name="uq_admin_nomination_tree_id_id"),
    )
    op.create_index(op.f("ix_admin_nomination_tree_id"), "admin_nomination", ["tree_id"], unique=False)
    op.create_index(
        "ix_admin_nomination_status", "admin_nomination", ["tree_id", "status", "expires_at"], unique=False
    )
    op.create_index(
        "uq_admin_nomination_open_nominee",
        "admin_nomination",
        ["tree_id", "nominee_membership_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.drop_constraint(op.f(NOTIFICATION_CHECK), "user_notification", type_="check")
    op.create_check_constraint(
        op.f(NOTIFICATION_CHECK),
        "user_notification",
        f"kind IN ({NOTIFICATION_KINDS_BEFORE}, {NOMINATION_KINDS})",
    )

    for stmt in enable_sql("admin_nomination"):
        op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.execute(f"DELETE FROM user_notification WHERE kind IN ({NOMINATION_KINDS})")
    op.drop_constraint(op.f(NOTIFICATION_CHECK), "user_notification", type_="check")
    op.create_check_constraint(
        op.f(NOTIFICATION_CHECK), "user_notification", f"kind IN ({NOTIFICATION_KINDS_BEFORE})"
    )

    for stmt in disable_sql("admin_nomination"):
        op.execute(stmt)
    op.drop_index("uq_admin_nomination_open_nominee", table_name="admin_nomination")
    op.drop_index("ix_admin_nomination_status", table_name="admin_nomination")
    op.drop_index(op.f("ix_admin_nomination_tree_id"), table_name="admin_nomination")
    op.drop_table("admin_nomination")
