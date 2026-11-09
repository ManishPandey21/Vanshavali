from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.api.schemas import ApiModel, SharedPrivacyLevel
from app.core.dates import GenealogicalDate, GenealogicalTime
from app.models.enums import AstrologyProvenance, Confidence, EvidenceStatus
from app.modules.astrology import vocab
from app.modules.genealogy.schemas import ProvenanceOut


def _vocab(fn: Callable[[str], str | None], what: str, v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    canonical = fn(v)
    if canonical is None:
        raise ValueError(f"'{v}' is not a recognised {what}")
    return canonical


def _tz(v: str | None) -> str | None:
    if v is None:
        return v
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("unknown IANA time zone") from exc
    return v


class _AstrologyFields(ApiModel):
    nakshatra: str | None = Field(default=None, max_length=60)
    nakshatra_pada: int | None = Field(default=None, ge=1, le=4)
    rashi: str | None = Field(default=None, max_length=60)
    lagna: str | None = Field(default=None, max_length=60)
    tithi: str | None = Field(default=None, max_length=60)
    paksha: str | None = Field(default=None, max_length=20)
    yoga: str | None = Field(default=None, max_length=60)
    karana: str | None = Field(default=None, max_length=60)
    lunar_month: str | None = Field(default=None, max_length=60)
    ayanamsha: str | None = Field(default=None, max_length=60)
    calculation_system: str | None = Field(default=None, max_length=120)
    ephemeris_version: str | None = Field(default=None, max_length=80)
    chart_birth_date: GenealogicalDate | None = None
    chart_birth_time: GenealogicalTime | None = None
    chart_birth_place: str | None = Field(default=None, max_length=300)
    place_latitude: float | None = Field(default=None, ge=-90, le=90)
    place_longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone_id: str | None = Field(default=None, max_length=64)
    utc_offset_minutes: int | None = Field(default=None, ge=-14 * 60, le=14 * 60)
    calculation_timestamp: dt.datetime | None = None
    birth_event_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    privacy_level: SharedPrivacyLevel | None = None
    notes: str | None = Field(default=None, max_length=20000)

    @field_validator("nakshatra")
    @classmethod
    def _nakshatra(cls, v: str | None) -> str | None:
        return _vocab(vocab.canonical_nakshatra, "nakshatra", v)

    @field_validator("rashi")
    @classmethod
    def _rashi(cls, v: str | None) -> str | None:
        return _vocab(vocab.canonical_rashi, "rashi", v)

    @field_validator("lagna")
    @classmethod
    def _lagna(cls, v: str | None) -> str | None:
        return _vocab(vocab.canonical_rashi, "lagna (rising sign)", v)

    @field_validator("tithi")
    @classmethod
    def _tithi(cls, v: str | None) -> str | None:
        return _vocab(vocab.canonical_tithi, "tithi", v)

    @field_validator("paksha")
    @classmethod
    def _paksha(cls, v: str | None) -> str | None:
        return _vocab(vocab.canonical_paksha, "paksha (shukla or krishna)", v)

    @field_validator("ayanamsha")
    @classmethod
    def _ayanamsha(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return vocab.canonical_ayanamsha(v) or v.strip()  # uncommon systems are kept as written

    @field_validator("timezone_id")
    @classmethod
    def _timezone(cls, v: str | None) -> str | None:
        return _tz(v)


class AstrologyIn(_AstrologyFields):
    provenance_kind: AstrologyProvenance = AstrologyProvenance.ENTERED
    is_preferred: bool | None = None
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN

    @model_validator(mode="after")
    def _provenance(self) -> AstrologyIn:
        check_calculated(self.provenance_kind, self.calculation_system, self.ephemeris_version)
        return self


class AstrologyUpdate(_AstrologyFields):
    provenance_kind: AstrologyProvenance | None = None
    is_preferred: bool | None = None
    evidence_status: EvidenceStatus | None = None
    confidence: Confidence | None = None


def check_calculated(kind: Any, system: str | None, ephemeris: str | None) -> None:
    if kind == AstrologyProvenance.CALCULATED and not (system and ephemeris):
        raise ValueError(
            "calculated values must record calculation_system and ephemeris_version "
            "(the platform does not calculate charts itself)"
        )


class AstrologyOut(ApiModel):
    id: uuid.UUID
    person_id: uuid.UUID
    provenance_kind: AstrologyProvenance
    nakshatra: str | None
    nakshatra_pada: int | None
    rashi: str | None
    lagna: str | None
    tithi: str | None
    paksha: str | None
    yoga: str | None
    karana: str | None
    lunar_month: str | None
    ayanamsha: str | None
    calculation_system: str | None
    ephemeris_version: str | None
    chart_birth_date: dict[str, Any] | None
    chart_birth_date_display: str | None = None
    chart_birth_time: dict[str, Any] | None
    chart_birth_place: str | None
    place_latitude: float | None
    place_longitude: float | None
    timezone_id: str | None
    utc_offset_minutes: int | None
    calculation_timestamp: dt.datetime | None
    birth_event_id: uuid.UUID | None
    document_id: uuid.UUID | None
    is_preferred: bool
    privacy_level: SharedPrivacyLevel
    evidence_status: EvidenceStatus
    confidence: Confidence
    notes: str | None
    provenance: ProvenanceOut | None = None
    citation_count: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


class ClaimSource(ApiModel):
    source_id: uuid.UUID
    title: str
    source_type: str
    document_id: uuid.UUID | None = None


class BirthClaim(ApiModel):
    claim_type: str  # event | astrology_profile
    id: uuid.UUID
    is_preferred: bool
    date: dict[str, Any] | None = None
    date_display: str | None = None
    time: dict[str, Any] | None = None
    time_display: str | None = None
    place: str | None = None
    evidence_status: EvidenceStatus
    confidence: Confidence
    provenance: ProvenanceOut
    provenance_kind: AstrologyProvenance | None = None
    sources: list[ClaimSource] = []


class ConflictValue(ApiModel):
    claim_type: str
    claim_id: uuid.UUID
    value: str


class BirthConflict(ApiModel):
    field: str  # date | time | place
    message: str
    values: list[ConflictValue]


class BirthConflictsOut(ApiModel):
    person_id: uuid.UUID
    claims: list[BirthClaim]
    conflicts: list[BirthConflict]
    has_conflicts: bool
    withheld_fields: list[str] = []
