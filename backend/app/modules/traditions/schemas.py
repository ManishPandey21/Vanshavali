from __future__ import annotations

import datetime as dt
import re
import unicodedata
import uuid

from pydantic import Field, field_validator

from app.api.schemas import ApiModel
from app.models.enums import RecordPrivacyLevel, ReviewState, TraditionKind, TraditionLinkTarget

MAX_BODY = 50_000
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(v: str) -> str:
    """Plain text with light formatting (line breaks, lists, **bold**): normalised, no control
    characters. It is never stored or rendered as HTML."""
    v = unicodedata.normalize("NFC", v.replace("\r\n", "\n").replace("\r", "\n"))
    v = _CONTROL.sub("", v)
    return "\n".join(line.rstrip() for line in v.split("\n")).strip()


class TraditionLinkIn(ApiModel):
    target_type: TraditionLinkTarget
    target_id: uuid.UUID


class _TraditionFields(ApiModel):
    @field_validator("title", check_fields=False)
    @classmethod
    def _title(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = " ".join(clean_text(v).split())
        if not v:
            raise ValueError("a title is required")
        return v

    @field_validator("body", check_fields=False)
    @classmethod
    def _body(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = clean_text(v)
        if len(v) > MAX_BODY:
            raise ValueError(f"at most {MAX_BODY} characters")
        return v


class TraditionEntryIn(_TraditionFields):
    kind: TraditionKind
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=MAX_BODY + 5_000)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    script: str | None = Field(default=None, pattern=r"^[A-Z][a-z]{3}$")
    branch_id: uuid.UUID | None = None
    privacy_level: RecordPrivacyLevel = RecordPrivacyLevel.TREE_MEMBERS
    links: list[TraditionLinkIn] = Field(default=[], max_length=50)


class TraditionEntryUpdate(_TraditionFields):
    kind: TraditionKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, max_length=MAX_BODY + 5_000)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    script: str | None = Field(default=None, pattern=r"^[A-Z][a-z]{3}$")
    branch_id: uuid.UUID | None = None
    privacy_level: RecordPrivacyLevel | None = None
    links: list[TraditionLinkIn] | None = Field(default=None, max_length=50)


class TraditionLinkOut(ApiModel):
    target_type: TraditionLinkTarget
    target_id: uuid.UUID
    label: str


class TraditionSummaryOut(ApiModel):
    id: uuid.UUID
    kind: TraditionKind
    title: str
    excerpt: str
    language: str | None
    script: str | None
    branch_id: uuid.UUID | None
    privacy_level: RecordPrivacyLevel
    author_name: str | None
    updated_at: dt.datetime


class TraditionOut(TraditionSummaryOut):
    body: str
    links: list[TraditionLinkOut] = []
    revision: int
    review_state: ReviewState
    created_at: dt.datetime
    created_by: uuid.UUID | None
    # what the reader may do now (the server checks again on every write)
    can_edit: bool = False
    edit_needs_review: bool = False
    can_withdraw: bool = False
    is_owner: bool = False
    can_edit_sharing: bool = False  # may open Visibility & Sharing (ADR-0027)


class TraditionsOut(ApiModel):
    items: list[TraditionSummaryOut]
    next_cursor: str | None = None


class TraditionRevisionOut(ApiModel):
    id: uuid.UUID
    revision: int
    op: str
    created_at: dt.datetime
    actor_name: str | None
    reviewer_name: str | None
    proposal_id: uuid.UUID | None
    changed: list[str]
    before: dict[str, object]
    after: dict[str, object]
