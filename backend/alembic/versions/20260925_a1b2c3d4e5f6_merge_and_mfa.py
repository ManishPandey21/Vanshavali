"""person merge records and TOTP MFA

Revision ID: a1b2c3d4e5f6
Revises: 7fefb8493516
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "7fefb8493516"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("app_user", sa.Column("mfa_secret_enc", sa.String(length=400), nullable=True))
    op.add_column("app_user", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("person", sa.Column("merged_into_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_person_tree_id_merged_into_id_person"),
        "person",
        "person",
        ["tree_id", "merged_into_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (merged_into_id)",
    )
    op.create_table(
        "merge_record",
        sa.Column("survivor_id", sa.UUID(), nullable=False),
        sa.Column("merged_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_merge_record_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "merged_id"],
            ["person.tree_id", "person.id"],
            name=op.f("fk_merge_record_tree_id_merged_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "survivor_id"],
            ["person.tree_id", "person.id"],
            name=op.f("fk_merge_record_tree_id_survivor_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_merge_record_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_merge_record_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merge_record")),
        sa.UniqueConstraint("tree_id", "id", name="uq_merge_record_tree_id_id"),
    )
    op.create_index(op.f("ix_merge_record_tree_id"), "merge_record", ["tree_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_merge_record_tree_id"), table_name="merge_record")
    op.drop_table("merge_record")
    op.drop_constraint(op.f("fk_person_tree_id_merged_into_id_person"), "person", type_="foreignkey")
    op.drop_column("person", "merged_into_id")
    op.drop_column("app_user", "mfa_enabled_at")
    op.drop_column("app_user", "mfa_secret_enc")
