"""Property API schemas (PRS §17, §37; ADR-0010).

Every property response carries ``legal_notice``: these are genealogical/documentary records,
never legal title opinions.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.api.schemas import ApiModel, SharedPrivacyLevel
from app.core.dates import GenealogicalDate
from app.models.enums import (
    Confidence,
    DocumentCategory,
    DocumentLinkTarget,
    EventType,
    EvidenceStatus,
    HolderType,
    InterestStatus,
    InterestType,
    PrivacyLevel,
    PropertyClassification,
    PropertyEventType,
    PropertyType,
)
from app.modules.genealogy.schemas import PersonSummary, ProvenanceOut
from app.modules.property.units import AreaUnit

LEGAL_NOTICE = "Genealogical/documentary record only — not a legal title opinion."

ULPIN_RE = re.compile(r"^[A-Z0-9]{14}$")
_EXTRA_KEY_RE = re.compile(r"^[A-Za-z0-9_.\- ]{1,60}$")
MAX_SHARE_DENOMINATOR = 10**15  # fits BIGINT with room to spare


class LegalNoticed(ApiModel):
    legal_notice: str = LEGAL_NOTICE


# ---------------------------------------------------------------- properties
class PropertyIn(ApiModel):
    property_type: PropertyType
    classification: PropertyClassification = PropertyClassification.UNKNOWN
    display_name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    place_id: uuid.UUID | None = None
    address_text: str | None = Field(default=None, max_length=2000)
    current_status: str | None = Field(default=None, max_length=120)
    privacy_level: SharedPrivacyLevel = PrivacyLevel.PRIVATE_TREE_ADMINS


class PropertyUpdate(ApiModel):
    property_type: PropertyType | None = None
    classification: PropertyClassification | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    place_id: uuid.UUID | None = None
    address_text: str | None = Field(default=None, max_length=2000)
    current_status: str | None = Field(default=None, max_length=120)
    privacy_level: SharedPrivacyLevel | None = None

    @model_validator(mode="after")
    def _no_null_required(self) -> PropertyUpdate:
        for f in ("property_type", "classification", "display_name", "privacy_level"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


# ---------------------------------------------------------------- parcels
class ParcelFields(ApiModel):
    """Common Indian land-record identifiers plus ``extra_identifiers`` for state-specific keys."""

    place_id: uuid.UUID | None = None
    state_or_ut: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    tehsil_taluk: str | None = Field(default=None, max_length=100)
    village: str | None = Field(default=None, max_length=150)
    revenue_village_code: str | None = Field(default=None, max_length=60)
    survey_number: str | None = Field(default=None, max_length=60)
    khasra_or_gata_number: str | None = Field(default=None, max_length=60)
    khata_number: str | None = Field(default=None, max_length=60)
    khatauni_number: str | None = Field(default=None, max_length=60)
    patta_number: str | None = Field(default=None, max_length=60)
    plot_number: str | None = Field(default=None, max_length=60)
    subdivision_number: str | None = Field(default=None, max_length=60)
    ulpin: str | None = Field(default=None, description="Unique Land Parcel Identification Number (14 chars)")
    area: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    area_unit: AreaUnit | None = None
    land_use: str | None = Field(default=None, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    cadastral_map_reference: str | None = Field(default=None, max_length=200)
    state_portal_reference: str | None = Field(default=None, max_length=300)
    extra_identifiers: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=10000)

    @field_validator("ulpin")
    @classmethod
    def _ulpin(cls, v: str | None) -> str | None:
        if v is None:
            return None
        norm = v.strip().upper()
        if not ULPIN_RE.fullmatch(norm):
            raise ValueError("ULPIN must be exactly 14 alphanumeric characters")
        return norm

    @field_validator("extra_identifiers")
    @classmethod
    def _extra(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        if len(v) > 50:
            raise ValueError("at most 50 extra identifiers")
        for k, val in v.items():
            if not _EXTRA_KEY_RE.fullmatch(k):
                raise ValueError(f"invalid identifier key {k!r} (letters, digits, space, _ . - ; ≤60 chars)")
            if val is not None and not isinstance(val, str | int | bool):
                raise ValueError(f"identifier {k!r} must be a string, integer, boolean or null")
            if isinstance(val, str) and len(val) > 300:
                raise ValueError(f"identifier {k!r} is longer than 300 characters")
        return v


class NewParcelFields(ParcelFields):
    @model_validator(mode="after")
    def _area_pair(self) -> NewParcelFields:
        if self.area is not None and self.area_unit is None:
            raise ValueError("area_unit is required when area is given")
        return self


class ParcelIn(NewParcelFields):
    parent_parcel_id: uuid.UUID | None = None


class ParcelUpdate(ParcelFields):
    parent_parcel_id: uuid.UUID | None = None


class ParcelRef(ApiModel):
    id: uuid.UUID
    label: str
    parent_parcel_id: uuid.UUID | None = None


class ParcelOut(LegalNoticed):
    id: uuid.UUID
    property_id: uuid.UUID
    parent_parcel_id: uuid.UUID | None
    label: str
    place_id: uuid.UUID | None
    state_or_ut: str | None
    district: str | None
    tehsil_taluk: str | None
    village: str | None
    revenue_village_code: str | None
    survey_number: str | None
    khasra_or_gata_number: str | None
    khata_number: str | None
    khatauni_number: str | None
    patta_number: str | None
    plot_number: str | None
    subdivision_number: str | None
    ulpin: str | None
    area: Decimal | None
    area_unit: str | None
    area_sq_m: Decimal | None = None
    area_conversion_note: str | None = None
    land_use: str | None
    latitude: float | None
    longitude: float | None
    cadastral_map_reference: str | None
    state_portal_reference: str | None
    extra_identifiers: dict[str, Any]
    notes: str | None
    child_count: int = 0
    provenance: ProvenanceOut | None = None
    created_at: dt.datetime


class SubdivisionChildIn(NewParcelFields):
    pass


class SubdivideIn(ApiModel):
    children: list[SubdivisionChildIn] = Field(min_length=1, max_length=200)
    date: GenealogicalDate | None = None
    description: str | None = Field(default=None, max_length=5000)
    record_event: bool = True
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION


class ParcelNode(ApiModel):
    parcel: ParcelRef
    depth: int


class ParcelLineageOut(LegalNoticed):
    parcel: ParcelOut
    ancestors: list[ParcelRef] = []  # nearest parent first
    siblings: list[ParcelRef] = []  # other parcels sharing the same parent
    descendants: list[ParcelNode] = []


# ---------------------------------------------------------------- interests
class HolderIn(ApiModel):
    holder_type: HolderType
    holder_person_id: uuid.UUID | None = None
    holder_branch_id: uuid.UUID | None = None
    holder_name: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _holder(self) -> HolderIn:
        t = self.holder_type
        if t == HolderType.PERSON:
            if self.holder_person_id is None or self.holder_branch_id is not None:
                raise ValueError("a person holder needs holder_person_id (and no holder_branch_id)")
        elif t == HolderType.FAMILY_BRANCH:
            if self.holder_branch_id is None or self.holder_person_id is not None:
                raise ValueError("a family_branch holder needs holder_branch_id (and no holder_person_id)")
        else:
            if self.holder_person_id is not None or self.holder_branch_id is not None:
                raise ValueError(f"a {t.value} holder is identified by holder_name only")
            if t in (HolderType.TRUST, HolderType.ENTITY) and not (self.holder_name or "").strip():
                raise ValueError(f"a {t.value} holder needs holder_name")
        return self


class ShareIn(ApiModel):
    share_numerator: int = Field(default=1, ge=0, le=MAX_SHARE_DENOMINATOR)
    share_denominator: int = Field(default=1, ge=1, le=MAX_SHARE_DENOMINATOR)

    @model_validator(mode="after")
    def _share(self) -> ShareIn:
        if self.share_numerator > self.share_denominator:
            raise ValueError("a share cannot exceed the whole (numerator ≤ denominator)")
        return self


class InterestIn(HolderIn, ShareIn):
    parcel_id: uuid.UUID | None = None
    interest_type: InterestType = InterestType.OWNER
    valid_from: GenealogicalDate | None = None
    valid_to: GenealogicalDate | None = None
    status: InterestStatus = InterestStatus.ASSERTED
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN
    notes: str | None = Field(default=None, max_length=5000)


class InterestUpdate(ApiModel):
    parcel_id: uuid.UUID | None = None
    holder_name: str | None = Field(default=None, max_length=300)
    interest_type: InterestType | None = None
    share_numerator: int | None = Field(default=None, ge=0, le=MAX_SHARE_DENOMINATOR)
    share_denominator: int | None = Field(default=None, ge=1, le=MAX_SHARE_DENOMINATOR)
    valid_from: GenealogicalDate | None = None
    valid_to: GenealogicalDate | None = None
    status: InterestStatus | None = None
    evidence_status: EvidenceStatus | None = None
    confidence: Confidence | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _no_null_required(self) -> InterestUpdate:
        for f in (
            "interest_type",
            "share_numerator",
            "share_denominator",
            "status",
            "evidence_status",
            "confidence",
        ):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class InterestEndIn(ApiModel):
    valid_to: GenealogicalDate
    status: Literal["transferred", "relinquished"] = "transferred"
    notes: str | None = Field(default=None, max_length=5000)


class HolderOut(ApiModel):
    type: HolderType
    hidden: bool = False
    person_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    name: str | None = None
    display_name: str | None = None
    person: PersonSummary | None = None


class InterestOut(LegalNoticed):
    id: uuid.UUID
    property_id: uuid.UUID
    parcel_id: uuid.UUID | None
    holder: HolderOut
    interest_type: InterestType
    share_numerator: int
    share_denominator: int
    share: str  # exact, reduced "n/d"
    share_percent: float  # display only — never used for arithmetic
    valid_from: dict[str, Any] | None
    valid_from_display: str | None = None
    valid_to: dict[str, Any] | None
    valid_to_display: str | None = None
    status: InterestStatus
    is_current: bool
    counts_toward_whole: bool  # documented owner/co_owner: subject to the ≤ 1 invariant
    evidence_status: EvidenceStatus
    confidence: Confidence
    created_by_event_id: uuid.UUID | None
    ended_by_event_id: uuid.UUID | None
    notes: str | None
    citation_count: int = 0
    provenance: ProvenanceOut | None = None


# ---------------------------------------------------------------- events
class EventInterestIn(InterestIn):
    """An interest created by a property event; ``valid_from`` defaults to the event date."""

    status: InterestStatus = InterestStatus.DOCUMENTED


class PropertyEventIn(ApiModel):
    type: PropertyEventType
    date: GenealogicalDate | None = None
    description: str | None = Field(default=None, max_length=5000)
    registration_number: str | None = Field(default=None, max_length=120)
    registration_date: GenealogicalDate | None = None
    mutation_number: str | None = Field(default=None, max_length=120)
    consideration: str | None = Field(default=None, max_length=200)
    related_event_id: uuid.UUID | None = None
    parcel_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    ends_interest_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    end_status: Literal["transferred", "relinquished"] | None = None
    creates_interests: list[EventInterestIn] = Field(default_factory=list, max_length=500)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN


class PropertyEventUpdate(ApiModel):
    description: str | None = Field(default=None, max_length=5000)
    registration_number: str | None = Field(default=None, max_length=120)
    registration_date: GenealogicalDate | None = None
    mutation_number: str | None = Field(default=None, max_length=120)
    consideration: str | None = Field(default=None, max_length=200)
    related_event_id: uuid.UUID | None = None
    evidence_status: EvidenceStatus | None = None
    confidence: Confidence | None = None

    @model_validator(mode="after")
    def _no_null_required(self) -> PropertyEventUpdate:
        for f in ("evidence_status", "confidence"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class AllocationIn(HolderIn, ShareIn):
    parcel_id: uuid.UUID | None = None
    interest_type: InterestType | None = None  # default: owner for a whole share, else co_owner


class PartitionIn(ApiModel):
    date: GenealogicalDate
    description: str | None = Field(default=None, max_length=5000)
    registration_number: str | None = Field(default=None, max_length=120)
    registration_date: GenealogicalDate | None = None
    related_event_id: uuid.UUID | None = None
    parcel_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    allocations: list[AllocationIn] = Field(min_length=1, max_length=500)
    ends_interest_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    allow_partial: bool = Field(
        default=False,
        description="Accept allocations that do not add up to the ended shares (e.g. a partial deed).",
    )
    status: InterestStatus = InterestStatus.DOCUMENTED
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN


class DocumentRef(ApiModel):
    """Linked document metadata only — never file bytes or storage keys."""

    id: uuid.UUID
    title: str
    category: DocumentCategory
    privacy_level: SharedPrivacyLevel
    linked_to: DocumentLinkTarget
    linked_id: uuid.UUID
    note: str | None = None


class RelatedEventOut(ApiModel):
    id: uuid.UUID
    hidden: bool = False
    type: EventType | None = None
    date_display: str | None = None
    principal: PersonSummary | None = None


class PropertyEventOut(LegalNoticed):
    id: uuid.UUID
    property_id: uuid.UUID
    type: PropertyEventType
    date: dict[str, Any] | None
    date_display: str | None = None
    date_sort_from: dt.date | None
    description: str | None
    registration_number: str | None
    registration_date: dict[str, Any] | None
    mutation_number: str | None
    consideration: str | None
    related_event: RelatedEventOut | None = None
    parcels: list[ParcelRef] = []
    interests_ended: list[InterestOut] = []
    interests_created: list[InterestOut] = []
    documents: list[DocumentRef] = []
    hidden_document_count: int = 0
    citation_count: int = 0
    evidence_status: EvidenceStatus
    confidence: Confidence
    provenance: ProvenanceOut | None = None
    created_at: dt.datetime


# ---------------------------------------------------------------- property outputs
class PropertyOut(LegalNoticed):
    id: uuid.UUID
    property_type: PropertyType
    classification: PropertyClassification
    display_name: str
    description: str | None
    place_id: uuid.UUID | None
    place_name: str | None = None
    address_text: str | None
    current_status: str | None
    privacy_level: SharedPrivacyLevel
    parcel_count: int = 0
    can_edit: bool = False
    created_at: dt.datetime
    updated_at: dt.datetime


class PropertyCounts(ApiModel):
    parcels: int = 0
    events: int = 0
    interests: int = 0
    current_interests: int = 0
    documents: int = 0
    citations: int = 0


class PropertyDetailOut(PropertyOut):
    parcels: list[ParcelOut] = []
    current_interests: list[InterestOut] = []
    documented_share_total: str = "0/1"  # current property-wide documented ownership
    has_overlapping_claims: bool = False
    counts: PropertyCounts = PropertyCounts()


class HoldersAtOut(ApiModel):
    at: dt.date
    interests: list[InterestOut] = []
    # property-wide owner/co_owner shares recorded as documented (or documented-then-ended) at ``at``
    documented_share_total: str = "0/1"
    # any active ownership claims (whatever their status) adding up to more than the whole
    has_overlapping_claims: bool = False


class TimelineOut(LegalNoticed):
    property: PropertyOut
    events: list[PropertyEventOut] = []
    current_interests: list[InterestOut] = []
    holders_at: HoldersAtOut | None = None
    documents: list[DocumentRef] = []  # linked to the property or its parcels (not to an event)
    hidden_document_count: int = 0


class LineageChain(ApiModel):
    interest: InterestOut
    steps: list[PropertyEventOut] = []  # most recent first, back to the earliest recorded event
    origin_interests: list[InterestOut] = []  # the earliest recorded interests in this chain
    first_acquirers: list[HolderOut] = []


class TransferOut(ApiModel):
    event: PropertyEventOut
    from_holders: list[HolderOut] = []
    to_holders: list[HolderOut] = []


class ParcelGroupOut(ApiModel):
    parent: ParcelRef
    children: list[ParcelRef] = []


class LineageOut(LegalNoticed):
    property: PropertyOut
    chains: list[LineageChain] = []
    first_acquirers: list[HolderOut] = []
    first_acquisition_events: list[PropertyEventOut] = []
    partitions: list[PropertyEventOut] = []
    transfers_out: list[TransferOut] = []  # relinquishments, sales, gifts: who gave up what
    parcel_groups: list[ParcelGroupOut] = []


class PersonPropertyInterestOut(ApiModel):
    property: PropertyOut
    interest: InterestOut


class PersonPropertyInterestsOut(LegalNoticed):
    person_id: uuid.UUID
    items: list[PersonPropertyInterestOut] = []


class SubdivideOut(LegalNoticed):
    parent: ParcelOut
    children: list[ParcelOut]
    event: PropertyEventOut | None = None
    warnings: list[str] = []
