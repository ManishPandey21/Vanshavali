from __future__ import annotations

from typing import Any

from app.api.schemas import ApiModel


class VocabularyOut(ApiModel):
    code: str
    name: str
    description: str | None = None
    parent_vocabulary: str | None = None
    version: str
    source: str | None = None
    license: str | None = None
    term_count: int


class TermOut(ApiModel):
    code: str
    label: str
    labels: dict[str, str]
    aliases: list[str]
    tags: list[str]
    attributes: dict[str, Any]
    parent_code: str | None = None
    is_active: bool
