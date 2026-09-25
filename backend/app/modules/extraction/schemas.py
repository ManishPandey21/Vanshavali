from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field, model_validator

from app.api.schemas import ApiModel
from app.models.enums import ProcessingStatus, ProposalStatus


class ProposalOut(ApiModel):
    id: uuid.UUID
    document_id: uuid.UUID
    subject_person_id: uuid.UUID | None
    subject_property_id: uuid.UUID | None
    extractor: str
    extractor_version: str
    engine: str | None
    field: str
    label: str
    proposed_value: Any
    display_value: str
    confidence: float
    source_location: dict[str, Any] | None
    status: ProposalStatus
    final_value: Any | None
    reviewed_by: uuid.UUID | None
    reviewed_at: dt.datetime | None
    review_note: str | None
    applied_target_type: str | None
    applied_target_id: uuid.UUID | None
    created_at: dt.datetime
    value_label: str = (
        "extracted"  # extracted | source-verified (accepted as read) | user-confirmed (edited) | rejected
    )


class ReviewIn(ApiModel):
    action: Literal["accept", "edit", "reject"]
    value: Any | None = None
    note: str | None = Field(default=None, max_length=2000)
    target_person_id: uuid.UUID | None = None
    target_property_id: uuid.UUID | None = None
    target_parcel_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _value(self) -> ReviewIn:
        if self.action == "edit" and self.value is None:
            raise ValueError("an edit needs a value")
        if self.action != "edit" and self.value is not None:
            raise ValueError("value is only used with action 'edit'")
        return self


class OcrLineOut(ApiModel):
    line_no: int
    text: str
    confidence: float


class OcrPageOut(ApiModel):
    page: int
    lines: list[OcrLineOut]


class OcrTextOut(ApiModel):
    document_id: uuid.UUID
    status: ProcessingStatus
    engine: str | None
    confidence: float | None = None
    text: str | None = None
    pages: list[OcrPageOut] = []
    note: str = "Machine-read text. It may contain errors and is not a verified transcription."


class ReprocessOut(ApiModel):
    document_id: uuid.UUID
    preview_status: ProcessingStatus
    ocr_status: ProcessingStatus
    extraction_status: ProcessingStatus
    pending_proposals: int
