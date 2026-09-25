"""Shared API schema helpers."""

from __future__ import annotations

import base64
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


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
