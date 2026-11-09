"""family calendar: lunar reminders, calendar settings, feeds, cached calendar days

Revision ID: 7b2e4d9a1c63
Revises: 9c4e2a7d5b18
Create Date: 2026-11-08

ADR-0022: `event_reminder` gains `date_rule` (solar | lunar), `convention` and an observance city;
`tree` gains the family's calendar convention and observance city;
`calendar_feed` (a member's ICS feed, resolved by a hashed token, protected by the service layer
like invitations); `panchang_day` (global computed days, read-only to the application role).
The lunar part of a date lives in the existing date JSON and needs no column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL

revision: str = "7b2e4d9a1c63"
down_revision: str | None = "9c4e2a7d5b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"


def upgrade() -> None:
    op.create_table(
        "panchang_day",
        sa.Column("place_key", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("sunrise", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sunset", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tithi_at_sunrise", sa.SmallInteger(), nullable=False),
        sa.Column("tithis", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("amanta_masa", sa.SmallInteger(), nullable=False),
        sa.Column("is_adhik", sa.Boolean(), nullable=False),
        sa.Column("engine_version", sa.String(length=60), nullable=False),
        sa.PrimaryKeyConstraint("place_key", "day", name=op.f("pk_panchang_day")),
    )
    op.create_table(
        "calendar_feed",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("include_names", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_calendar_feed_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_calendar_feed_user_id_app_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_feed")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_calendar_feed_token_hash")),
    )
    op.create_index(op.f("ix_calendar_feed_tree_id"), "calendar_feed", ["tree_id"], unique=False)
    op.create_index(op.f("ix_calendar_feed_user_id"), "calendar_feed", ["user_id"], unique=False)
    op.create_index(
        "uq_calendar_feed_active",
        "calendar_feed",
        ["tree_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.add_column(
        "event_reminder",
        sa.Column(
            "date_rule",
            sa.Enum(
                "solar",
                "lunar",
                name="reminderdaterule",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="solar",
            nullable=False,
        ),
    )
    op.add_column("event_reminder", sa.Column("convention", sa.String(length=40), nullable=True))
    op.add_column("event_reminder", sa.Column("observance_city", sa.String(length=60), nullable=True))
    op.add_column("tree", sa.Column("calendar_convention", sa.String(length=40), nullable=True))
    op.add_column("tree", sa.Column("observance_city", sa.String(length=60), nullable=True))
    op.create_check_constraint(
        op.f("ck_event_reminder_reminderdaterule"), "event_reminder", "date_rule IN ('solar', 'lunar')"
    )
    # panchang_day is reference data: the application role may only read it
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.drop_column("tree", "observance_city")
    op.drop_column("tree", "calendar_convention")
    op.drop_constraint(op.f("ck_event_reminder_reminderdaterule"), "event_reminder", type_="check")
    op.drop_column("event_reminder", "observance_city")
    op.drop_column("event_reminder", "convention")
    op.drop_column("event_reminder", "date_rule")
    op.drop_index(
        "uq_calendar_feed_active", table_name="calendar_feed", postgresql_where=sa.text("revoked_at IS NULL")
    )
    op.drop_index(op.f("ix_calendar_feed_user_id"), table_name="calendar_feed")
    op.drop_index(op.f("ix_calendar_feed_tree_id"), table_name="calendar_feed")
    op.drop_table("calendar_feed")
    op.drop_table("panchang_day")
