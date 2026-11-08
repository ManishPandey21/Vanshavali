"""Indian geography reference data (ADR-0019).

Global and read-only for the application: ``geo_snapshot``, ``geo_unit``, ``geo_unit_alias`` and
``pincode_office`` hold Local Government Directory and India Post data, never tree data, so they
have no row-level security. The application role gets ``SELECT`` only
(``app.models.rls.READ_ONLY_TABLES``); ``python -m app.cli.geo`` loads them as the schema owner.

Units are versioned, not copied per snapshot: a row is valid from ``first_snapshot`` up to and
including ``last_snapshot`` (NULL = still valid in the newest snapshot). Snapshot ids are
``YYYY-MM`` and sort as text. LGD codes are unique per level only, so a unit is (level, code).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.base import Base, TimestampMixin, enum_column
from app.models.enums import GeoAliasKind, GeoLevel, GeoSnapshotStatus

_SNAP = "geo_snapshot.id"


class GeoSnapshot(TimestampMixin, Base):
    __tablename__ = "geo_snapshot"
    __table_args__ = (
        # at most one active snapshot
        Index(
            "uq_geo_snapshot_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM
    status: Mapped[GeoSnapshotStatus] = mapped_column(
        enum_column(GeoSnapshotStatus),
        default=GeoSnapshotStatus.STAGED,
        server_default=GeoSnapshotStatus.STAGED.value,
    )
    # one entry per imported file: stage, state, file name, source URL, download date, licence,
    # sha256, row counts and the change-report summary
    imports: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[str | None] = mapped_column(String(120))


class GeoUnit(Base):
    __tablename__ = "geo_unit"
    __table_args__ = (
        UniqueConstraint("level", "lgd_code", "first_snapshot", name="uq_geo_unit_version"),
        # one row per unit is valid in the newest snapshot
        Index(
            "uq_geo_unit_current",
            "level",
            "lgd_code",
            unique=True,
            postgresql_where=text("last_snapshot IS NULL"),
        ),
        # the cascade and scoped searches filter by ancestor (state / district / sub-district code)
        # among current rows; one partial index per ancestor level, ordered for children listing
        *(
            Index(
                f"ix_geo_unit_current_{col}",
                col,
                "level",
                "name_en",
                postgresql_where=text("last_snapshot IS NULL"),
            )
            for col in ("state_code", "district_code", "sub_district_code")
        ),
        Index("ix_geo_unit_code", "level", "lgd_code"),
        # exact and prefix name matches among current rows (search step 1)
        *(
            Index(
                f"ix_geo_unit_current_{col}_prefix",
                col,
                postgresql_ops={col: "text_pattern_ops"},
                postgresql_where=text("last_snapshot IS NULL"),
            )
            for col in ("name_key", "local_key")
        ),
        Index("ix_geo_unit_state", "state_code", "level"),
        Index(
            "ix_geo_unit_name_trgm",
            "name_key",
            postgresql_using="gin",
            postgresql_ops={"name_key": "gin_trgm_ops"},
        ),
        Index(
            "ix_geo_unit_local_trgm",
            "local_key",
            postgresql_using="gin",
            postgresql_ops={"local_key": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    level: Mapped[GeoLevel] = mapped_column(enum_column(GeoLevel))
    lgd_code: Mapped[str] = mapped_column(String(20))
    parent_level: Mapped[GeoLevel | None] = mapped_column(enum_column(GeoLevel, "geo_parent_level"))
    parent_lgd_code: Mapped[str | None] = mapped_column(String(20))
    # ancestors, denormalised so a search can be scoped to a state or district without joins
    state_code: Mapped[str | None] = mapped_column(String(20))
    district_code: Mapped[str | None] = mapped_column(String(20))
    sub_district_code: Mapped[str | None] = mapped_column(String(20))
    name_en: Mapped[str] = mapped_column(String(200))
    name_local: Mapped[str | None] = mapped_column(String(200))
    local_script: Mapped[str | None] = mapped_column(String(10))
    category: Mapped[str | None] = mapped_column(String(80))  # e.g. "Municipal Corporation"
    name_key: Mapped[str] = mapped_column(Text, default="", server_default="")
    local_key: Mapped[str] = mapped_column(Text, default="", server_default="")
    first_snapshot: Mapped[str] = mapped_column(String(7), ForeignKey(_SNAP, ondelete="CASCADE"))
    last_snapshot: Mapped[str | None] = mapped_column(String(7), ForeignKey(_SNAP))
    successor_codes: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}")


class GeoUnitAlias(TimestampMixin, Base):
    """Alternative and historical names of a unit. Never a family's own spelling (that stays on the place)."""

    __tablename__ = "geo_unit_alias"
    __table_args__ = (
        UniqueConstraint("level", "lgd_code", "name_key", name="uq_geo_unit_alias"),
        Index("ix_geo_unit_alias_unit", "level", "lgd_code"),
        Index("ix_geo_unit_alias_prefix", "name_key", postgresql_ops={"name_key": "text_pattern_ops"}),
        Index(
            "ix_geo_unit_alias_trgm",
            "name_key",
            postgresql_using="gin",
            postgresql_ops={"name_key": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    level: Mapped[GeoLevel] = mapped_column(enum_column(GeoLevel))
    lgd_code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    script: Mapped[str | None] = mapped_column(String(10))
    kind: Mapped[GeoAliasKind] = mapped_column(enum_column(GeoAliasKind))
    source: Mapped[str | None] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(Text, default="", server_default="")


class PincodeOffice(Base):
    """An India Post office (versioned like ``geo_unit``). Office coordinates are not imported (§1)."""

    __tablename__ = "pincode_office"
    __table_args__ = (
        UniqueConstraint("pincode", "office_key", "first_snapshot", name="uq_pincode_office_version"),
        Index(
            "ix_pincode_office_current",
            "pincode",
            postgresql_where=text("last_snapshot IS NULL"),
        ),
        Index("ix_pincode_office_pincode", "pincode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    pincode: Mapped[str] = mapped_column(String(6))
    office_name: Mapped[str] = mapped_column(String(200))
    office_key: Mapped[str] = mapped_column(String(200))
    office_type: Mapped[str | None] = mapped_column(String(20))
    delivery: Mapped[bool | None] = mapped_column(Boolean)
    division: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    circle: Mapped[str | None] = mapped_column(String(120))
    district_name: Mapped[str | None] = mapped_column(String(120))
    state_name: Mapped[str | None] = mapped_column(String(120))
    taluk_name: Mapped[str | None] = mapped_column(String(120))
    # LGD units matched by name at import; NULL when the match failed (listed in the change report)
    state_code: Mapped[str | None] = mapped_column(String(20))
    district_code: Mapped[str | None] = mapped_column(String(20))
    sub_district_code: Mapped[str | None] = mapped_column(String(20))
    first_snapshot: Mapped[str] = mapped_column(String(7), ForeignKey(_SNAP, ondelete="CASCADE"))
    last_snapshot: Mapped[str | None] = mapped_column(String(7), ForeignKey(_SNAP))
