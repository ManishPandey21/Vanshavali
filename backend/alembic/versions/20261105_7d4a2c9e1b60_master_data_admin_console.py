"""master data admin console

Revision ID: 7d4a2c9e1b60
Revises: 5c2d8e1f7a90
Create Date: 2026-11-05

ADR-0026: change requests and history for global vocabulary terms (``vocabulary_change``), plus
revision counters (optimistic concurrency and cache refresh), pack/console ownership, successor
codes and authorship on ``vocabulary_term``, and console grouping / closed-set flags on
``vocabulary``. All global reference data: no row-level security, nothing about any family.

Downgrade drops the change history and the console columns. Terms edited in the console keep their
current labels but become pack-managed again, so the next pack load may overwrite them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL

revision: str = "7d4a2c9e1b60"
down_revision: str | None = "5c2d8e1f7a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=40)


def upgrade() -> None:
    op.create_table(
        "vocabulary_change",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("vocabulary_key", sa.String(length=40), nullable=False),
        sa.Column("term_code", sa.String(length=80), nullable=False),
        sa.Column(
            "action", _enum("vocabularychangeaction", "create", "update", "retire", "reactivate"), nullable=False
        ),
        sa.Column(
            "status",
            _enum("vocabularychangestatus", "pending", "published", "rejected", "withdrawn"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("base_revision", sa.Integer(), nullable=True),
        sa.Column("previous", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("proposed", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("proposed_by", sa.UUID(), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "action IN ('create', 'update', 'retire', 'reactivate')",
            name=op.f("ck_vocabulary_change_vocabularychangeaction"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'rejected', 'withdrawn')",
            name=op.f("ck_vocabulary_change_vocabularychangestatus"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["app_user.id"],
            name=op.f("fk_vocabulary_change_decided_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_by"],
            ["app_user.id"],
            name=op.f("fk_vocabulary_change_proposed_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_key"],
            ["vocabulary.key"],
            name=op.f("fk_vocabulary_change_vocabulary_key_vocabulary"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vocabulary_change")),
    )
    op.create_index("ix_vocabulary_change_term", "vocabulary_change", ["vocabulary_key", "term_code"])
    op.create_index("ix_vocabulary_change_vocabulary_status", "vocabulary_change", ["vocabulary_key", "status"])
    op.create_index(
        "uq_vocabulary_change_one_pending",
        "vocabulary_change",
        ["vocabulary_key", "term_code"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.add_column("vocabulary", sa.Column("category", sa.String(length=40), server_default="other", nullable=False))
    op.add_column(
        "vocabulary", sa.Column("fixed_membership", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("vocabulary", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))

    op.add_column("vocabulary_term", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "vocabulary_term",
        sa.Column("managed_by", _enum("vocabularytermmanagedby", "pack", "admin"), server_default="pack", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_vocabulary_term_vocabularytermmanagedby"), "vocabulary_term", "managed_by IN ('pack', 'admin')"
    )
    op.add_column("vocabulary_term", sa.Column("successor_code", sa.String(length=80), nullable=True))
    op.add_column("vocabulary_term", sa.Column("created_by", sa.UUID(), nullable=True))
    op.add_column("vocabulary_term", sa.Column("updated_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_vocabulary_term_created_by_app_user"),
        "vocabulary_term",
        "app_user",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_vocabulary_term_updated_by_app_user"),
        "vocabulary_term",
        "app_user",
        ["updated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.drop_constraint(op.f("fk_vocabulary_term_updated_by_app_user"), "vocabulary_term", type_="foreignkey")
    op.drop_constraint(op.f("fk_vocabulary_term_created_by_app_user"), "vocabulary_term", type_="foreignkey")
    op.drop_column("vocabulary_term", "updated_by")
    op.drop_column("vocabulary_term", "created_by")
    op.drop_column("vocabulary_term", "successor_code")
    op.drop_constraint(op.f("ck_vocabulary_term_vocabularytermmanagedby"), "vocabulary_term", type_="check")
    op.drop_column("vocabulary_term", "managed_by")
    op.drop_column("vocabulary_term", "revision")
    op.drop_column("vocabulary", "revision")
    op.drop_column("vocabulary", "fixed_membership")
    op.drop_column("vocabulary", "category")
    op.drop_index("uq_vocabulary_change_one_pending", table_name="vocabulary_change")
    op.drop_index("ix_vocabulary_change_vocabulary_status", table_name="vocabulary_change")
    op.drop_index("ix_vocabulary_change_term", table_name="vocabulary_change")
    op.drop_table("vocabulary_change")
