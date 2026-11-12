"""Public, aggregate landing-page impact statistics.

Only active family-tree *counts* are disclosed. Optional visitor measurement uses a
random first-party, HttpOnly browser cookie and Redis HyperLogLog: no IP, user agent,
profile, family identifier, or request-level visitor history is retained.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import secrets
from functools import lru_cache

import redis
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DbDep
from app.core.config import get_settings
from app.models import Tree

router = APIRouter(prefix="/public", tags=["public"])
log = logging.getLogger(__name__)

_COOKIE = "vsh_impact_visitor"
_COOKIE_MAX_AGE = 90 * 86400
_DAYS = 30
_KEY_PREFIX = "vsh:impact:unique:"
_KEY_TTL = 35 * 86400


class SiteImpactOut(BaseModel):
    family_trees: int = Field(ge=0)
    # Null means measurement is disabled or temporarily unavailable, never zero.
    unique_visitors_30d: int | None = Field(default=None, ge=0)


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=0.5
    )


def _signed_cookie(token: str, key: str) -> str:
    signature = hmac.new(key.encode(), f"visitor:{token}".encode(), hashlib.sha256).hexdigest()
    return f"{token}.{signature}"


def _visitor_token(cookie: str | None, key: str) -> tuple[str, bool]:
    if cookie:
        token, dot, signature = cookie.partition(".")
        if (
            dot
            and 32 <= len(token) <= 64
            and all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in token)
            and hmac.compare_digest(_signed_cookie(token, key).split(".")[1], signature)
        ):
            return token, False
    return secrets.token_urlsafe(24), True


def _record_visitor(request: Request, response: Response) -> int:
    settings = get_settings()
    token, new = _visitor_token(request.cookies.get(_COOKIE), settings.signing_key)
    # The cookie is never sent to the datastore. This digest remains stable across
    # days so Redis PFCOUNT can estimate distinct browsers over a 30-day window.
    visitor_hash = hmac.new(
        settings.signing_key.encode(), f"impact:{token}".encode(), hashlib.sha256
    ).hexdigest()
    today = dt.datetime.now(dt.UTC).date()
    keys = [
        f"{_KEY_PREFIX}{(today - dt.timedelta(days=i)).isoformat()}"
        for i in range(_DAYS)
    ]
    r = _redis_client()
    pipe = r.pipeline()
    pipe.pfadd(keys[0], visitor_hash)
    pipe.expire(keys[0], _KEY_TTL)
    pipe.execute()
    count = int(r.pfcount(*keys))
    if new:
        response.set_cookie(
            _COOKIE,
            _signed_cookie(token, settings.signing_key),
            max_age=_COOKIE_MAX_AGE,
            secure=settings.env == "production",
            httponly=True,
            samesite="lax",
            path=f"{settings.api_prefix}/public",
        )
    return count


@router.get("/site-impact", response_model=SiteImpactOut)
def site_impact(request: Request, response: Response, db: DbDep) -> SiteImpactOut:
    """Aggregate family trees and opt-in 30-day browser visitors for the landing page."""
    family_trees = int(
        db.scalar(select(func.count(Tree.id)).where(Tree.deleted_at.is_(None))) or 0
    )
    visitors: int | None = None
    if get_settings().visitor_stats_enabled:
        try:
            visitors = _record_visitor(request, response)
        except (redis.RedisError, OSError):
            # Never turn a Redis outage into a broken landing page or a false zero.
            log.warning("Visitor count temporarily unavailable", exc_info=True)
    return SiteImpactOut(family_trees=family_trees, unique_visitors_30d=visitors)
