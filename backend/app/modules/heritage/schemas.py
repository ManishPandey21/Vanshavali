from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field, model_validator

from app.api.schemas import ApiModel, SharedPrivacyLevel
from app.models.enums import (
    AssertionSubject,
    Confidence,
    EvidenceStatus,
    HeritageAttribute,
    ReviewState,
    ValueStatus,
)
from app.modules.genealogy.schemas import ProvenanceOut


class AssertionIn(ApiModel):
    attribute: HeritageAttribute
    value_text: str | None = Field(default=None, max_length=2000)
    value_json: Any | None = None
    place_id: uuid.UUID | None = None
    value_status: ValueStatus = ValueStatus.KNOWN
    evidence_status: EvidenceStatus = EvidenceStatus.USER_ASSERTION
    confidence: Confidence = Confidence.UNKNOWN
    is_preferred: bool | None = None
    privacy_level: SharedPrivacyLevel | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _value(self) -> AssertionIn:
        has_value = (
            bool((self.value_text or "").strip()) or self.value_json is not None or self.place_id is not None
        )
        if self.value_status == ValueStatus.KNOWN and not has_value:
            raise ValueError("a known value needs value_text, value_json or place_id")
        if self.value_status != ValueStatus.KNOWN and has_value:
            raise ValueError(f"a '{self.value_status.value}' assertion must not carry a value")
        return self


class AssertionUpdate(ApiModel):
    value_text: str | None = None
    value_json: Any | None = None
    place_id: uuid.UUID | None = None
    value_status: ValueStatus | None = None
    evidence_status: EvidenceStatus | None = None
    confidence: Confidence | None = None
    is_preferred: bool | None = None
    privacy_level: SharedPrivacyLevel | None = None
    notes: str | None = None


class AssertionOut(ApiModel):
    review_state: ReviewState = ReviewState.UNREVIEWED  # family review (ADR-0021 §6)
    id: uuid.UUID
    subject_type: AssertionSubject
    person_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    attribute: str
    value_text: str | None
    value_json: Any | None
    place_id: uuid.UUID | None
    place_name: str | None = None
    value_status: ValueStatus
    evidence_status: EvidenceStatus
    confidence: Confidence
    is_preferred: bool
    privacy_level: SharedPrivacyLevel | None
    notes: str | None
    provenance: ProvenanceOut | None = None
    citation_count: int = 0
    created_by: uuid.UUID | None
    created_at: dt.datetime


class HeritageAttributeView(ApiModel):
    attribute: str
    preferred: AssertionOut | None
    alternatives: list[AssertionOut] = []
    disputed: bool = False


class HeritageProfileOut(ApiModel):
    subject_type: AssertionSubject
    subject_id: uuid.UUID
    attributes: list[HeritageAttributeView]
    withheld_attributes: list[str] = []
