from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate, GenealogicalTime
from app.models.enums import (
    Confidence,
    EventType,
    EvidenceStatus,
    Lineage,
    NameType,
    ParticipantRole,
    PlaceType,
    PrivacyLevel,
    ProfileStatus,
    ProvenanceOrigin,
    RelationshipType,
    SexAtBirth,
)


class ProvenanceOut(ApiModel):
    origin: ProvenanceOrigin
    algorithm_or_model: str | None = None
    model_version: str | None = None
    source_document_id: uuid.UUID | None = None
    source_location: str | None = None
    extracted_at: dt.datetime | None = None
    confirmed_by: uuid.UUID | None = None
    confirmed_at: dt.datetime | None = None

    @classmethod
    def of(cls, obj: Any) -> ProvenanceOut:
        return cls(
            origin=obj.prov_origin,
            algorithm_or_model=obj.prov_algorithm,
            model_version=obj.prov_model_version,
            source_document_id=obj.prov_source_document_id,
            source_location=obj.prov_source_location,
            extracted_at=obj.prov_extracted_at,
            confirmed_by=obj.prov_confirmed_by,
            confirmed_at=obj.prov_confirmed_at,
        )


# ---------- places ----------
class PlaceName(ApiModel):
    name: str = Field(max_length=300)
    language: str | None = Field(default=None, max_length=16)
    script: str | None = Field(default=None, max_length=20)
    valid_from: GenealogicalDate | None = None
    valid_to: GenealogicalDate | None = None
    note: str | None = Field(default=None, max_length=500)


class PlaceIn(ApiModel):
    canonical_name: str = Field(min_length=1, max_length=300)
    place_type: PlaceType = PlaceType.OTHER
    parent_place_id: uuid.UUID | None = None
    local_names: list[PlaceName] = []
    historical_names: list[PlaceName] = []
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geocoding_source: str | None = Field(default=None, max_length=120)
    lgd_code: str | None = Field(default=None, max_length=40)


class PlaceUpdate(ApiModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=300)
    place_type: PlaceType | None = None
    parent_place_id: uuid.UUID | None = None
    local_names: list[PlaceName] | None = None
    historical_names: list[PlaceName] | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geocoding_source: str | None = None
    lgd_code: str | None = None


class PlaceOut(ApiModel):
    id: uuid.UUID
    canonical_name: str
    place_type: PlaceType
    parent_place_id: uuid.UUID | None
    local_names: list[dict[str, Any]]
    historical_names: list[dict[str, Any]]
    latitude: float | None
    longitude: float | None
    geocoding_source: str | None
    lgd_code: str | None
    hierarchy: list[str] = []


# ---------- names ----------
class NameIn(ApiModel):
    type: NameType = NameType.BIRTH
    given_name: str | None = Field(default=None, max_length=200)
    middle_names: str | None = Field(default=None, max_length=200)
    patronymic: str | None = Field(default=None, max_length=200)
    matronymic: str | None = Field(default=None, max_length=200)
    surname: str | None = Field(default=None, max_length=200)
    family_house_name: str | None = Field(default=None, max_length=200)
    village_prefix: str | None = Field(default=None, max_length=200)
    honorific_prefix: str | None = Field(default=None, max_length=80)
    honorific_suffix: str | None = Field(default=None, max_length=80)
    full_name_as_recorded: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=16)
    script: str | None = Field(default=None, max_length=20)
    romanized_value: str | None = Field(default=None, max_length=500)
    date_range: dict[str, GenealogicalDate | None] | None = None
    is_preferred: bool = False
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN

    @model_validator(mode="after")
    def _has_content(self) -> NameIn:
        if not any(
            [
                self.given_name,
                self.surname,
                self.full_name_as_recorded,
                self.middle_names,
                self.patronymic,
                self.family_house_name,
            ]
        ):
            raise ValueError("a name needs at least a given name, surname or the full name as recorded")
        return self


class NameUpdate(ApiModel):
    type: NameType | None = None
    given_name: str | None = None
    middle_names: str | None = None
    patronymic: str | None = None
    matronymic: str | None = None
    surname: str | None = None
    family_house_name: str | None = None
    village_prefix: str | None = None
    honorific_prefix: str | None = None
    honorific_suffix: str | None = None
    full_name_as_recorded: str | None = None
    language: str | None = None
    script: str | None = None
    romanized_value: str | None = None
    is_preferred: bool | None = None
    evidence_status: EvidenceStatus | None = None
    confidence: Confidence | None = None


class NameOut(ApiModel):
    id: uuid.UUID
    type: NameType
    given_name: str | None
    middle_names: str | None
    patronymic: str | None
    matronymic: str | None
    surname: str | None
    family_house_name: str | None
    village_prefix: str | None
    honorific_prefix: str | None
    honorific_suffix: str | None
    full_name_as_recorded: str | None
    language: str | None
    script: str | None
    romanized_value: str | None
    date_range: dict[str, Any] | None
    is_preferred: bool
    evidence_status: EvidenceStatus
    confidence: Confidence
    provenance: ProvenanceOut | None = None
    display: str = ""


# ---------- events ----------
class EventCore(ApiModel):
    date: GenealogicalDate | None = None
    time: GenealogicalTime | None = None
    timezone_id: str | None = Field(default=None, max_length=64)
    utc_offset_minutes: int | None = Field(default=None, ge=-14 * 60, le=14 * 60)
    place_id: uuid.UUID | None = None
    place_as_recorded: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = Field(default=None, max_length=5000)
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN

    @field_validator("timezone_id")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown IANA time zone") from exc
        return v


class VitalIn(EventCore):
    """Birth/death details embedded in person creation."""


class ParticipantIn(ApiModel):
    person_id: uuid.UUID
    role: ParticipantRole = ParticipantRole.PRINCIPAL
    role_detail: str | None = Field(default=None, max_length=80)


class EventIn(EventCore):
    type: EventType
    subtype: str | None = Field(default=None, max_length=80)
    participants: list[ParticipantIn] = Field(min_length=1)
    origin_place_id: uuid.UUID | None = None
    origin_place_as_recorded: str | None = Field(default=None, max_length=500)
    reason: str | None = Field(default=None, max_length=5000)
    is_preferred: bool = True
    privacy_level: PrivacyLevel | None = None


class EventUpdate(ApiModel):
    subtype: str | None = None
    date: GenealogicalDate | None = None
    time: GenealogicalTime | None = None
    timezone_id: str | None = None
    utc_offset_minutes: int | None = None
    place_id: uuid.UUID | None = None
    place_as_recorded: str | None = None
    origin_place_id: uuid.UUID | None = None
    origin_place_as_recorded: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    reason: str | None = None
    description: str | None = None
    is_preferred: bool | None = None
    evidence_status: EvidenceStatus | None = None
    confidence: Confidence | None = None
    privacy_level: PrivacyLevel | None = None


class ParticipantOut(ApiModel):
    person_id: uuid.UUID
    role: ParticipantRole
    role_detail: str | None = None
    display_name: str | None = None


class EventOut(ApiModel):
    id: uuid.UUID
    type: EventType
    subtype: str | None
    date: dict[str, Any] | None
    date_display: str | None = None
    time: dict[str, Any] | None
    time_display: str | None = None
    timezone_id: str | None
    utc_offset_minutes: int | None
    place_id: uuid.UUID | None
    place_name: str | None = None
    place_as_recorded: str | None
    origin_place_id: uuid.UUID | None
    origin_place_name: str | None = None
    origin_place_as_recorded: str | None
    latitude: float | None
    longitude: float | None
    reason: str | None
    description: str | None
    is_preferred: bool
    evidence_status: EvidenceStatus
    confidence: Confidence
    participants: list[ParticipantOut] = []
    provenance: ProvenanceOut | None = None
    citation_count: int = 0
    redacted_fields: list[str] = []


# ---------- persons ----------
class PersonCreate(ApiModel):
    profile_status: ProfileStatus = ProfileStatus.UNKNOWN
    preferred_display_name: str | None = Field(default=None, max_length=300)
    sex_at_birth: SexAtBirth | None = None
    gender_identity: str | None = Field(default=None, max_length=100)
    primary_language: str | None = Field(default=None, max_length=16)
    scripts_used: list[str] = []
    privacy_level: PrivacyLevel | None = None
    occupation: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=20000)
    contact_info: str | None = Field(default=None, max_length=2000)
    residential_address: str | None = Field(default=None, max_length=2000)
    names: list[NameIn] = Field(min_length=1)
    birth: VitalIn | None = None
    death: VitalIn | None = None
    branch_ids: list[uuid.UUID] = []


class PersonUpdate(ApiModel):
    profile_status: ProfileStatus | None = None
    preferred_display_name: str | None = Field(default=None, max_length=300)
    sex_at_birth: SexAtBirth | None = None
    gender_identity: str | None = None
    primary_language: str | None = None
    scripts_used: list[str] | None = None
    occupation: str | None = None
    notes: str | None = None
    contact_info: str | None = None
    residential_address: str | None = None


class PrivacyUpdate(ApiModel):
    privacy_level: PrivacyLevel | None = None
    field_privacy: dict[str, PrivacyLevel | None] | None = None


class VitalSummary(ApiModel):
    event_id: uuid.UUID
    date: dict[str, Any] | None
    date_display: str | None
    time: dict[str, Any] | None = None
    time_display: str | None = None
    place_name: str | None = None
    place_as_recorded: str | None = None
    redacted_fields: list[str] = []


class PersonSummary(ApiModel):
    id: uuid.UUID
    display_name: str
    profile_status: ProfileStatus
    sex_at_birth: SexAtBirth | None
    birth_year: int | None = None
    death_year: int | None = None
    # Qualified dates (precision + calendar), already privacy-redacted; use these for display so
    # "c. 1840 (shaka)" is never shown as a bare "1840".
    birth_date: dict[str, Any] | None = None
    birth_display: str | None = None
    death_date: dict[str, Any] | None = None
    death_display: str | None = None
    is_minor: bool = False
    is_protected: bool = False
    privacy_level: PrivacyLevel | None = None


class PersonOut(PersonSummary):
    gender_identity: str | None = None
    primary_language: str | None = None
    scripts_used: list[str] = []
    occupation: str | None = None
    notes: str | None = None
    contact_info: str | None = None
    residential_address: str | None = None
    field_privacy: dict[str, str] | None = None
    claimed_by_user_id: uuid.UUID | None = None
    names: list[NameOut] = []
    birth: VitalSummary | None = None
    death: VitalSummary | None = None
    branch_ids: list[uuid.UUID] = []
    redacted_fields: list[str] = []
    can_edit: bool = False
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None


# ---------- relationships ----------
class RelationshipIn(ApiModel):
    person_a_id: uuid.UUID
    person_b_id: uuid.UUID
    type: RelationshipType
    subtype: str | None = Field(default=None, max_length=80)
    lineage: Lineage | None = None
    union_id: uuid.UUID | None = None
    start_date: GenealogicalDate | None = None
    end_date: GenealogicalDate | None = None
    union_order: int | None = Field(default=None, ge=1, le=50)
    legal_status: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=5000)
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN


class RelationshipUpdate(ApiModel):
    type: RelationshipType | None = None
    subtype: str | None = None
    lineage: Lineage | None = None
    union_id: uuid.UUID | None = None
    clear_union: bool = False
    start_date: GenealogicalDate | None = None
    end_date: GenealogicalDate | None = None
    union_order: int | None = None
    legal_status: str | None = None
    notes: str | None = None
    evidence_status: EvidenceStatus | None = None
    confidence: Confidence | None = None


class RelationshipOut(ApiModel):
    id: uuid.UUID
    person_a_id: uuid.UUID
    person_b_id: uuid.UUID
    type: RelationshipType
    subtype: str | None
    lineage: Lineage | None
    union_id: uuid.UUID | None
    start_date: dict[str, Any] | None
    end_date: dict[str, Any] | None
    union_order: int | None
    legal_status: str | None
    notes: str | None
    evidence_status: EvidenceStatus
    confidence: Confidence
    provenance: ProvenanceOut | None = None


class RelativeIn(ApiModel):
    """Convenience: link an existing or new person as parent/spouse/child/sibling of the anchor."""

    relation: str = Field(pattern="^(parent|spouse|child|sibling)$")
    relationship_type: RelationshipType | None = None
    existing_person_id: uuid.UUID | None = None
    new_person: PersonCreate | None = None
    union_id: uuid.UUID | None = None  # child: which union of the anchor the child belongs to
    other_parent_id: uuid.UUID | None = None  # child: link the child to the anchor's partner too
    start_date: GenealogicalDate | None = None
    subtype: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _one_person(self) -> RelativeIn:
        if (self.existing_person_id is None) == (self.new_person is None):
            raise ValueError("provide exactly one of existing_person_id or new_person")
        return self


class RelativeOut(ApiModel):
    person: PersonSummary
    relationships: list[RelationshipOut]


# ---------- family / traversal ----------
class RelatedPerson(ApiModel):
    person: PersonSummary | None  # None = hidden by privacy
    hidden: bool = False
    relationship_id: uuid.UUID | None = None
    relationship_type: RelationshipType | None = None
    lineage: Lineage | None = None
    subtype: str | None = None
    evidence_status: EvidenceStatus | None = None


class UnionOut(ApiModel):
    relationship: RelationshipOut
    partner: RelatedPerson
    children: list[RelatedPerson] = []


class SiblingOut(RelatedPerson):
    kind: str  # full | half | step | adoptive | explicit


class FamilyOut(ApiModel):
    person: PersonSummary
    parents: list[RelatedPerson]
    unions: list[UnionOut]
    other_children: list[RelatedPerson]
    siblings: list[SiblingOut]


class GraphNode(ApiModel):
    id: str
    person: PersonSummary | None
    hidden: bool = False
    generation: int
    partner: bool = False  # spouse/partner of a lineage member, not in the lineage itself


class GraphEdge(ApiModel):
    source: str  # parent
    target: str  # child
    type: RelationshipType
    lineage: Lineage | None = None


class GraphOut(ApiModel):
    root_id: uuid.UUID
    direction: str
    depth: int
    truncated: bool
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    unions: list[dict[str, str]] = []


class RelationshipPathOut(ApiModel):
    from_id: uuid.UUID
    to_id: uuid.UUID
    found: bool
    label: str | None = None
    chain: list[str] = []
    path: list[uuid.UUID | None] = []  # None = a person hidden from the viewer
    common_ancestor_ids: list[uuid.UUID] = []
    lineages: list[Lineage] = []
    explanation: str | None = None
