from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field, model_validator

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate
from app.models.enums import AddressPurpose, AddressReuseMode, AddressStatus, RecordPrivacyLevel
from app.modules.profile_details.schemas import AddressOut, AddressPayload


class FamilyAddressSnapshot(AddressPayload):
    place_id: uuid.UUID | None = None
    locality: str | None = Field(default=None, max_length=200)
    sub_district: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def has_identity(self):  # type: ignore[no-untyped-def]
        fields = (
            self.place_id,
            self.as_recorded,
            self.building,
            self.street,
            self.locality,
            self.sub_district,
            self.district,
            self.state,
            self.postal_code,
            self.gram_panchayat,
            self.post_office,
        )
        if not any(value and str(value).strip() for value in fields):
            raise ValueError("enter at least one place or postal address detail")
        if self.country_code:
            self.country_code = self.country_code.upper()
        return self


class FamilyAddressCreateIn(ApiModel):
    label: str = Field(min_length=1, max_length=200)
    privacy_level: RecordPrivacyLevel = RecordPrivacyLevel.TREE_MEMBERS
    audience_branch_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    household_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    ancestral_assertion_id: uuid.UUID | None = None
    source_person_id: uuid.UUID | None = None
    source_person_address_id: uuid.UUID | None = None
    snapshot: FamilyAddressSnapshot | None = None
    idempotency_key: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def exactly_one_source(self):  # type: ignore[no-untyped-def]
        person_copy = self.source_person_id is not None or self.source_person_address_id is not None
        if person_copy and (self.source_person_id is None or self.source_person_address_id is None):
            raise ValueError("source person and address must be supplied together")
        if sum((self.snapshot is not None, self.ancestral_assertion_id is not None, person_copy)) != 1:
            raise ValueError("choose one snapshot, ancestral assertion, or copied person address")
        if self.privacy_level == RecordPrivacyLevel.FAMILY_BRANCH and self.audience_branch_id is None:
            raise ValueError("selected branch is required for branch-only visibility")
        return self


class FamilyAddressVersionIn(ApiModel):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
    snapshot: FamilyAddressSnapshot


class FamilyAddressOut(ApiModel):
    id: uuid.UUID
    label: str
    privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    household_id: uuid.UUID | None
    property_id: uuid.UUID | None
    place_id: uuid.UUID | None
    ancestral_assertion_id: uuid.UUID | None
    current_version: int
    revision: int
    sharing_released: bool
    snapshot: FamilyAddressSnapshot
    created_at: dt.datetime
    updated_at: dt.datetime


class FamilyAddressSourceOut(ApiModel):
    source_kind: Literal["family_address", "ancestral_assertion", "my_address"]
    source_id: uuid.UUID
    version: int | None = None
    label: str
    group: Literal["Recent", "Family", "Branch", "Ancestral", "My addresses"]
    snapshot: FamilyAddressSnapshot
    link_allowed: bool


class AddressReuseIn(ApiModel):
    source_kind: Literal["family_address", "ancestral_assertion", "my_address"]
    source_id: uuid.UUID
    source_version: int | None = Field(default=None, ge=1)
    mode: AddressReuseMode
    purpose: AddressPurpose
    status: AddressStatus
    is_primary_current: bool = False
    valid_from: GenealogicalDate | None = None
    valid_until: GenealogicalDate | None = None
    idempotency_key: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def source_supports_mode(self):  # type: ignore[no-untyped-def]
        if self.source_kind != "family_address" and self.mode == AddressReuseMode.LINK:
            raise ValueError("only a versioned family address can be linked")
        return self


class AffectedAddressOut(ApiModel):
    person_id: uuid.UUID
    person_name: str
    address_id: uuid.UUID
    pinned_version: int


class ReleaseConsentIn(ApiModel):
    source_version: int = Field(ge=1)
    destination_family_address_id: uuid.UUID
    permitted_privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None = None
    purpose: str = Field(min_length=1, max_length=300)
    notice_version: str = Field(min_length=1, max_length=80)


class ReleaseConsentOut(ApiModel):
    id: uuid.UUID
    source_version_id: uuid.UUID
    destination_family_address_id: uuid.UUID
    permitted_privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None
    purpose: str
    notice_version: str
    granted_at: dt.datetime
    withdrawn_at: dt.datetime | None


class ReleaseReaderOut(ApiModel):
    membership_id: uuid.UUID
    display_name: str


class ReleasePreviewOut(ApiModel):
    additional_readers: list[ReleaseReaderOut]
    required_controller_membership_ids: list[uuid.UUID]


class ActivateSharingIn(ApiModel):
    revision: int = Field(ge=1)
    consent_id: uuid.UUID


class FamilyAddressGrantIn(ApiModel):
    membership_id: uuid.UUID
    expires_at: dt.datetime | None = None


class FamilyAddressGrantOut(ApiModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    expires_at: dt.datetime | None
    granted_at: dt.datetime


class ReuseResult(ApiModel):
    address: AddressOut
