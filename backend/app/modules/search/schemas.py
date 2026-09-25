from __future__ import annotations

import uuid

from app.api.schemas import ApiModel
from app.modules.genealogy.schemas import PersonSummary


class SearchHit(ApiModel):
    kind: str  # person | place | document | property | branch | household
    id: uuid.UUID
    title: str
    subtitle: str | None = None
    score: float
    match_tier: str
    match_reason: str
    person: PersonSummary | None = None


class SearchOut(ApiModel):
    query: str
    hits: list[SearchHit]


class DuplicateCandidate(ApiModel):
    person_a: PersonSummary
    person_b: PersonSummary
    score: float
    outcome: str  # possible | probable
    reasons: list[str]
