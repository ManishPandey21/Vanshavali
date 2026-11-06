"""Indian geography reference data (ADR-0019): LGD administrative units and India Post offices.

Global reference data, loaded as versioned **snapshots**. Users only ever read the *active*
snapshot of each source; a new snapshot is staged, validated, approved and activated as a whole,
and the previous one stays for rollback. Nothing here describes a family: a family's own place is
the tree-scoped ``place`` row, which may name a unit by ``lgd_level`` + ``lgd_code``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    DDL,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, enum_column
from app.models.enums import GeoLevel, GeoSnapshotStatus, GeoSource, GeoUnitOrigin

# child level → the levels its parent may have (ADR-0019 increment 1). The trigger below states the
# same table in SQL; test_geo.py checks that the two agree.
PARENT_LEVELS: dict[str, tuple[str, ...]] = {
    "country": (),
    "state": ("country",),
    "district": ("state",),
    "subdistrict": ("district",),
    "block": ("district",),
    "gram_panchayat": ("block", "subdistrict"),
    "village": ("subdistrict",),
    "town": ("subdistrict", "district"),
    "ulb": ("district",),
}


class GeoSnapshot(Base):
    __tablename__ = "geo_snapshot"
    __table_args__ = (
        # at most one active snapshot per source
        Index(
            "uq_geo_snapshot_one_active", "source", unique=True, postgresql_where=text("status = 'active'")
        ),
        UniqueConstraint("source", "label", name="uq_geo_snapshot_label"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    source: Mapped[GeoSource] = mapped_column(enum_column(GeoSource))
    label: Mapped[str] = mapped_column(String(40))  # e.g. "2026-10"
    status: Mapped[GeoSnapshotStatus] = mapped_column(
        enum_column(GeoSnapshotStatus), default=GeoSnapshotStatus.STAGED, server_default="staged"
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    downloaded_on: Mapped[dt.date | None] = mapped_column(Date)
    licence: Mapped[str] = mapped_column(String(200))
    attribution: Mapped[str] = mapped_column(Text)
    # [{name, sha256, bytes, rows}]
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # validation errors/warnings, counts per level and the diff against the previously active snapshot
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    staged_by: Mapped[str | None] = mapped_column(String(200))  # operator note (CLI) or admin name
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GeoUnit(Base):
    """One LGD unit (state, district, sub-district, village, town, ULB…) in one snapshot."""

    __tablename__ = "geo_unit"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "level", "code", name="uq_geo_unit_code"),
        Index("ix_geo_unit_children", "snapshot_id", "parent_id"),
        Index("ix_geo_unit_level", "snapshot_id", "level"),
        Index("ix_geo_unit_code", "level", "code"),
        Index(
            "ix_geo_unit_search_trgm",
            "search_key",
            postgresql_using="gin",
            postgresql_ops={"search_key": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_snapshot.id", ondelete="CASCADE")
    )
    level: Mapped[GeoLevel] = mapped_column(enum_column(GeoLevel))
    code: Mapped[str] = mapped_column(String(40))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_unit.id", ondelete="CASCADE")
    )
    name_en: Mapped[str] = mapped_column(String(200))
    name_local: Mapped[str | None] = mapped_column(String(200))
    local_script: Mapped[str | None] = mapped_column(String(8))
    # what the state calls this level (Tehsil, Taluka, Mandal, Circle…), shown as the field label
    local_term: Mapped[str | None] = mapped_column(String(60))
    category: Mapped[str | None] = mapped_column(String(60))  # town / ULB type
    alt_names: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list, server_default="{}")
    former_names: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list, server_default="{}")
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    successor_codes: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")
    origin: Mapped[GeoUnitOrigin] = mapped_column(
        enum_column(GeoUnitOrigin), default=GeoUnitOrigin.OFFICIAL, server_default="official"
    )
    search_key: Mapped[str] = mapped_column(Text, default="", server_default="")


class GeoPinOffice(Base):
    """One India Post office. A PIN can have many offices and serve many units (ADR-0019 §2)."""

    __tablename__ = "geo_pin_office"
    __table_args__ = (
        Index("ix_geo_pin_office_pin", "snapshot_id", "pin"),
        UniqueConstraint("snapshot_id", "pin", "office_name", name="uq_geo_pin_office"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_snapshot.id", ondelete="CASCADE")
    )
    pin: Mapped[str] = mapped_column(String(6))
    office_name: Mapped[str] = mapped_column(String(200))
    office_type: Mapped[str | None] = mapped_column(String(10))  # H.O. / S.O. / B.O.
    delivery: Mapped[bool | None] = mapped_column(Boolean)
    district_name: Mapped[str | None] = mapped_column(String(200))
    state_name: Mapped[str | None] = mapped_column(String(200))


class GeoPinUnit(Base):
    """Which LGD units an office serves, by level and code (so the link survives LGD snapshots)."""

    __tablename__ = "geo_pin_unit"
    __table_args__ = (
        UniqueConstraint("office_id", "unit_level", "unit_code", name="uq_geo_pin_unit"),
        Index("ix_geo_pin_unit_unit", "unit_level", "unit_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geo_pin_office.id", ondelete="CASCADE")
    )
    unit_level: Mapped[GeoLevel] = mapped_column(enum_column(GeoLevel, "geo_pin_unit_level"))
    unit_code: Mapped[str] = mapped_column(String(40))


# The hierarchy is enforced by the database, so no importer bug can store a village under a state.
GEO_UNIT_PARENT_SQL = """
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
# DDL applies %-formatting (for %(table)s), so the RAISE placeholders are escaped here only
GEO_UNIT_PARENT_FUNCTION = DDL(GEO_UNIT_PARENT_SQL.replace("%", "%%"))
GEO_UNIT_PARENT_TRIGGER_SQL = (
    "CREATE TRIGGER geo_unit_parent_check BEFORE INSERT OR UPDATE OF parent_id, level, snapshot_id "
    "ON geo_unit FOR EACH ROW EXECUTE FUNCTION geo_unit_parent_check()"
)
GEO_UNIT_PARENT_TRIGGER = DDL(GEO_UNIT_PARENT_TRIGGER_SQL)
event.listen(GeoUnit.__table__, "after_create", GEO_UNIT_PARENT_FUNCTION)
event.listen(GeoUnit.__table__, "after_create", GEO_UNIT_PARENT_TRIGGER)
