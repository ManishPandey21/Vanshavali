"""geo reference data (LGD, India Post)

Revision ID: 8e4a1f6c2b37
Revises: 5c2d8e1f7a90
Create Date: 2026-11-07

ADR-0019: global, read-only reference tables ``geo_snapshot``, ``geo_unit`` (versioned rows),
``geo_unit_alias`` and ``pincode_office``, loaded by ``python -m app.cli.geo``. No row-level
security (they hold no tree data); the application role may only SELECT them. ``place`` gains
``lgd_level`` and ``lgd_snapshot_id`` for codes picked from the reference.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL

revision: str = "8e4a1f6c2b37"
down_revision: str | None = "5c2d8e1f7a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
# partial indexes on current rows, one per ancestor the cascade and scoped searches filter by
ANCESTOR_COLUMNS = ("state_code", "district_code", "sub_district_code")


def upgrade() -> None:
    op.create_table(
        "geo_snapshot",
        sa.Column("id", sa.String(length=7), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "staged",
                "active",
                "inactive",
                name="geosnapshotstatus",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="staged",
            nullable=False,
        ),
        sa.Column("imports", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('staged', 'active', 'inactive')", name=op.f("ck_geo_snapshot_geosnapshotstatus")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_snapshot")),
    )
    op.create_index(
        "uq_geo_snapshot_active",
        "geo_snapshot",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "geo_unit_alias",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "level",
            sa.Enum(
                "state",
                "district",
                "sub_district",
                "village",
                "urban_body",
                name="geolevel",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("lgd_code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("script", sa.String(length=10), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "alternative",
                "historical",
                "curated",
                name="geoaliaskind",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("name_key", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('alternative', 'historical', 'curated')", name=op.f("ck_geo_unit_alias_geoaliaskind")
        ),
        sa.CheckConstraint(
            "level IN ('state', 'district', 'sub_district', 'village', 'urban_body')",
            name=op.f("ck_geo_unit_alias_geolevel"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_unit_alias")),
        sa.UniqueConstraint("level", "lgd_code", "name_key", name="uq_geo_unit_alias"),
    )
    op.create_index(
        "ix_geo_unit_alias_trgm",
        "geo_unit_alias",
        ["name_key"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_key": "gin_trgm_ops"},
    )
    op.create_index("ix_geo_unit_alias_unit", "geo_unit_alias", ["level", "lgd_code"], unique=False)
    op.create_index(
        "ix_geo_unit_alias_prefix",
        "geo_unit_alias",
        ["name_key"],
        unique=False,
        postgresql_ops={"name_key": "text_pattern_ops"},
    )
    op.create_table(
        "geo_unit",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "level",
            sa.Enum(
                "state",
                "district",
                "sub_district",
                "village",
                "urban_body",
                name="geolevel",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("lgd_code", sa.String(length=20), nullable=False),
        sa.Column(
            "parent_level",
            sa.Enum(
                "state",
                "district",
                "sub_district",
                "village",
                "urban_body",
                name="geo_parent_level",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("parent_lgd_code", sa.String(length=20), nullable=True),
        sa.Column("state_code", sa.String(length=20), nullable=True),
        sa.Column("district_code", sa.String(length=20), nullable=True),
        sa.Column("sub_district_code", sa.String(length=20), nullable=True),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("name_local", sa.String(length=200), nullable=True),
        sa.Column("local_script", sa.String(length=10), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("name_key", sa.Text(), server_default="", nullable=False),
        sa.Column("local_key", sa.Text(), server_default="", nullable=False),
        sa.Column("first_snapshot", sa.String(length=7), nullable=False),
        sa.Column("last_snapshot", sa.String(length=7), nullable=True),
        sa.Column(
            "successor_codes", postgresql.ARRAY(sa.String(length=20)), server_default="{}", nullable=False
        ),
        sa.CheckConstraint(
            "level IN ('state', 'district', 'sub_district', 'village', 'urban_body')",
            name=op.f("ck_geo_unit_geolevel"),
        ),
        sa.CheckConstraint(
            "parent_level IN ('state', 'district', 'sub_district', 'village', 'urban_body')",
            name=op.f("ck_geo_unit_geo_parent_level"),
        ),
        sa.ForeignKeyConstraint(
            ["first_snapshot"],
            ["geo_snapshot.id"],
            name=op.f("fk_geo_unit_first_snapshot_geo_snapshot"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_snapshot"], ["geo_snapshot.id"], name=op.f("fk_geo_unit_last_snapshot_geo_snapshot")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geo_unit")),
        sa.UniqueConstraint("level", "lgd_code", "first_snapshot", name="uq_geo_unit_version"),
    )
    op.create_index("ix_geo_unit_code", "geo_unit", ["level", "lgd_code"], unique=False)
    for col in ("name_key", "local_key"):
        op.create_index(
            f"ix_geo_unit_current_{col}_prefix",
            "geo_unit",
            [col],
            unique=False,
            postgresql_ops={col: "text_pattern_ops"},
            postgresql_where=sa.text("last_snapshot IS NULL"),
        )
    for col in ANCESTOR_COLUMNS:
        op.create_index(
            f"ix_geo_unit_current_{col}",
            "geo_unit",
            [col, "level", "name_en"],
            unique=False,
            postgresql_where=sa.text("last_snapshot IS NULL"),
        )
    op.create_index(
        "ix_geo_unit_local_trgm",
        "geo_unit",
        ["local_key"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"local_key": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_geo_unit_name_trgm",
        "geo_unit",
        ["name_key"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name_key": "gin_trgm_ops"},
    )
    op.create_index("ix_geo_unit_state", "geo_unit", ["state_code", "level"], unique=False)
    op.create_index(
        "uq_geo_unit_current",
        "geo_unit",
        ["level", "lgd_code"],
        unique=True,
        postgresql_where=sa.text("last_snapshot IS NULL"),
    )
    op.create_table(
        "pincode_office",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pincode", sa.String(length=6), nullable=False),
        sa.Column("office_name", sa.String(length=200), nullable=False),
        sa.Column("office_key", sa.String(length=200), nullable=False),
        sa.Column("office_type", sa.String(length=20), nullable=True),
        sa.Column("delivery", sa.Boolean(), nullable=True),
        sa.Column("division", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("circle", sa.String(length=120), nullable=True),
        sa.Column("district_name", sa.String(length=120), nullable=True),
        sa.Column("state_name", sa.String(length=120), nullable=True),
        sa.Column("taluk_name", sa.String(length=120), nullable=True),
        sa.Column("state_code", sa.String(length=20), nullable=True),
        sa.Column("district_code", sa.String(length=20), nullable=True),
        sa.Column("sub_district_code", sa.String(length=20), nullable=True),
        sa.Column("first_snapshot", sa.String(length=7), nullable=False),
        sa.Column("last_snapshot", sa.String(length=7), nullable=True),
        sa.ForeignKeyConstraint(
            ["first_snapshot"],
            ["geo_snapshot.id"],
            name=op.f("fk_pincode_office_first_snapshot_geo_snapshot"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_snapshot"], ["geo_snapshot.id"], name=op.f("fk_pincode_office_last_snapshot_geo_snapshot")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pincode_office")),
        sa.UniqueConstraint("pincode", "office_key", "first_snapshot", name="uq_pincode_office_version"),
    )
    op.create_index(
        "ix_pincode_office_current",
        "pincode_office",
        ["pincode"],
        unique=False,
        postgresql_where=sa.text("last_snapshot IS NULL"),
    )
    op.create_index("ix_pincode_office_pincode", "pincode_office", ["pincode"], unique=False)
    op.add_column(
        "place",
        sa.Column(
            "lgd_level",
            sa.Enum(
                "state",
                "district",
                "sub_district",
                "village",
                "urban_body",
                name="place_lgd_level",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=True,
        ),
    )
    op.add_column("place", sa.Column("lgd_snapshot_id", sa.String(length=7), nullable=True))
    op.create_check_constraint(
        op.f("ck_place_place_lgd_level"),
        "place",
        "lgd_level IN ('state', 'district', 'sub_district', 'village', 'urban_body')",
    )
    op.create_foreign_key(
        op.f("fk_place_lgd_snapshot_id_geo_snapshot"),
        "place",
        "geo_snapshot",
        ["lgd_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # grants SELECT on the new tables and revokes writes on the read-only reference tables
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    op.drop_constraint(op.f("fk_place_lgd_snapshot_id_geo_snapshot"), "place", type_="foreignkey")
    op.drop_constraint(op.f("ck_place_place_lgd_level"), "place", type_="check")
    op.drop_column("place", "lgd_snapshot_id")
    op.drop_column("place", "lgd_level")
    op.drop_index("ix_pincode_office_pincode", table_name="pincode_office")
    op.drop_index(
        "ix_pincode_office_current",
        table_name="pincode_office",
        postgresql_where=sa.text("last_snapshot IS NULL"),
    )
    op.drop_table("pincode_office")
    op.drop_index(
        "uq_geo_unit_current", table_name="geo_unit", postgresql_where=sa.text("last_snapshot IS NULL")
    )
    op.drop_index("ix_geo_unit_state", table_name="geo_unit")
    op.drop_index(
        "ix_geo_unit_name_trgm",
        table_name="geo_unit",
        postgresql_using="gin",
        postgresql_ops={"name_key": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_geo_unit_local_trgm",
        table_name="geo_unit",
        postgresql_using="gin",
        postgresql_ops={"local_key": "gin_trgm_ops"},
    )
    for col in ANCESTOR_COLUMNS:
        op.drop_index(f"ix_geo_unit_current_{col}", table_name="geo_unit")
    for col in ("name_key", "local_key"):
        op.drop_index(f"ix_geo_unit_current_{col}_prefix", table_name="geo_unit")
    op.drop_index("ix_geo_unit_code", table_name="geo_unit")
    op.drop_table("geo_unit")
    op.drop_index("ix_geo_unit_alias_prefix", table_name="geo_unit_alias")
    op.drop_index("ix_geo_unit_alias_unit", table_name="geo_unit_alias")
    op.drop_index(
        "ix_geo_unit_alias_trgm",
        table_name="geo_unit_alias",
        postgresql_using="gin",
        postgresql_ops={"name_key": "gin_trgm_ops"},
    )
    op.drop_table("geo_unit_alias")
    op.drop_index(
        "uq_geo_snapshot_active", table_name="geo_snapshot", postgresql_where=sa.text("status = 'active'")
    )
    op.drop_table("geo_snapshot")
