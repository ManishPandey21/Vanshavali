"""Shared API schema helpers."""

from __future__ import annotations

import base64
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.models.enums import RECORD_ONLY_LEVELS, PrivacyLevel

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


def _not_record_only(level: PrivacyLevel) -> PrivacyLevel:
    if level in RECORD_ONLY_LEVELS:
        raise ValueError("'Only me' and 'Selected members' are for documents and traditions only")
    return level


# A privacy level for anything that is not a shareable record: people, field groups, events,
# sources, properties, places, the tree default (ADR-0027 §1: these reject the record-only levels).
SharedPrivacyLevel = Annotated[PrivacyLevel, AfterValidator(_not_record_only)]


class Page(ApiModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        if raw.startswith("o:"):
            return max(0, int(raw[2:]))
    except (ValueError, UnicodeDecodeError):
        pass
    return 0


class Message(ApiModel):
    message: str
