"""master data vocabularies

Revision ID: 5c2d8e1f7a90
Revises: 3b7e1c9d2a40
Create Date: 2026-11-04

ADR-0018: global ``vocabulary`` / ``vocabulary_term`` (reference data loaded from packs by
``python -m app.cli.masterdata load``) and the tree-scoped ``tree_vocabulary_term`` (a family's
own entries) with row-level security.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "5c2d8e1f7a90"
down_revision: str | None = "3b7e1c9d2a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
# Frozen at this revision (see b7c1e0d2f3a4).
NEW_RLS_TABLES: tuple[str, ...] = ("tree_vocabulary_term",)


def upgrade() -> None:
    op.create_table(
        "vocabulary",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("licence", sa.String(length=120), nullable=True),
        sa.Column("allows_custom", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_vocabulary")),
    )
    op.create_table(
        "vocabulary_term",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vocabulary_key", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String(length=200)), server_default="{}", nullable=False),
        sa.Column("scope", postgresql.ARRAY(sa.String(length=80)), server_default="{}", nullable=False),
        sa.Column("parent_code", sa.String(length=80), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "reviewed",
                "retired",
                name="vocabularytermstatus",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'reviewed', 'retired')", name=op.f("ck_vocabulary_term_vocabularytermstatus")
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_key"],
            ["vocabulary.key"],
            name=op.f("fk_vocabulary_term_vocabulary_key_vocabulary"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vocabulary_term")),
        sa.UniqueConstraint("vocabulary_key", "code", name="uq_vocabulary_term_code"),
    )
    op.create_index(
        op.f("ix_vocabulary_term_vocabulary_key"), "vocabulary_term", ["vocabulary_key"], unique=False
    )
    op.create_table(
        "tree_vocabulary_term",
        sa.Column("vocabulary_key", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=90), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String(length=200)), server_default="{}", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_tree_vocabulary_term_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_tree_vocabulary_term_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_tree_vocabulary_term_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_key"],
            ["vocabulary.key"],
            name=op.f("fk_tree_vocabulary_term_vocabulary_key_vocabulary"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tree_vocabulary_term")),
        sa.UniqueConstraint("tree_id", "id", name="uq_tree_vocabulary_term_tree_id_id"),
        sa.UniqueConstraint("tree_id", "vocabulary_key", "code", name="uq_tree_vocabulary_term_code"),
    )
    op.create_index(
        op.f("ix_tree_vocabulary_term_tree_id"), "tree_vocabulary_term", ["tree_id"], unique=False
    )
    for table in NEW_RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in NEW_RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
    op.drop_index(op.f("ix_tree_vocabulary_term_tree_id"), table_name="tree_vocabulary_term")
    op.drop_table("tree_vocabulary_term")
    op.drop_index(op.f("ix_vocabulary_term_vocabulary_key"), table_name="vocabulary_term")
    op.drop_table("vocabulary_term")
    op.drop_table("vocabulary")
