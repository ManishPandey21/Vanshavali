"""forced password change flag and external (OpenID Connect) identities

Revision ID: d5f2a9c1e7b3
Revises: edcd174a0123
Create Date: 2026-09-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.rls import GRANT_APP_ROLE_SQL

revision: str = "d5f2a9c1e7b3"
down_revision: str | None = "edcd174a0123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("must_change_password", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_table(
        "external_identity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email_at_link", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_external_identity_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_identity")),
        sa.UniqueConstraint("provider", "subject", name=op.f("uq_external_identity_provider_subject")),
    )
    op.create_index(op.f("ix_external_identity_user_id"), "external_identity", ["user_id"], unique=False)
    # external_identity is not tree-scoped (no RLS); the application role still needs DML on it.
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.drop_index(op.f("ix_external_identity_user_id"), table_name="external_identity")
    op.drop_table("external_identity")
    op.drop_column("app_user", "must_change_password")
