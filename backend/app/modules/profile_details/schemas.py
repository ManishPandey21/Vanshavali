from __future__ import annotations

import datetime as dt
import re
import uuid

from pydantic import Field, field_validator, model_validator

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate
from app.models.enums import AddressPurpose, AddressStatus, ContactKind


class AddressPayload(ApiModel):
    building: str | None = Field(default=None, max_length=300)
    street: str | None = Field(default=None, max_length=500)
    landmark: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=1000)
    as_recorded: str | None = Field(default=None, max_length=2000)
    gram_panchayat: str | None = Field(default=None, max_length=200)
    post_office: str | None = Field(default=None, max_length=200)


class AddressIn(AddressPayload):
    purpose: AddressPurpose
    status: AddressStatus
    is_primary_current: bool = False
    place_id: uuid.UUID | None = None
    locality: str | None = Field(default=None, max_length=200)
    sub_district: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=24)
    valid_from: GenealogicalDate | None = None
    valid_until: GenealogicalDate | None = None
    idempotency_key: str | None = Field(default=None, max_length=100)

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @model_validator(mode="after")
    def primary_is_current(self):  # type: ignore[no-untyped-def]
        if self.is_primary_current and self.status != AddressStatus.CURRENT:
            raise ValueError("a primary address must be current")
        identifying = (
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
        if not any(value and str(value).strip() for value in identifying):
            raise ValueError("enter at least one place or postal address detail")
        return self


class AddressUpdate(AddressPayload):
    revision: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)
    purpose: AddressPurpose | None = None
    status: AddressStatus | None = None
    is_primary_current: bool | None = None
    place_id: uuid.UUID | None = None
    locality: str | None = Field(default=None, max_length=200)
    sub_district: str | None = Field(default=None, max_length=160)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=24)
    valid_from: GenealogicalDate | None = None
    valid_until: GenealogicalDate | None = None


class AddressOut(AddressPayload):
    id: uuid.UUID
    person_id: uuid.UUID
    purpose: AddressPurpose
    status: AddressStatus
    is_primary_current: bool
    place_id: uuid.UUID | None
    locality: str | None
    sub_district: str | None
    district: str | None
    state: str | None
    country_code: str | None
    postal_code: str | None
    valid_from: dict | None
    valid_until: dict | None
    revision: int
    source: str
    created_at: dt.datetime
    updated_at: dt.datetime


class MoveAddressIn(ApiModel):
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=100)
    valid_until: GenealogicalDate | None = None
    reason: str | None = Field(default="Moved", max_length=500)
    new_address: AddressIn


class MoveAddressOut(ApiModel):
    former_address: AddressOut
    new_address: AddressOut


class RevisionSnapshot(ApiModel):
    revision: int
    operation: str
    reason: str | None
    before: dict | None
    after: dict | None
    created_at: dt.datetime


class ContactIn(ApiModel):
    kind: ContactKind
    value: str = Field(min_length=1, max_length=2000)
    purpose: str | None = Field(default=None, max_length=80)
    language: str | None = Field(default=None, max_length=16)
    is_preferred: bool = False
    copied_from_contact_id: uuid.UUID | None = None
    copied_from_revision: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_value(self):  # type: ignore[no-untyped-def]
        validate_contact(self.kind, self.value)
        if (self.copied_from_contact_id is None) != (self.copied_from_revision is None):
            raise ValueError("copied contact id and revision must be supplied together")
        if self.copied_from_contact_id is not None and self.kind != ContactKind.WHATSAPP:
            raise ValueError("only WhatsApp can be copied from a mobile contact")
        return self


class ContactUpdate(ApiModel):
    revision: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)
    value: str | None = Field(default=None, min_length=1, max_length=2000)
    purpose: str | None = Field(default=None, max_length=80)
    language: str | None = Field(default=None, max_length=16)
    is_preferred: bool | None = None
    copied_from_contact_id: uuid.UUID | None = None
    copied_from_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def copy_reference_is_complete(self):  # type: ignore[no-untyped-def]
        supplied = {"copied_from_contact_id", "copied_from_revision"} & self.model_fields_set
        if supplied and supplied != {"copied_from_contact_id", "copied_from_revision"}:
            raise ValueError("copied contact id and revision must be supplied together")
        if supplied and (self.copied_from_contact_id is None) != (self.copied_from_revision is None):
            raise ValueError("copied contact id and revision must both be set or cleared")
        return self


class ContactOut(ApiModel):
    id: uuid.UUID
    person_id: uuid.UUID
    kind: ContactKind
    hint: str
    purpose: str | None
    language: str | None
    is_preferred: bool
    copied_from_contact_id: uuid.UUID | None
    copy_outdated: bool
    revision: int
    source: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ContactReveal(ApiModel):
    id: uuid.UUID
    value: str
    profile_url: str | None = None


_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE = re.compile(r"^\+[1-9][0-9]{7,14}$")
_TELEGRAM_USERNAME = r"[A-Za-z][A-Za-z0-9_]{4,31}"
_INSTAGRAM_USERNAME = r"(?!.*\.\.)[A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?"


def validate_contact(kind: ContactKind, value: str) -> None:
    if kind == ContactKind.EMAIL and not _EMAIL.fullmatch(value):
        raise ValueError("enter a valid email address")
    if kind in {ContactKind.MOBILE, ContactKind.WHATSAPP} and not _PHONE.fullmatch(value):
        raise ValueError("enter an international phone number such as +919876543210")
    if kind == ContactKind.TELEGRAM and not (
        re.fullmatch(rf"@{_TELEGRAM_USERNAME}", value)
        or re.fullmatch(rf"https://t\.me/{_TELEGRAM_USERNAME}", value)
    ):
        raise ValueError("enter a Telegram @handle or https://t.me link")
    if kind == ContactKind.INSTAGRAM and not (
        re.fullmatch(rf"@{_INSTAGRAM_USERNAME}", value)
        or re.fullmatch(rf"https://(?:www\.)?instagram\.com/{_INSTAGRAM_USERNAME}/?", value)
    ):
        raise ValueError("enter an Instagram @handle or fixed https://instagram.com link")
