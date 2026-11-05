"""Request/response schemas of the Super Admin master-data console (ADR-0025).

Input models forbid unknown fields, so a request cannot set ``managed_by``, ``revision``, authorship
or anything else the server owns (mass assignment).
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.api.schemas import ApiModel
from app.models.enums import (
    VocabularyChangeAction,
    VocabularyChangeStatus,
    VocabularyTermManagedBy,
    VocabularyTermStatus,
)

CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,79}$")
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
ATTR_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,79}$")
REQUIRED_LANGS = ("en", "hi")


def _clean(v: str) -> str:
    return " ".join(v.split())


def _code(v: str | None) -> str | None:
    if v is None:
        return None
    if not CODE_RE.match(v):
        raise ValueError("use lower-case letters, digits and underscores (at most 80)")
    return v


class _In(ApiModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")


class VocabularyTermFieldsIn(_In):
    """Every editable field of a global term. An update sends the complete new set."""

    labels: dict[str, str] = Field(description="Label per language tag; English and Hindi are required")
    aliases: list[str] = Field(default=[], max_length=30)
    scope: list[str] = Field(default=[], max_length=20, description="Regions or traditions (slugs)")
    parent_code: str | None = None
    attributes: dict[str, str | int | bool] = Field(default={}, max_length=20)
    source_url: str | None = Field(default=None, max_length=500)
    status: Literal["draft", "reviewed"] = "draft"
    sort_order: int = Field(default=0, ge=0, le=100_000)

    @field_validator("labels")
    @classmethod
    def _labels(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 12:
            raise ValueError("at most 12 languages")
        out: dict[str, str] = {}
        for lang, label in v.items():
            if not LANG_RE.match(lang):
                raise ValueError(f"bad language tag {lang!r}")
            text = _clean(label)
            if len(text) > 200:
                raise ValueError(f"the {lang} label is longer than 200 characters")
            if text:
                out[lang] = text
        missing = [lang for lang in REQUIRED_LANGS if lang not in out]
        if missing:
            raise ValueError(f"a label is required in: {', '.join(missing)}")
        return out

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for a in v:
            text = _clean(a)
            if len(text) > 200:
                raise ValueError("an alias is longer than 200 characters")
            if text and text not in out:
                out.append(text)
        return out

    @field_validator("scope")
    @classmethod
    def _scope(cls, v: list[str]) -> list[str]:
        for s in v:
            if not SCOPE_RE.match(s):
                raise ValueError(f"bad scope {s!r}: use lower-case slugs")
        return list(dict.fromkeys(v))

    @field_validator("parent_code")
    @classmethod
    def _parent(cls, v: str | None) -> str | None:
        return _code(v)

    @field_validator("attributes")
    @classmethod
    def _attributes(cls, v: dict[str, str | int | bool]) -> dict[str, str | int | bool]:
        for k, val in v.items():
            if not ATTR_KEY_RE.match(k):
                raise ValueError(f"bad attribute name {k!r}")
            if isinstance(val, str) and len(val) > 200:
                raise ValueError(f"attribute {k} is longer than 200 characters")
        return v

    @field_validator("source_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        # only web links: never javascript:, data: or other schemes that would run when clicked
        if not re.match(r"^https?://[^\s<>\"']+$", v, re.IGNORECASE):
            raise ValueError("the source link must start with https:// or http://")
        return v


class MasterDataChangeIn(_In):
    action: VocabularyChangeAction
    code: str = Field(description="Code of the term to create or change")
    # the term revision the editor showed (required for update/retire/reactivate): a change prepared
    # against an older revision is refused with 409 instead of silently overwriting newer data
    base_revision: int | None = Field(default=None, ge=1)
    term: VocabularyTermFieldsIn | None = Field(
        default=None, description="create/update: the complete new term"
    )
    successor_code: str | None = Field(default=None, description="retire: the term that replaces it")
    reactivate_as: Literal["draft", "reviewed"] = "draft"
    reason: str = Field(min_length=3, max_length=2000, description="Why the change is needed")
    source_reference: str | None = Field(default=None, max_length=1000)
    allow_similar: bool = Field(default=False, description="create/update: the label resembles another term")
    publish: bool = Field(default=False, description="Publish at once instead of saving a draft")

    @field_validator("code", "successor_code")
    @classmethod
    def _codes(cls, v: str | None) -> str | None:
        return _code(v)

    @field_validator("reason", "source_reference")
    @classmethod
    def _text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def _shape(self) -> MasterDataChangeIn:
        if not self.reason:
            raise ValueError("a reason is required")
        needs_term = self.action in (VocabularyChangeAction.CREATE, VocabularyChangeAction.UPDATE)
        if needs_term and self.term is None:
            raise ValueError(f"{self.action.value} needs the term fields")
        if not needs_term and self.term is not None:
            raise ValueError(f"{self.action.value} takes no term fields")
        if self.action != VocabularyChangeAction.CREATE and self.base_revision is None:
            raise ValueError("base_revision is required")
        if self.action == VocabularyChangeAction.CREATE and self.base_revision is not None:
            raise ValueError("a new term has no base revision")
        if self.successor_code is not None and self.action != VocabularyChangeAction.RETIRE:
            raise ValueError("only a retirement takes a successor")
        return self


class MasterDataDecisionIn(_In):
    note: str | None = Field(default=None, max_length=2000)


class MasterDataRejectIn(_In):
    note: str = Field(min_length=3, max_length=2000)


class VocabularyDuplicateCheckIn(_In):
    labels: dict[str, str] = Field(default={}, max_length=12)
    aliases: list[str] = Field(default=[], max_length=30)
    exclude_code: str | None = None


class AdminVocabularyOut(ApiModel):
    key: str
    description: str
    category: str
    version: int
    revision: int
    source: str | None = None
    licence: str | None = None
    allows_custom: bool
    fixed_membership: bool
    counts: dict[str, int] = Field(description="Terms per status")
    pending_changes: int = 0


class AdminTermOut(ApiModel):
    code: str
    labels: dict[str, str]
    aliases: list[str]
    scope: list[str]
    parent_code: str | None
    attributes: dict[str, Any]
    source_url: str | None
    status: VocabularyTermStatus
    sort_order: int
    successor_code: str | None
    managed_by: VocabularyTermManagedBy
    revision: int
    updated_at: dt.datetime
    pending_change_id: uuid.UUID | None = None


class AdminTermPage(ApiModel):
    vocabulary: AdminVocabularyOut
    items: list[AdminTermOut]
    total: int
    next_cursor: str | None = None


class MasterDataChangeOut(ApiModel):
    id: uuid.UUID
    vocabulary_key: str
    term_code: str
    action: VocabularyChangeAction
    status: VocabularyChangeStatus
    base_revision: int | None
    previous: dict[str, Any]
    proposed: dict[str, Any]
    reason: str
    source_reference: str | None
    proposed_by_name: str | None = None
    proposed_by_me: bool = False
    proposed_at: dt.datetime
    decided_by_name: str | None = None
    decided_at: dt.datetime | None
    decision_note: str | None
    # pending only: the term moved on since the change was prepared (publishing would be refused)
    stale: bool = False


class MasterDataChangePage(ApiModel):
    items: list[MasterDataChangeOut]
    next_cursor: str | None = None


class AdminTermDetailOut(ApiModel):
    term: AdminTermOut
    history: list[MasterDataChangeOut]


class VocabularyDuplicateOut(ApiModel):
    code: str
    label: str
    status: VocabularyTermStatus
    matched: str
