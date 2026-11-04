from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
    Confidence,
    EventSignificance,
    EventType,
    LifeEventCategory,
    Lineage,
    LocationPrecision,
    NameType,
    ParticipantRole,
    PlaceType,
    PrivacyLevel,
    ProfileStatus,
    RelationshipType,
    SexAtBirth,
)


class Person(TreeScopedMixin, Base):
    __tablename__ = "person"
    __table_args__ = (tree_unique("person"), tree_fk(["merged_into_id"], "person", ondelete="SET NULL"))

    profile_status: Mapped[ProfileStatus] = mapped_column(
        enum_column(ProfileStatus), default=ProfileStatus.UNKNOWN, server_default=ProfileStatus.UNKNOWN.value
    )
    preferred_display_name: Mapped[str] = mapped_column(String(300))
    sex_at_birth: Mapped[SexAtBirth | None] = mapped_column(enum_column(SexAtBirth), nullable=True)
    gender_identity: Mapped[str | None] = mapped_column(String(100))
    primary_language: Mapped[str | None] = mapped_column(String(16))
    scripts_used: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}")
    privacy_level: Mapped[PrivacyLevel] = mapped_column(
        enum_column(PrivacyLevel),
        default=PrivacyLevel.TREE_MEMBERS,
        server_default=PrivacyLevel.TREE_MEMBERS.value,
    )
    # field-group -> PrivacyLevel overrides (see authz.privacy.FIELD_GROUPS)
    field_privacy: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, server_default="{}")
    claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    occupation: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    contact_info: Mapped[str | None] = mapped_column(Text)
    residential_address: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Added as "unknown for now" by Smart Add (ADR-0020); cleared when the person gets a name.
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class RelativeAgeOrder(TreeScopedMixin, Base):
    """Family-confirmed "A is older than B" for two relatives (ADR-0020), e.g. Tau vs Chacha.

    Family knowledge that takes precedence over (often approximate) birth dates when kinship terms
    depend on relative age. One row per ordered pair; the reverse pair is rejected by the service.
    """

    __tablename__ = "relative_age_order"
    __table_args__ = (
        tree_unique("relative_age_order"),
        tree_fk(["elder_person_id"], "person", ondelete="CASCADE"),
        tree_fk(["younger_person_id"], "person", ondelete="CASCADE"),
        UniqueConstraint(
            "tree_id", "elder_person_id", "younger_person_id", name="uq_relative_age_order_pair"
        ),
        CheckConstraint("elder_person_id <> younger_person_id", name="distinct"),
    )

    elder_person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    younger_person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # created_by records who confirmed the order


class MergeRecord(TreeScopedMixin, Base):
    """A reversible person merge (PRS §53): every row change is recorded so it can be undone."""

    __tablename__ = "merge_record"
    __table_args__ = (
        tree_unique("merge_record"),
        tree_fk(["survivor_id"], "person"),
        tree_fk(["merged_id"], "person"),
    )

    survivor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    merged_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    reverted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    reverted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class NameRecord(TreeScopedMixin, EvidenceMixin, ProvenanceMixin, Base):
    __tablename__ = "name_record"
    __table_args__ = (
        tree_unique("name_record"),
        tree_fk(["person_id"], "person"),
        Index("ix_name_record_person", "tree_id", "person_id"),
        Index(
            "ix_name_record_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    type: Mapped[NameType] = mapped_column(enum_column(NameType), default=NameType.BIRTH)
    given_name: Mapped[str | None] = mapped_column(String(200))
    middle_names: Mapped[str | None] = mapped_column(String(200))
    patronymic: Mapped[str | None] = mapped_column(String(200))
    matronymic: Mapped[str | None] = mapped_column(String(200))
    surname: Mapped[str | None] = mapped_column(String(200))
    family_house_name: Mapped[str | None] = mapped_column(String(200))
    village_prefix: Mapped[str | None] = mapped_column(String(200))
    honorific_prefix: Mapped[str | None] = mapped_column(String(80))
    honorific_suffix: Mapped[str | None] = mapped_column(String(80))
    full_name_as_recorded: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[str | None] = mapped_column(String(16))
    script: Mapped[str | None] = mapped_column(String(20))
    romanized_value: Mapped[str | None] = mapped_column(String(500))
    date_range: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    search_phonetic: Mapped[str] = mapped_column(Text, default="", server_default="")


class Place(TreeScopedMixin, Base):
    __tablename__ = "place"
    __table_args__ = (
        tree_unique("place"),
        tree_fk(["parent_place_id"], "place", ondelete="SET NULL"),
        Index(
            "ix_place_search_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    canonical_name: Mapped[str] = mapped_column(String(300))
    local_names: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    historical_names: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    place_type: Mapped[PlaceType] = mapped_column(enum_column(PlaceType), default=PlaceType.OTHER)
    parent_place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    geocoding_source: Mapped[str | None] = mapped_column(String(120))
    date_validity: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    lgd_code: Mapped[str | None] = mapped_column(String(40))
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    # geo-tagging (ADR-0015): administrative context, precision, provenance and coordinate privacy
    locality: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    map_label: Mapped[str | None] = mapped_column(String(200))
    location_precision: Mapped[LocationPrecision] = mapped_column(
        enum_column(LocationPrecision),
        default=LocationPrecision.UNKNOWN,
        server_default=LocationPrecision.UNKNOWN.value,
    )
    geo_confidence: Mapped[Confidence] = mapped_column(
        enum_column(Confidence, "geo_confidence"),
        default=Confidence.UNKNOWN,
        server_default=Confidence.UNKNOWN.value,
    )
    geo_note: Mapped[str | None] = mapped_column(Text)
    # viewers below this level get coarsened coordinates; NULL = any member sees exact coordinates
    coordinate_privacy: Mapped[PrivacyLevel | None] = mapped_column(
        enum_column(PrivacyLevel, "coordinate_privacy"), nullable=True
    )


class Relationship(TreeScopedMixin, EvidenceMixin, ProvenanceMixin, Base):
    """Typed edge. Parent types: person_a = parent, person_b = child. Symmetric types: a < b."""

    __tablename__ = "relationship"
    __table_args__ = (
        tree_unique("relationship"),
        tree_fk(["person_a_id"], "person"),
        tree_fk(["person_b_id"], "person"),
        tree_fk(["union_id"], "relationship", ondelete="SET NULL"),
        CheckConstraint("person_a_id <> person_b_id", name="no_self_relationship"),
        UniqueConstraint("tree_id", "type", "person_a_id", "person_b_id", name="uq_relationship_edge"),
        Index("ix_relationship_a", "tree_id", "person_a_id", "type"),
        Index("ix_relationship_b", "tree_id", "person_b_id", "type"),
    )

    person_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    person_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    type: Mapped[RelationshipType] = mapped_column(enum_column(RelationshipType))
    subtype: Mapped[str | None] = mapped_column(String(80))
    lineage: Mapped[Lineage | None] = mapped_column(enum_column(Lineage), nullable=True)
    union_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    start_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    end_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    union_order: Mapped[int | None] = mapped_column(Integer)
    legal_status: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)


class Event(TreeScopedMixin, EvidenceMixin, ProvenanceMixin, Base):
    __tablename__ = "event"
    __table_args__ = (
        tree_unique("event"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        tree_fk(["origin_place_id"], "place", ondelete="SET NULL"),
        Index("ix_event_type_sort", "tree_id", "type", "date_sort_from"),
    )

    type: Mapped[EventType] = mapped_column(enum_column(EventType))
    subtype: Mapped[str | None] = mapped_column(String(80))
    date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    date_sort_from: Mapped[dt.date | None] = mapped_column(Date)
    date_sort_to: Mapped[dt.date | None] = mapped_column(Date)
    time: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    timezone_id: Mapped[str | None] = mapped_column(String(64))
    utc_offset_minutes: Mapped[int | None] = mapped_column(Integer)
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    place_as_recorded: Mapped[str | None] = mapped_column(String(500))
    origin_place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    origin_place_as_recorded: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6))
    reason: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    privacy_level: Mapped[PrivacyLevel | None] = mapped_column(enum_column(PrivacyLevel), nullable=True)
    # important life events (ADR-0015)
    title: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[LifeEventCategory | None] = mapped_column(enum_column(LifeEventCategory), nullable=True)
    significance: Mapped[EventSignificance] = mapped_column(
        enum_column(EventSignificance),
        default=EventSignificance.STANDARD,
        server_default=EventSignificance.STANDARD.value,
    )
    location_precision: Mapped[LocationPrecision | None] = mapped_column(
        enum_column(LocationPrecision, "event_location_precision"), nullable=True
    )


class EventParticipant(TreeScopedMixin, Base):
    __tablename__ = "event_participant"
    __table_args__ = (
        tree_unique("event_participant"),
        tree_fk(["event_id"], "event"),
        tree_fk(["person_id"], "person"),
        UniqueConstraint("event_id", "person_id", "role", name="uq_event_participant"),
        Index("ix_event_participant_person", "tree_id", "person_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    role: Mapped[ParticipantRole] = mapped_column(
        enum_column(ParticipantRole), default=ParticipantRole.PRINCIPAL
    )
    role_detail: Mapped[str | None] = mapped_column(String(80))
