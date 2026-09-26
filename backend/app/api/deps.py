"""Shared FastAPI dependencies: authentication, CSRF, tree context."""

from __future__ import annotations

import datetime as dt
import hmac
import uuid
from typing import Annotated

from fastapi import Depends, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.context import RequestInfo, TreeContext, load_public_context, load_tree_context
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError, Unauthorized
from app.core.security import token_hash
from app.models import User, UserSession

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

DbDep = Annotated[Session, Depends(get_db)]


def request_info(request: Request) -> RequestInfo:
    client = request.client.host if request.client else None
    return RequestInfo(ip=client, user_agent=request.headers.get("user-agent"))


def _load_session(db: Session, request: Request) -> UserSession | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    if sess is None or sess.revoked_at is not None:
        return None
    now = dt.datetime.now(dt.UTC)
    if sess.idle_expires_at < now or sess.absolute_expires_at < now:
        return None
    return sess


def verify_csrf(request: Request) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    s = get_settings()
    cookie = request.cookies.get(s.csrf_cookie_name)
    header = request.headers.get(s.csrf_header_name)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise ApiError("CSRF token missing or invalid", code="csrf_failed", status_code=403)


def optional_user(request: Request, db: DbDep) -> User | None:
    sess = _load_session(db, request)
    if sess is None:
        return None
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active or user.email_verified_at is None:
        return None  # unverified accounts never get a session; this is defence in depth
    now = dt.datetime.now(dt.UTC)
    if (now - sess.last_seen_at).total_seconds() > 300:
        sess.last_seen_at = now
        sess.idle_expires_at = min(
            now + dt.timedelta(days=get_settings().session_idle_days), sess.absolute_expires_at
        )
    request.state.session_id = sess.id
    return user


def current_user(request: Request, user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise Unauthorized()
    verify_csrf(request)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def tree_context(
    request: Request,
    db: DbDep,
    user: CurrentUser,
    tree_id: Annotated[uuid.UUID, Path()],
) -> TreeContext:
    return load_tree_context(db, tree_id, user, request_info(request))


TreeCtx = Annotated[TreeContext, Depends(tree_context)]


def public_context(request: Request, db: DbDep, slug: Annotated[str, Path()]) -> TreeContext:
    return load_public_context(db, slug, request_info(request))


PublicCtx = Annotated[TreeContext, Depends(public_context)]
