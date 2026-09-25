from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.models.enums import JobStatus
from app.modules.genealogy.schemas import PersonSummary


class AttachDecision(ApiModel):
    attach: uuid.UUID


Decision = Literal["create", "skip"] | AttachDecision


class CommitIn(ApiModel):
    decisions: dict[str, Decision] = Field(default_factory=dict)


class ImportJobSummary(ApiModel):
    id: uuid.UUID
    status: JobStatus
    original_filename: str | None
    detected_version: str | None
    detected_encoding: str | None
    counts: dict[str, int] = {}
    error: str | None = None
    created_at: dt.datetime
    committed_at: dt.datetime | None = None


class DuplicateMatch(ApiModel):
    person: PersonSummary
    score: float
    outcome: str  # possible | probable
    reasons: list[str]


class StagedPersonPreview(ApiModel):
    xref: str
    display_name: str
    sex: str | None = None
    profile_status: str
    birth: str | None = None
    death: str | None = None
    names: list[str] = []
    event_count: int = 0
    heritage: list[str] = []  # attribute names only
    has_astrology: bool = False
    preserved_tags: list[str] = []
    duplicates: list[DuplicateMatch] = []


class ImportJobOut(ImportJobSummary):
    report: dict[str, Any] = {}
    preview: list[StagedPersonPreview] = []
    preview_total: int = 0
    commit_result: dict[str, Any] | None = None
