from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field, field_validator

from app.api.schemas import ApiModel

LANG = r"^[a-z]{2,3}$"
REGION = r"^[a-z_]{1,40}$"
# a chain pattern, optionally narrowed to one age order: "father.brother", "father.brother:elder"
OVERRIDE_PATTERN = r"^[a-z_]+(\.[a-z_]+){0,5}(:(elder|younger))?$"


class KinshipTermOut(ApiModel):
    """A relationship word for the chain of a ``/relationship-path`` answer (ADR-0026 §6)."""

    pack: str | None = None  # None for a family's own word without a pack
    lang: str
    region: str | None = None
    term: str
    transliteration: str | None = None
    # both words when the choice depends on something not recorded (age order, speaker's sex)
    alternatives: list[str] = []
    basis: Literal["family_confirmed", "birth_dates", "unknown"] | None = None
    review_status: Literal["reviewed", "unreviewed", "family"]
    family_word: bool = False
    pack_term: str | None = None  # the pack's own word, shown beside a family's word
    description: str | None = None  # a literal reading of the chain in this language


class KinshipPackOut(ApiModel):
    key: str
    lang: str
    region: str
    name: dict[str, str]
    status: Literal["draft", "reviewed"]
    in_use: bool = False
    reviewer: str | None = None
    reviewed_on: str | None = None
    source: str
    licence: str
    term_count: int


class KinshipPreferenceIn(ApiModel):
    lang: str | None = Field(default=None, pattern=LANG)  # null = follow the tree, then the UI
    region: str | None = Field(default=None, pattern=REGION)


class KinshipPreferenceOut(ApiModel):
    lang: str | None
    region: str | None


class KinshipOverrideIn(ApiModel):
    pattern: str = Field(pattern=OVERRIDE_PATTERN, max_length=200)
    lang: str = Field(pattern=LANG)
    region: str | None = Field(default=None, pattern=REGION)
    word: str = Field(min_length=1, max_length=120)
    branch_id: uuid.UUID | None = None  # None = the whole tree

    @field_validator("word")
    @classmethod
    def _word(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v or any(ord(c) < 32 for c in v) or "<" in v or ">" in v:
            raise ValueError("a word is plain text")
        return v


class KinshipOverrideOut(ApiModel):
    id: uuid.UUID
    pattern: str
    lang: str
    region: str | None
    word: str
    branch_id: uuid.UUID | None
    revision: int
    updated_at: dt.datetime
