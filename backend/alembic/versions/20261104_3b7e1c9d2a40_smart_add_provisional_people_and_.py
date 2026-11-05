"""smart add provisional people and relative age order

Revision ID: 3b7e1c9d2a40
Revises: 9a1b2c3d4e5f
Create Date: 2026-11-04

ADR-0020: ``person.is_provisional`` (people added "as unknown for now" by Smart Add) and the
tree-scoped ``relative_age_order`` table (family-confirmed elder/younger), with row-level security.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "3b7e1c9d2a40"
down_revision: str | None = "9a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
# Frozen at this revision (see b7c1e0d2f3a4).
NEW_RLS_TABLES: tuple[str, ...] = ("relative_age_order",)


def upgrade() -> None:
    op.create_table(
        "relative_age_order",
        sa.Column("elder_person_id", sa.UUID(), nullable=False),
        sa.Column("younger_person_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "elder_person_id <> younger_person_id", name=op.f("ck_relative_age_order_distinct")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_relative_age_order_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "elder_person_id"],
            ["person.tree_id", "person.id"],
            name=op.f("fk_relative_age_order_tree_id_elder_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "younger_person_id"],
            ["person.tree_id", "person.id"],
            name=op.f("fk_relative_age_order_tree_id_younger_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_relative_age_order_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_relative_age_order_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_relative_age_order")),
        sa.UniqueConstraint(
            "tree_id", "elder_person_id", "younger_person_id", name="uq_relative_age_order_pair"
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_relative_age_order_tree_id_id"),
    )
    op.create_index(op.f("ix_relative_age_order_tree_id"), "relative_age_order", ["tree_id"], unique=False)
    op.add_column("person", sa.Column("is_provisional", sa.Boolean(), server_default="false", nullable=False))
    for table in NEW_RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in NEW_RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
    op.drop_column("person", "is_provisional")
    op.drop_index(op.f("ix_relative_age_order_tree_id"), table_name="relative_age_order")
    op.drop_table("relative_age_order")
