from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Date, Index, Numeric, String, Text, UniqueConstraint
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
from app.models.enums import (
    HolderType,
    InterestStatus,
    InterestType,
    PrivacyLevel,
    PropertyClassification,
    PropertyEventType,
    PropertyType,
)


class Property(TreeScopedMixin, Base):
    __tablename__ = "property"
    __table_args__ = (tree_unique("property"), tree_fk(["place_id"], "place", ondelete="SET NULL"))

    property_type: Mapped[PropertyType] = mapped_column(enum_column(PropertyType))
    classification: Mapped[PropertyClassification] = mapped_column(
        enum_column(PropertyClassification),
        default=PropertyClassification.UNKNOWN,
        server_default=PropertyClassification.UNKNOWN.value,
    )
    display_name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    address_text: Mapped[str | None] = mapped_column(Text)
    current_status: Mapped[str | None] = mapped_column(String(120))
    privacy_level: Mapped[PrivacyLevel] = mapped_column(
        enum_column(PrivacyLevel),
        default=PrivacyLevel.PRIVATE_TREE_ADMINS,
        server_default=PrivacyLevel.PRIVATE_TREE_ADMINS.value,
    )


class LandParcel(TreeScopedMixin, ProvenanceMixin, Base):
    __tablename__ = "land_parcel"
    __table_args__ = (
        tree_unique("land_parcel"),
        tree_fk(["property_id"], "property"),
        tree_fk(["parent_parcel_id"], "land_parcel", ondelete="SET NULL"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        Index("ix_land_parcel_property", "tree_id", "property_id"),
    )

    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    parent_parcel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    state_or_ut: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    tehsil_taluk: Mapped[str | None] = mapped_column(String(100))
    village: Mapped[str | None] = mapped_column(String(150))
    revenue_village_code: Mapped[str | None] = mapped_column(String(60))
    survey_number: Mapped[str | None] = mapped_column(String(60))
    khasra_or_gata_number: Mapped[str | None] = mapped_column(String(60))
    khata_number: Mapped[str | None] = mapped_column(String(60))
    khatauni_number: Mapped[str | None] = mapped_column(String(60))
    patta_number: Mapped[str | None] = mapped_column(String(60))
    plot_number: Mapped[str | None] = mapped_column(String(60))
    subdivision_number: Mapped[str | None] = mapped_column(String(60))
    ulpin: Mapped[str | None] = mapped_column(String(20))
    area: Mapped[float | None] = mapped_column(Numeric(18, 4))
    area_unit: Mapped[str | None] = mapped_column(String(40))
    land_use: Mapped[str | None] = mapped_column(String(100))
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    cadastral_map_reference: Mapped[str | None] = mapped_column(String(200))
    state_portal_reference: Mapped[str | None] = mapped_column(String(300))
    extra_identifiers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text)


class PropertyEvent(TreeScopedMixin, EvidenceMixin, ProvenanceMixin, Base):
    __tablename__ = "property_event"
    __table_args__ = (
        tree_unique("property_event"),
        tree_fk(["property_id"], "property"),
        tree_fk(["related_event_id"], "event", ondelete="SET NULL"),
        Index("ix_property_event_property", "tree_id", "property_id", "date_sort_from"),
    )

    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    type: Mapped[PropertyEventType] = mapped_column(enum_column(PropertyEventType))
    date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    date_sort_from: Mapped[dt.date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    registration_number: Mapped[str | None] = mapped_column(String(120))
    registration_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    mutation_number: Mapped[str | None] = mapped_column(String(120))
    consideration: Mapped[str | None] = mapped_column(String(200))
    related_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PropertyEventParcel(TreeScopedMixin, Base):
    __tablename__ = "property_event_parcel"
    __table_args__ = (
        tree_unique("property_event_parcel"),
        tree_fk(["property_event_id"], "property_event"),
        tree_fk(["parcel_id"], "land_parcel"),
        UniqueConstraint("property_event_id", "parcel_id", name="uq_property_event_parcel"),
    )

    property_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    parcel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


class PropertyInterest(TreeScopedMixin, EvidenceMixin, ProvenanceMixin, Base):
    __tablename__ = "property_interest"
    __table_args__ = (
        tree_unique("property_interest"),
        tree_fk(["property_id"], "property"),
        tree_fk(["parcel_id"], "land_parcel", ondelete="SET NULL"),
        tree_fk(["holder_person_id"], "person", ondelete="RESTRICT"),
        tree_fk(["holder_branch_id"], "family_branch", ondelete="RESTRICT"),
        tree_fk(["created_by_event_id"], "property_event", ondelete="SET NULL"),
        tree_fk(["ended_by_event_id"], "property_event", ondelete="SET NULL"),
        CheckConstraint("share_denominator > 0 AND share_numerator >= 0", name="valid_share"),
        CheckConstraint("share_numerator <= share_denominator", name="share_at_most_one"),
        CheckConstraint(
            "(holder_type = 'person' AND holder_person_id IS NOT NULL) OR "
            "(holder_type = 'family_branch' AND holder_branch_id IS NOT NULL) OR "
            "(holder_type IN ('trust','entity','unknown'))",
            name="holder_matches",
        ),
        Index("ix_property_interest_property", "tree_id", "property_id"),
        Index("ix_property_interest_holder", "tree_id", "holder_person_id"),
    )

    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    holder_type: Mapped[HolderType] = mapped_column(enum_column(HolderType))
    holder_person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    holder_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    holder_name: Mapped[str | None] = mapped_column(String(300))
    interest_type: Mapped[InterestType] = mapped_column(enum_column(InterestType))
    share_numerator: Mapped[int] = mapped_column(BigInteger, default=1)
    share_denominator: Mapped[int] = mapped_column(BigInteger, default=1)
    valid_from: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valid_from_sort: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valid_to_sort: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[InterestStatus] = mapped_column(enum_column(InterestStatus))
    created_by_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ended_by_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)
