"""heritage visualization, life events and reminders

Revision ID: 9a1b2c3d4e5f
Revises: f0a1b2c3d4e5
Create Date: 2026-10-02

ADR-0015/0016/0017: geo-tagged places, important life events, event photo albums, reminders and
notification delivery, chart presets and render jobs. New tree-scoped tables get row-level security;
``notification_contact`` is user-level identity data (service-layer protected, like ``app_user``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "9a1b2c3d4e5f"
down_revision: str | None = "f0a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"

# Frozen at this revision (see b7c1e0d2f3a4).
NEW_RLS_TABLES: tuple[str, ...] = (
    "chart_preset",
    "event_media",
    "event_reminder",
    "notification_delivery",
    "notification_preference",
    "render_artifact",
    "render_job",
)

_OLD_PLACE_TYPES = (
    "village",
    "town",
    "city",
    "tehsil",
    "district",
    "state",
    "country",
    "temple",
    "property",
    "other",
)
_NEW_PLACE_TYPES = (
    *_OLD_PLACE_TYPES[:-1],
    "ancestral_house",
    "shrine",
    "land_parcel",
    "neighbourhood",
    "other",
)
_PRECISIONS = ("exact", "approximate", "locality", "district", "state", "country", "unknown")
_CATEGORIES = (
    "birth",
    "naming_ceremony",
    "annaprashan",
    "mundan",
    "upanayana",
    "initiation",
    "education",
    "graduation",
    "engagement",
    "marriage",
    "migration",
    "employment",
    "retirement",
    "award",
    "property_acquisition",
    "illness",
    "recovery",
    "pilgrimage",
    "death",
    "memorial",
    "custom",
)
_LEVELS = (
    "PRIVATE_SELF",
    "PRIVATE_TREE_ADMINS",
    "FAMILY_BRANCH",
    "TREE_MEMBERS",
    "INVITED_RESEARCHER",
    "PUBLIC_DECEASED_ONLY",
    "CUSTOM",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


_ADDED_CHECKS = (
    ("event", "ck_event_lifeeventcategory", _in("category", _CATEGORIES)),
    ("event", "ck_event_eventsignificance", _in("significance", ("standard", "important", "milestone"))),
    ("event", "ck_event_event_location_precision", _in("location_precision", _PRECISIONS)),
    ("place", "ck_place_locationprecision", _in("location_precision", _PRECISIONS)),
    ("place", "ck_place_geo_confidence", _in("geo_confidence", ("high", "medium", "low", "unknown"))),
    ("place", "ck_place_coordinate_privacy", _in("coordinate_privacy", _LEVELS)),
)


def upgrade() -> None:
    op.create_table(
        "notification_contact",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "sms",
                "whatsapp",
                name="notificationchannel",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("address_enc", sa.String(length=400), nullable=False),
        sa.Column("address_hint", sa.String(length=40), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_code_hash", sa.String(length=64), nullable=True),
        sa.Column("verify_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "channel IN ('email', 'sms', 'whatsapp')",
            name=op.f("ck_notification_contact_notificationchannel"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_notification_contact_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_contact")),
        sa.UniqueConstraint("user_id", "channel", name="uq_notification_contact"),
    )
    op.create_index(
        op.f("ix_notification_contact_user_id"), "notification_contact", ["user_id"], unique=False
    )
    op.create_table(
        "chart_preset",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "chart_type",
            sa.Enum(
                "fan",
                "graph",
                "pedigree",
                "family_tree",
                "lifespan",
                "event_timeline",
                "map",
                name="charttype",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("shared", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "chart_type IN ('fan', 'graph', 'pedigree', 'family_tree', 'lifespan', 'event_timeline', 'map')",
            name=op.f("ck_chart_preset_charttype"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_chart_preset_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_chart_preset_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_chart_preset_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_chart_preset_user_id_app_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chart_preset")),
        sa.UniqueConstraint("tree_id", "id", name="uq_chart_preset_tree_id_id"),
    )
    op.create_index(
        "ix_chart_preset_owner", "chart_preset", ["tree_id", "user_id", "chart_type"], unique=False
    )
    op.create_index(op.f("ix_chart_preset_tree_id"), "chart_preset", ["tree_id"], unique=False)
    op.create_index(op.f("ix_chart_preset_user_id"), "chart_preset", ["user_id"], unique=False)
    op.create_table(
        "notification_preference",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("channels", postgresql.ARRAY(sa.String(length=20)), server_default="{}", nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="Asia/Kolkata", nullable=False),
        sa.Column("send_hour", sa.SmallInteger(), server_default="8", nullable=False),
        sa.Column("default_lead_days", postgresql.ARRAY(sa.Integer()), server_default="{0}", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_notification_preference_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_notification_preference_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_notification_preference_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_notification_preference_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preference")),
        sa.UniqueConstraint("tree_id", "id", name="uq_notification_preference_tree_id_id"),
        sa.UniqueConstraint("tree_id", "user_id", name="uq_notification_preference"),
    )
    op.create_index(
        op.f("ix_notification_preference_tree_id"), "notification_preference", ["tree_id"], unique=False
    )
    op.create_index(
        op.f("ix_notification_preference_user_id"), "notification_preference", ["user_id"], unique=False
    )
    op.create_table(
        "render_job",
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column(
            "chart_type",
            sa.Enum(
                "fan",
                "graph",
                "pedigree",
                "family_tree",
                "lifespan",
                "event_timeline",
                "map",
                name="charttype",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "output",
            sa.Enum(
                "poster", "mp4", name="renderoutput", native_enum=False, create_constraint=False, length=40
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                name="renderstatus",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("progress", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("payload_storage_key", sa.String(length=500), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("renderer", sa.String(length=80), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=300), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "chart_type IN ('fan', 'graph', 'pedigree', 'family_tree', 'lifespan', 'event_timeline', 'map')",
            name=op.f("ck_render_job_charttype"),
        ),
        sa.CheckConstraint("output IN ('poster', 'mp4')", name=op.f("ck_render_job_renderoutput")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_render_job_renderstatus"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_render_job_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["app_user.id"],
            name=op.f("fk_render_job_requested_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_render_job_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_render_job_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_render_job")),
        sa.UniqueConstraint("tree_id", "id", name="uq_render_job_tree_id_id"),
    )
    op.create_index(op.f("ix_render_job_requested_by"), "render_job", ["requested_by"], unique=False)
    op.create_index(
        "ix_render_job_requester", "render_job", ["tree_id", "requested_by", "created_at"], unique=False
    )
    op.create_index(op.f("ix_render_job_tree_id"), "render_job", ["tree_id"], unique=False)
    op.create_table(
        "render_artifact",
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "poster_png",
                "video_mp4",
                name="renderartifactkind",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('poster_png', 'video_mp4')", name=op.f("ck_render_artifact_renderartifactkind")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_render_artifact_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "job_id"],
            ["render_job.tree_id", "render_job.id"],
            name=op.f("fk_render_artifact_tree_id_job_id_render_job"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_render_artifact_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_render_artifact_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_render_artifact")),
        sa.UniqueConstraint("tree_id", "id", name="uq_render_artifact_tree_id_id"),
    )
    op.create_index(op.f("ix_render_artifact_job_id"), "render_artifact", ["job_id"], unique=False)
    op.create_index(op.f("ix_render_artifact_tree_id"), "render_artifact", ["tree_id"], unique=False)
    op.create_table(
        "event_media",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("caption", sa.String(length=500), nullable=True),
        sa.Column("taken_date", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_cover", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_event_media_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "document_id"],
            ["document.tree_id", "document.id"],
            name=op.f("fk_event_media_tree_id_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "event_id"],
            ["event.tree_id", "event.id"],
            name=op.f("fk_event_media_tree_id_event_id_event"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_event_media_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_event_media_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_media")),
        sa.UniqueConstraint("event_id", "document_id", name="uq_event_media"),
        sa.UniqueConstraint("tree_id", "id", name="uq_event_media_tree_id_id"),
    )
    op.create_index(
        "ix_event_media_event", "event_media", ["tree_id", "event_id", "sort_order"], unique=False
    )
    op.create_index(op.f("ix_event_media_tree_id"), "event_media", ["tree_id"], unique=False)
    op.create_index(
        "uq_event_media_cover", "event_media", ["event_id"], unique=True, postgresql_where=sa.text("is_cover")
    )
    op.create_table(
        "event_reminder",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "birthday",
                "anniversary",
                "memorial",
                "one_time",
                "custom",
                name="reminderkind",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "recurrence",
            sa.Enum(
                "none",
                "annual",
                name="reminderrecurrence",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("lead_days", postgresql.ARRAY(sa.Integer()), server_default="{0}", nullable=False),
        sa.Column("channels", postgresql.ARRAY(sa.String(length=20)), server_default="{}", nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('birthday', 'anniversary', 'memorial', 'one_time', 'custom')",
            name=op.f("ck_event_reminder_reminderkind"),
        ),
        sa.CheckConstraint(
            "recurrence IN ('none', 'annual')", name=op.f("ck_event_reminder_reminderrecurrence")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_event_reminder_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "event_id"],
            ["event.tree_id", "event.id"],
            name=op.f("fk_event_reminder_tree_id_event_id_event"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_event_reminder_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_event_reminder_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app_user.id"], name=op.f("fk_event_reminder_user_id_app_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_reminder")),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_reminder"),
        sa.UniqueConstraint("tree_id", "id", name="uq_event_reminder_tree_id_id"),
    )
    op.create_index(
        "ix_event_reminder_due", "event_reminder", ["tree_id", "active", "next_fire_at"], unique=False
    )
    op.create_index(op.f("ix_event_reminder_tree_id"), "event_reminder", ["tree_id"], unique=False)
    op.create_index(op.f("ix_event_reminder_user_id"), "event_reminder", ["user_id"], unique=False)
    op.create_table(
        "notification_delivery",
        sa.Column("reminder_id", sa.UUID(), nullable=True),
        sa.Column("event_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum(
                "email",
                "sms",
                "whatsapp",
                name="notificationchannel",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("lead_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                "retrying",
                "cancelled",
                name="deliverystatus",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.String(length=80), nullable=True),
        sa.Column("is_test", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "channel IN ('email', 'sms', 'whatsapp')",
            name=op.f("ck_notification_delivery_notificationchannel"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'retrying', 'cancelled')",
            name=op.f("ck_notification_delivery_deliverystatus"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_notification_delivery_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "event_id"],
            ["event.tree_id", "event.id"],
            name=op.f("fk_notification_delivery_tree_id_event_id_event"),
            ondelete="SET NULL (event_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "reminder_id"],
            ["event_reminder.tree_id", "event_reminder.id"],
            name=op.f("fk_notification_delivery_tree_id_reminder_id_event_reminder"),
            ondelete="SET NULL (reminder_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_notification_delivery_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_notification_delivery_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_notification_delivery_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_delivery")),
        sa.UniqueConstraint(
            "reminder_id", "channel", "occurrence_date", "lead_days", name="uq_notification_delivery_once"
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_notification_delivery_tree_id_id"),
    )
    op.create_index(
        "ix_notification_delivery_retry",
        "notification_delivery",
        ["tree_id", "status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_delivery_tree_id"), "notification_delivery", ["tree_id"], unique=False
    )
    op.create_index(
        "ix_notification_delivery_user",
        "notification_delivery",
        ["tree_id", "user_id", "scheduled_for"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_delivery_user_id"), "notification_delivery", ["user_id"], unique=False
    )
    op.add_column("event", sa.Column("title", sa.String(length=300), nullable=True))
    op.add_column(
        "event",
        sa.Column(
            "category",
            sa.Enum(
                "birth",
                "naming_ceremony",
                "annaprashan",
                "mundan",
                "upanayana",
                "initiation",
                "education",
                "graduation",
                "engagement",
                "marriage",
                "migration",
                "employment",
                "retirement",
                "award",
                "property_acquisition",
                "illness",
                "recovery",
                "pilgrimage",
                "death",
                "memorial",
                "custom",
                name="lifeeventcategory",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "event",
        sa.Column(
            "significance",
            sa.Enum(
                "standard",
                "important",
                "milestone",
                name="eventsignificance",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="standard",
            nullable=False,
        ),
    )
    op.add_column(
        "event",
        sa.Column(
            "location_precision",
            sa.Enum(
                "exact",
                "approximate",
                "locality",
                "district",
                "state",
                "country",
                "unknown",
                name="event_location_precision",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=True,
        ),
    )
    op.add_column("place", sa.Column("locality", sa.String(length=200), nullable=True))
    op.add_column("place", sa.Column("district", sa.String(length=120), nullable=True))
    op.add_column("place", sa.Column("state", sa.String(length=120), nullable=True))
    op.add_column("place", sa.Column("country", sa.String(length=120), nullable=True))
    op.add_column("place", sa.Column("map_label", sa.String(length=200), nullable=True))
    op.add_column(
        "place",
        sa.Column(
            "location_precision",
            sa.Enum(
                "exact",
                "approximate",
                "locality",
                "district",
                "state",
                "country",
                "unknown",
                name="locationprecision",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "place",
        sa.Column(
            "geo_confidence",
            sa.Enum(
                "high",
                "medium",
                "low",
                "unknown",
                name="geo_confidence",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column("place", sa.Column("geo_note", sa.Text(), nullable=True))
    op.add_column(
        "place",
        sa.Column(
            "coordinate_privacy",
            sa.Enum(
                "PRIVATE_SELF",
                "PRIVATE_TREE_ADMINS",
                "FAMILY_BRANCH",
                "TREE_MEMBERS",
                "INVITED_RESEARCHER",
                "PUBLIC_DECEASED_ONLY",
                "CUSTOM",
                name="coordinate_privacy",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=True,
        ),
    )
    for table, name, expr in _ADDED_CHECKS:
        op.create_check_constraint(op.f(name), table, expr)
    op.drop_constraint(op.f("ck_place_placetype"), "place", type_="check")
    op.create_check_constraint(op.f("ck_place_placetype"), "place", _in("place_type", _NEW_PLACE_TYPES))
    for table in NEW_RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in NEW_RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
    # constants only (no user input)
    op.execute(f"UPDATE place SET place_type = 'other' WHERE NOT ({_in('place_type', _OLD_PLACE_TYPES)})")  # noqa: S608
    op.drop_constraint(op.f("ck_place_placetype"), "place", type_="check")
    op.create_check_constraint(op.f("ck_place_placetype"), "place", _in("place_type", _OLD_PLACE_TYPES))
    for table, name, _expr in _ADDED_CHECKS:
        op.drop_constraint(op.f(name), table, type_="check")
    op.drop_column("place", "coordinate_privacy")
    op.drop_column("place", "geo_note")
    op.drop_column("place", "geo_confidence")
    op.drop_column("place", "location_precision")
    op.drop_column("place", "map_label")
    op.drop_column("place", "country")
    op.drop_column("place", "state")
    op.drop_column("place", "district")
    op.drop_column("place", "locality")
    op.drop_column("event", "location_precision")
    op.drop_column("event", "significance")
    op.drop_column("event", "category")
    op.drop_column("event", "title")
    op.drop_index(op.f("ix_notification_delivery_user_id"), table_name="notification_delivery")
    op.drop_index("ix_notification_delivery_user", table_name="notification_delivery")
    op.drop_index(op.f("ix_notification_delivery_tree_id"), table_name="notification_delivery")
    op.drop_index("ix_notification_delivery_retry", table_name="notification_delivery")
    op.drop_table("notification_delivery")
    op.drop_index(op.f("ix_event_reminder_user_id"), table_name="event_reminder")
    op.drop_index(op.f("ix_event_reminder_tree_id"), table_name="event_reminder")
    op.drop_index("ix_event_reminder_due", table_name="event_reminder")
    op.drop_table("event_reminder")
    op.drop_index("uq_event_media_cover", table_name="event_media", postgresql_where=sa.text("is_cover"))
    op.drop_index(op.f("ix_event_media_tree_id"), table_name="event_media")
    op.drop_index("ix_event_media_event", table_name="event_media")
    op.drop_table("event_media")
    op.drop_index(op.f("ix_render_artifact_tree_id"), table_name="render_artifact")
    op.drop_index(op.f("ix_render_artifact_job_id"), table_name="render_artifact")
    op.drop_table("render_artifact")
    op.drop_index(op.f("ix_render_job_tree_id"), table_name="render_job")
    op.drop_index("ix_render_job_requester", table_name="render_job")
    op.drop_index(op.f("ix_render_job_requested_by"), table_name="render_job")
    op.drop_table("render_job")
    op.drop_index(op.f("ix_notification_preference_user_id"), table_name="notification_preference")
    op.drop_index(op.f("ix_notification_preference_tree_id"), table_name="notification_preference")
    op.drop_table("notification_preference")
    op.drop_index(op.f("ix_chart_preset_user_id"), table_name="chart_preset")
    op.drop_index(op.f("ix_chart_preset_tree_id"), table_name="chart_preset")
    op.drop_index("ix_chart_preset_owner", table_name="chart_preset")
    op.drop_table("chart_preset")
    op.drop_index(op.f("ix_notification_contact_user_id"), table_name="notification_contact")
    op.drop_table("notification_contact")
