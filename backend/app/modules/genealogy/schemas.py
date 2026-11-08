from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate, GenealogicalTime
from app.models.enums import (
    CATEGORY_EVENT_TYPE,
    Confidence,
    EventSignificance,
    EventType,
    EvidenceStatus,
    GeoLevel,
    LifeEventCategory,
    Lineage,
    LocationPrecision,
    NameType,
    ParticipantRole,
    PlaceType,
    PrivacyLevel,
    ProfileStatus,
    ProvenanceOrigin,
    RelationshipType,
    ReviewState,
    SexAtBirth,
)
from app.modules.geo.schemas import PlaceLgdNote
from app.modules.kinship.schemas import KinshipTermOut


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
    # set when the code was picked from the LGD cascade (ADR-0019 §4); the server then checks the
    # code and records the snapshot. Without it, lgd_code is free text as before.
    lgd_level: GeoLevel | None = None
    locality: str | None = Field(default=None, max_length=200)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    map_label: str | None = Field(default=None, max_length=200)
    geo_note: str | None = Field(default=None, max_length=2000)
    location_precision: LocationPrecision | None = None
    geo_confidence: Confidence = Confidence.UNKNOWN
    coordinate_privacy: PrivacyLevel | None = None

    @model_validator(mode="after")
    def _pair(self) -> PlaceIn:
        _check_pair(self.latitude, self.longitude)
        return self


def _check_pair(lat: float | None, lng: float | None) -> None:
    if (lat is None) != (lng is None):
        raise ValueError("latitude and longitude must be given together")


class PlaceUpdate(ApiModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=300)
    place_type: PlaceType | None = None
    parent_place_id: uuid.UUID | None = None
    local_names: list[PlaceName] | None = None
    historical_names: list[PlaceName] | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geocoding_source: str | None = None
    lgd_code: str | None = Field(default=None, max_length=40)
    lgd_level: GeoLevel | None = None
    # the user accepts the unit as LGD lists it now: re-link to the active snapshot (clears the note)
    lgd_accept_current: bool = False
    locality: str | None = Field(default=None, max_length=200)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    map_label: str | None = Field(default=None, max_length=200)
    geo_note: str | None = Field(default=None, max_length=2000)
    location_precision: LocationPrecision | None = None
    geo_confidence: Confidence | None = None
    coordinate_privacy: PrivacyLevel | None = None


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
    lgd_level: GeoLevel | None = None
    lgd_snapshot_id: str | None = None
    # the linked unit changed in LGD since it was picked; informational, the place is unchanged
    lgd_note: PlaceLgdNote | None = None
    locality: str | None = None
    district: str | None = None
    state: str | None = None
    country: str | None = None
    map_label: str | None = None
    geo_note: str | None = None
    location_precision: LocationPrecision = LocationPrecision.UNKNOWN
    geo_confidence: Confidence = Confidence.UNKNOWN
    coordinate_privacy: PrivacyLevel | None = None
    # true when the viewer gets rounded coordinates (coordinate_privacy above their access)
    coordinates_coarsened: bool = False
    hierarchy: list[str] = []


# ---------- names ----------
class NameSuggestionIn(ApiModel):
    """Marks a name the user accepted from a transliteration suggestion (ADR-0025 §5).

    The server, not the client, records the provenance: origin ``calculation``, its own engine
    version and the user as the one who confirmed it.
    """

    method: Literal["lexicon", "rules"]


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
    suggestion: NameSuggestionIn | None = None

    @model_validator(mode="after")
    def _suggested_names_are_transliterations(self) -> NameIn:
        # a suggested spelling is another form of a typed name: never the preferred one, never evidence
        if self.suggestion is not None:
            if self.type != NameType.TRANSLITERATION:
                raise ValueError("a suggested spelling can only be saved as a transliteration")
            if self.is_preferred:
                raise ValueError("a suggested spelling cannot be the preferred name")
            if self.evidence_status != EvidenceStatus.USER_ASSERTION:
                raise ValueError("a suggested spelling is not evidence")
        return self

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
    # family review (ADR-0021 §6): unreviewed, family_reviewed or contested; not evidence
    review_state: ReviewState = ReviewState.UNREVIEWED
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
    location_precision: LocationPrecision | None = None
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
    # Either a structural type or a life-event category (which implies a type) is required.
    type: EventType | None = None
    category: LifeEventCategory | None = None
    title: str | None = Field(default=None, max_length=300)
    significance: EventSignificance = EventSignificance.STANDARD
    subtype: str | None = Field(default=None, max_length=80)
    participants: list[ParticipantIn] = Field(min_length=1)
    origin_place_id: uuid.UUID | None = None
    origin_place_as_recorded: str | None = Field(default=None, max_length=500)
    reason: str | None = Field(default=None, max_length=5000)
    is_preferred: bool = True
    privacy_level: PrivacyLevel | None = None

    @model_validator(mode="after")
    def _type_or_category(self) -> EventIn:
        if self.type is None:
            if self.category is None:
                raise ValueError("an event needs a type or a life-event category")
            self.type = CATEGORY_EVENT_TYPE[self.category]
        _check_pair(self.latitude, self.longitude)
        return self


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
    title: str | None = Field(default=None, max_length=300)
    category: LifeEventCategory | None = None
    significance: EventSignificance | None = None
    location_precision: LocationPrecision | None = None


class ParticipantOut(ApiModel):
    person_id: uuid.UUID
    role: ParticipantRole
    role_detail: str | None = None
    display_name: str | None = None


class EventOut(ApiModel):
    # family review (ADR-0021 §6): unreviewed, family_reviewed or contested; not evidence
    review_state: ReviewState = ReviewState.UNREVIEWED
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
    title: str | None = None
    category: LifeEventCategory | None = None
    significance: EventSignificance = EventSignificance.STANDARD
    location_precision: LocationPrecision | None = None
    privacy_level: PrivacyLevel | None = None
    media_count: int = 0  # album photos the viewer may see
    cover_document_id: uuid.UUID | None = None


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
    # created by Smart Add as "unknown for now" (ADR-0020 §4): records origin, never cleared by a name
    is_provisional: bool = False
    # for provisional people only: needs_details (no name), unverified (a relationship has no
    # supporting evidence) or verified. A name alone never makes a person verified.
    provisional_state: Literal["needs_details", "unverified", "verified"] | None = None


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
    # family review (ADR-0021 §6): unreviewed, family_reviewed or contested; not evidence
    review_state: ReviewState = ReviewState.UNREVIEWED
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
    relationship: RelationshipOut | None  # None when the partner is hidden from the viewer
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


class AgeOrderOut(ApiModel):
    """Whether the person reached by a sibling word in ``chain`` is older or younger than the person
    that word starts from (e.g. the uncle vs the *father*), and on what basis (ADR-0020 §5)."""

    chain_index: int
    person_id: uuid.UUID
    relative_to_id: uuid.UUID
    order: Literal["elder", "younger", "unknown"]
    # family_confirmed wins over birth_dates; unknown when dates overlap, are missing or conflict
    basis: Literal["family_confirmed", "birth_dates", "unknown"]
    record_id: uuid.UUID | None = None  # the family-confirmed record, for correcting it
    dates_disagree: bool = False  # a family-confirmed order the viewer's visible birth dates contradict


class RelativeAgeOrderIn(ApiModel):
    person_id: uuid.UUID
    relative_to_id: uuid.UUID
    order: Literal["elder", "younger"]


class RelativeAgeOrderOut(ApiModel):
    id: uuid.UUID
    elder_person_id: uuid.UUID
    younger_person_id: uuid.UUID


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
    age_orders: list[AgeOrderOut] = []
    # the reader's relationship word in their chosen language and region (ADR-0026 §6)
    terms: list[KinshipTermOut] = []
    # the age order an age-dependent word depends on (asked once, in any language), if any
    age_decision: AgeOrderOut | None = None
