from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    EvidenceMixin,
    ProvenanceMixin,
    TreeScopedMixin,
    enum_column,
    tree_fk,
    tree_unique,
)
from app.models.enums import AstrologyProvenance, PrivacyLevel


class AstrologyProfile(TreeScopedMixin, EvidenceMixin, ProvenanceMixin, Base):
    """Optional heritage module (PRS §11). Several profiles per person may coexist (chart vs entered)."""

    __tablename__ = "astrology_profile"
    __table_args__ = (
        tree_unique("astrology_profile"),
        tree_fk(["person_id"], "person"),
        tree_fk(["birth_event_id"], "event", ondelete="SET NULL"),
        tree_fk(["document_id"], "document", ondelete="SET NULL"),
        Index("ix_astrology_profile_person", "tree_id", "person_id"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    birth_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provenance_kind: Mapped[AstrologyProvenance] = mapped_column(enum_column(AstrologyProvenance))
    nakshatra: Mapped[str | None] = mapped_column(String(60))
    nakshatra_pada: Mapped[int | None] = mapped_column(Integer)
    rashi: Mapped[str | None] = mapped_column(String(60))
    lagna: Mapped[str | None] = mapped_column(String(60))
    tithi: Mapped[str | None] = mapped_column(String(60))
    paksha: Mapped[str | None] = mapped_column(String(20))
    yoga: Mapped[str | None] = mapped_column(String(60))
    karana: Mapped[str | None] = mapped_column(String(60))
    lunar_month: Mapped[str | None] = mapped_column(String(60))
    ayanamsha: Mapped[str | None] = mapped_column(String(60))
    calculation_system: Mapped[str | None] = mapped_column(String(120))
    ephemeris_version: Mapped[str | None] = mapped_column(String(80))
    chart_birth_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    chart_birth_time: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    chart_birth_place: Mapped[str | None] = mapped_column(String(300))
    place_latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    place_longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    timezone_id: Mapped[str | None] = mapped_column(String(64))
    utc_offset_minutes: Mapped[int | None] = mapped_column(Integer)
    calculation_timestamp: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    privacy_level: Mapped[PrivacyLevel] = mapped_column(
        enum_column(PrivacyLevel),
        default=PrivacyLevel.PRIVATE_TREE_ADMINS,
        server_default=PrivacyLevel.PRIVATE_TREE_ADMINS.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)
