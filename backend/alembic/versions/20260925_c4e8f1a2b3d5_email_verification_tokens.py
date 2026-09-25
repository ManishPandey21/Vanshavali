"""email verification and password reset tokens

Revision ID: c4e8f1a2b3d5
Revises: b7c1e0d2f3a4
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.rls import GRANT_APP_ROLE_SQL

revision: str = "c4e8f1a2b3d5"
down_revision: str | None = "b7c1e0d2f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"


def upgrade() -> None:
    op.add_column("app_user", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Accounts that existed before verification was introduced keep working (nobody is locked out).
    op.execute("UPDATE app_user SET email_verified_at = created_at WHERE email_verified_at IS NULL")
    op.create_table(
        "auth_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'password_reset')", name=op.f("ck_auth_token_auth_token_purpose")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_auth_token_user_id_app_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_token_token_hash")),
    )
    op.create_index("ix_auth_token_user_purpose", "auth_token", ["user_id", "purpose"], unique=False)
    # auth_token is not tree-scoped (no RLS); the application role still needs DML on it.
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.drop_index("ix_auth_token_user_purpose", table_name="auth_token")
    op.drop_table("auth_token")
    op.drop_column("app_user", "email_verified_at")
