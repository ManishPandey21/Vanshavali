"""platform capability grants and session-level MFA

Revision ID: e7c2a9f4b310
Revises: d9b4f2c6a713
Create Date: 2026-11-11

ADR-0028 §7, increment 1. ``platform_capability_grant`` records which named person holds a platform
capability (only ``master_data.admin`` today). The operator CLI writes it as the schema owner; the
application role may only read it (it joins ``READ_ONLY_TABLES``), so nothing reachable from the API
can grant a capability. ``user_session`` gains ``mfa_verified_at`` (the session was opened with
password + TOTP) and ``mfa_step_up_at`` (the last TOTP step-up). Existing sessions get NULL and so do
not qualify for any platform capability until their holder signs in again.

The downgrade drops the table and both columns; nothing else depends on them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL

revision: str = "e7c2a9f4b310"
down_revision: str | None = "d9b4f2c6a713"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"


def upgrade() -> None:
    op.add_column("user_session", sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_session", sa.Column("mfa_step_up_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "platform_capability_grant",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "capability",
            sa.Enum("master_data.admin", name="platformcapability", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column("holder_name", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("granted_by", sa.String(length=200), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=200), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "capability IN ('master_data.admin')",
            name=op.f("ck_platform_capability_grant_platformcapability"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_platform_capability_grant_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_capability_grant")),
    )
    op.create_index(
        op.f("ix_platform_capability_grant_user_id"), "platform_capability_grant", ["user_id"], unique=False
    )
    op.create_index(
        "uq_platform_capability_grant_active",
        "platform_capability_grant",
        ["user_id", "capability"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    # grants SELECT on the new table and revokes writes (it is in READ_ONLY_TABLES)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.drop_index("uq_platform_capability_grant_active", table_name="platform_capability_grant")
    op.drop_index(op.f("ix_platform_capability_grant_user_id"), table_name="platform_capability_grant")
    op.drop_table("platform_capability_grant")
    op.drop_column("user_session", "mfa_step_up_at")
    op.drop_column("user_session", "mfa_verified_at")
