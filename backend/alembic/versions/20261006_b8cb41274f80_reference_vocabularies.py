"""reference vocabularies

Revision ID: b8cb41274f80
Revises: 9a1b2c3d4e5f
Create Date: 2026-10-06

ADR-0019: global typing-aid vocabularies (gotra, rashi, state, district, kin term, ...). Not
tree-scoped, so no row-level security; the data is loaded by ``python -m app.cli.load_vocabularies``,
not by this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8cb41274f80"
down_revision: str | None = "9a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vocabulary",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_vocabulary_code", sa.String(length=40), nullable=True),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("license", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_vocabulary_code"],
            ["vocabulary.code"],
            name=op.f("fk_vocabulary_parent_vocabulary_code_vocabulary"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_vocabulary")),
    )
    op.create_table(
        "vocabulary_term",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vocabulary_code", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=80)), server_default="{}", nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["vocabulary_term.id"],
            name=op.f("fk_vocabulary_term_parent_id_vocabulary_term"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_code"],
            ["vocabulary.code"],
            name=op.f("fk_vocabulary_term_vocabulary_code_vocabulary"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vocabulary_term")),
        sa.UniqueConstraint("vocabulary_code", "code", name="uq_vocabulary_term_code"),
    )
    op.create_index(
        "ix_vocabulary_term_parent", "vocabulary_term", ["vocabulary_code", "parent_id"], unique=False
    )
    op.create_index(
        "ix_vocabulary_term_search_trgm",
        "vocabulary_term",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vocabulary_term_search_trgm",
        table_name="vocabulary_term",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_index("ix_vocabulary_term_parent", table_name="vocabulary_term")
    op.drop_table("vocabulary_term")
    op.drop_table("vocabulary")
