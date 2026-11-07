"""geography reference

Revision ID: 9e3b5d7f2a14
Revises: 7d4a2c9e1b60

ADR-0019 increment 1: global LGD / India Post snapshots (``geo_snapshot``, ``geo_unit``,
``geo_pin_office``, ``geo_pin_unit``) with a trigger that enforces the administrative hierarchy,
and ``place.lgd_level`` next to the existing ``place.lgd_code``. Global reference data: no RLS.
Downgrade drops every imported snapshot (re-stage from the source files) and ``place.lgd_level``
(``place.lgd_code`` is kept).
Create Date: 2026-11-06 07:46:51.069211
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL

revision: str = "9e3b5d7f2a14"
down_revision: str | None = "7d4a2c9e1b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"

# Frozen copy of app.models.geo.GEO_UNIT_PARENT_SQL at this revision.
PARENT_CHECK_SQL = """
CREATE OR REPLACE FUNCTION geo_unit_parent_check() RETURNS trigger AS $$
DECLARE
  allowed text[] := CASE NEW.level
    WHEN 'country' THEN ARRAY[]::text[]
    WHEN 'state' THEN ARRAY['country']
    WHEN 'district' THEN ARRAY['state']
    WHEN 'subdistrict' THEN ARRAY['district']
    WHEN 'block' THEN ARRAY['district']
    WHEN 'gram_panchayat' THEN ARRAY['block', 'subdistrict']
    WHEN 'village' THEN ARRAY['subdistrict']
    WHEN 'town' THEN ARRAY['subdistrict', 'district']
    WHEN 'ulb' THEN ARRAY['district']
  END;
  p_level text;
  p_snapshot uuid;
BEGIN
  IF NEW.parent_id IS NULL THEN
    IF NEW.level <> 'country' THEN
      RAISE EXCEPTION 'geo_unit % % needs a parent', NEW.level, NEW.code USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
  END IF;
  SELECT level, snapshot_id INTO p_level, p_snapshot FROM geo_unit WHERE id = NEW.parent_id;
  IF p_snapshot IS DISTINCT FROM NEW.snapshot_id THEN
    RAISE EXCEPTION 'geo_unit % % has a parent from another snapshot', NEW.level, NEW.code USING ERRCODE = '23514';
  END IF;
  IF allowed IS NULL OR NOT (p_level = ANY (allowed)) THEN
    RAISE EXCEPTION 'geo_unit % % cannot sit under a %', NEW.level, NEW.code, p_level USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""
PARENT_CHECK_TRIGGER = (
    "CREATE TRIGGER geo_unit_parent_check BEFORE INSERT OR UPDATE OF parent_id, level, snapshot_id "
    "ON geo_unit FOR EACH ROW EXECUTE FUNCTION geo_unit_parent_check()"
)
LEVELS = (
    "('country', 'state', 'district', 'subdistrict', 'block', 'gram_panchayat', 'village', 'town', 'ulb')"
)


def upgrade() -> None:
    op.create_table(
        "geo_snapshot",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "lgd", "india_post", name="geosource", native_enum=False, create_constraint=False, length=40
            ),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "staged",
                "validated",
                "failed",
                "approved",
                "active",
                "superseded",
                name="geosnapshotstatus",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="staged",
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("downloaded_on", sa.Date(), nullable=True),
        sa.Column("licence", sa.String(length=200), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column("files", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("staged_by", sa.String(length=200), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.UUID(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source IN ('lgd', 'india_post')", name=op.f("ck_geo_snapshot_geosource")),
        sa.CheckConstraint(
            "status IN ('staged', 'validated', 'failed', 'approved', 'active', 'superseded')",
            name=op.f("ck_geo_snapshot_geosnapshotstatus"),
        ),
        sa.ForeignKeyConstraint(
            ["activated_by"],
            ["app_user.id"],
            name=op.f("fk_geo_snapshot_activated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["app_user.id"],
            name=op.f("fk_geo_snapshot_approved_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_snapshot")),
        sa.UniqueConstraint("source", "label", name="uq_geo_snapshot_label"),
    )
    op.create_index(
        "uq_geo_snapshot_one_active",
        "geo_snapshot",
        ["source"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "geo_pin_office",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column("pin", sa.String(length=6), nullable=False),
        sa.Column("office_name", sa.String(length=200), nullable=False),
        sa.Column("office_type", sa.String(length=10), nullable=True),
        sa.Column("delivery", sa.Boolean(), nullable=True),
        sa.Column("district_name", sa.String(length=200), nullable=True),
        sa.Column("state_name", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["geo_snapshot.id"],
            name=op.f("fk_geo_pin_office_snapshot_id_geo_snapshot"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_pin_office")),
        sa.UniqueConstraint("snapshot_id", "pin", "office_name", name="uq_geo_pin_office"),
    )
    op.create_index("ix_geo_pin_office_pin", "geo_pin_office", ["snapshot_id", "pin"], unique=False)
    op.create_table(
        "geo_unit",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("snapshot_id", sa.UUID(), nullable=False),
        sa.Column(
            "level",
            sa.Enum(
                "country",
                "state",
                "district",
                "subdistrict",
                "block",
                "gram_panchayat",
                "village",
                "town",
                "ulb",
                name="geolevel",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("name_local", sa.String(length=200), nullable=True),
        sa.Column("local_script", sa.String(length=8), nullable=True),
        sa.Column("local_term", sa.String(length=60), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("alt_names", postgresql.ARRAY(sa.String(length=200)), server_default="{}", nullable=False),
        sa.Column(
            "former_names", postgresql.ARRAY(sa.String(length=200)), server_default="{}", nullable=False
        ),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "successor_codes", postgresql.ARRAY(sa.String(length=40)), server_default="{}", nullable=False
        ),
        sa.Column(
            "origin",
            sa.Enum(
                "official",
                "curated",
                name="geounitorigin",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="official",
            nullable=False,
        ),
        sa.Column("search_key", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "level IN ('country', 'state', 'district', 'subdistrict', 'block', 'gram_panchayat', 'village', 'town', 'ulb')",
            name=op.f("ck_geo_unit_geolevel"),
        ),
        sa.CheckConstraint("origin IN ('official', 'curated')", name=op.f("ck_geo_unit_geounitorigin")),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["geo_unit.id"], name=op.f("fk_geo_unit_parent_id_geo_unit"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["geo_snapshot.id"],
            name=op.f("fk_geo_unit_snapshot_id_geo_snapshot"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_unit")),
        sa.UniqueConstraint("snapshot_id", "level", "code", name="uq_geo_unit_code"),
    )
    op.create_index("ix_geo_unit_children", "geo_unit", ["snapshot_id", "parent_id"], unique=False)
    op.create_index("ix_geo_unit_code", "geo_unit", ["level", "code"], unique=False)
    op.create_index("ix_geo_unit_level", "geo_unit", ["snapshot_id", "level"], unique=False)
    op.create_index(
        "ix_geo_unit_search_trgm",
        "geo_unit",
        ["search_key"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_key": "gin_trgm_ops"},
    )
    op.create_table(
        "geo_pin_unit",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("office_id", sa.UUID(), nullable=False),
        sa.Column(
            "unit_level",
            sa.Enum(
                "country",
                "state",
                "district",
                "subdistrict",
                "block",
                "gram_panchayat",
                "village",
                "town",
                "ulb",
                name="geo_pin_unit_level",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("unit_code", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "unit_level IN ('country', 'state', 'district', 'subdistrict', 'block', 'gram_panchayat', 'village', 'town', 'ulb')",
            name=op.f("ck_geo_pin_unit_geo_pin_unit_level"),
        ),
        sa.ForeignKeyConstraint(
            ["office_id"],
            ["geo_pin_office.id"],
            name=op.f("fk_geo_pin_unit_office_id_geo_pin_office"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_pin_unit")),
        sa.UniqueConstraint("office_id", "unit_level", "unit_code", name="uq_geo_pin_unit"),
    )
    op.create_index("ix_geo_pin_unit_unit", "geo_pin_unit", ["unit_level", "unit_code"], unique=False)
    op.add_column(
        "place",
        sa.Column(
            "lgd_level",
            sa.Enum(
                "country",
                "state",
                "district",
                "subdistrict",
                "block",
                "gram_panchayat",
                "village",
                "town",
                "ulb",
                name="place_lgd_level",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=True,
        ),
    )
    op.create_check_constraint(op.f("ck_place_place_lgd_level"), "place", f"lgd_level IN {LEVELS}")
    op.execute(PARENT_CHECK_SQL)
    op.execute(PARENT_CHECK_TRIGGER)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.drop_constraint(op.f("ck_place_place_lgd_level"), "place", type_="check")
    op.drop_column("place", "lgd_level")
    op.drop_index("ix_geo_pin_unit_unit", table_name="geo_pin_unit")
    op.drop_table("geo_pin_unit")
    op.drop_index(
        "ix_geo_unit_search_trgm",
        table_name="geo_unit",
        postgresql_using="gin",
        postgresql_ops={"search_key": "gin_trgm_ops"},
    )
    op.drop_index("ix_geo_unit_level", table_name="geo_unit")
    op.drop_index("ix_geo_unit_code", table_name="geo_unit")
    op.drop_index("ix_geo_unit_children", table_name="geo_unit")
    op.execute("DROP TRIGGER IF EXISTS geo_unit_parent_check ON geo_unit")
    op.drop_table("geo_unit")
    op.execute("DROP FUNCTION IF EXISTS geo_unit_parent_check()")
    op.drop_index("ix_geo_pin_office_pin", table_name="geo_pin_office")
    op.drop_table("geo_pin_office")
    op.drop_index(
        "uq_geo_snapshot_one_active", table_name="geo_snapshot", postgresql_where=sa.text("status = 'active'")
    )
    op.drop_table("geo_snapshot")
