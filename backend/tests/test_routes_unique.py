"""No two API routes share a method and path.

A later router silently shadows an earlier one with the same path (found when review
notifications briefly took over the reminders' GET /trees/{tree_id}/notifications).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from typing import Any

from fastapi.routing import APIRoute

from app.api.router import api_router


def _routes(router: Any, prefix: str = "") -> Iterator[APIRoute | tuple[str, str]]:
    for r in router.routes:
        if isinstance(r, APIRoute):
            for method in r.methods:
                yield (method, prefix + r.path)
        elif hasattr(r, "original_router"):  # FastAPI >= 0.140 wraps included routers
            ctx = getattr(r, "include_context", None)
            yield from _routes(r.original_router, prefix + (getattr(ctx, "prefix", "") or ""))


def test_the_walker_sees_every_module() -> None:
    paths = {p for _, p in _routes(api_router)}  # type: ignore[misc]
    assert "/trees/{tree_id}/notifications" in paths and "/trees/{tree_id}/inbox" in paths
    assert len(paths) > 150


def test_no_two_routes_share_a_method_and_path() -> None:
    seen = Counter(_routes(api_router))
    clashes = sorted(k for k, n in seen.items() if n > 1)  # type: ignore[type-var]
    assert clashes == [], f"routes registered twice: {clashes}"
