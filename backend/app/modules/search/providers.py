"""Pluggable search providers so other modules (documents, property) can contribute hits.

A provider is ``fn(ctx, query, limit) -> list[SearchHit]`` and MUST apply its own authorisation.
"""

from __future__ import annotations

from collections.abc import Callable

from app.authz.context import TreeContext

Provider = Callable[[TreeContext, str, int], list]
_PROVIDERS: dict[str, Provider] = {}


def register(kind: str, fn: Provider) -> None:
    _PROVIDERS[kind] = fn


def registered() -> dict[str, Provider]:
    return dict(_PROVIDERS)
