"""Transliteration suggestion API schemas (ADR-0025 §4)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.modules.translit.engine import MAX_TEXT


class TransliterateIn(ApiModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    target_script: Literal["Deva", "Latn"]


class TransliterationCandidate(ApiModel):
    text: str
    # "lexicon": a reviewed name list; "rules": a possible spelling worked out by rules
    method: Literal["lexicon", "rules"]


class TransliterateOut(ApiModel):
    candidates: list[TransliterationCandidate]
    engine: str
    version: str
    lexicon_version: str
