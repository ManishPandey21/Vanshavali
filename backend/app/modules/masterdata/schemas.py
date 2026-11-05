from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field, field_validator

from app.api.schemas import ApiModel
from app.models.enums import VocabularyTermStatus


class VocabularyOut(ApiModel):
    key: str
    description: str
    version: int
    source: str | None = None
    licence: str | None = None
    allows_custom: bool
    term_count: int = 0


class VocabularyTermOut(ApiModel):
    code: str
    # the label in the requested language (falls back to English, then to any label)
    label: str
    labels: dict[str, str]
    aliases: list[str] = []
    parent_code: str | None = None
    attributes: dict[str, Any] = {}
    status: VocabularyTermStatus
    origin: Literal["global", "family"] = "global"
    # family entries only: the tree-scoped row (for future edit/remove)
    id: uuid.UUID | None = None


class VocabularyTermsOut(ApiModel):
    vocabulary: VocabularyOut
    items: list[VocabularyTermOut]


class TreeTermIn(ApiModel):
    label: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default=[], max_length=10)

    @field_validator("label")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("label must not be blank")
        return v

    @field_validator("aliases")
    @classmethod
    def _aliases(cls, v: list[str]) -> list[str]:
        out = [" ".join(a.split())[:200] for a in v]
        return [a for a in out if a]


class TreeTermOut(ApiModel):
    term: VocabularyTermOut
    # false when the label matched an existing entry, which is returned instead of a duplicate
    created: bool
