"""Platform capabilities (ADR-0028 §7): what a named administrator may do outside any family tree.

Kept apart from the tree permission matrix on purpose. A capability comes only from an active row in
``platform_capability_grant`` (written by the operator CLI, read-only to the application role);
``is_system_admin`` grants nothing here. Nothing in this module reads or grants tree data: a
capability holder has no tree access beyond their own memberships (ADR-0028 §8).

Checks, in order, on every request (nothing is cached):

1. the console is switched on and the user holds the capability, else **404** (the console is not
   revealed to anyone else);
2. the request's session was opened with password + TOTP within the last
   ``platform_session_mfa_max_age_hours``, and after two-step sign-in was (last) turned on, else
   **403** ``admin_mfa_required``;
3. for writes, a TOTP step-up within ``platform_step_up_max_age_minutes``, else **403**
   ``admin_step_up_required``.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError, NotFound
from app.models import PlatformCapability, PlatformCapabilityGrant, User, UserSession

__all__ = [
    "PlatformCapability",
    "capabilities",
    "require_platform",
    "session_mfa_valid_until",
    "step_up_valid_until",
]


def capabilities(db: Session, user: User) -> frozenset[PlatformCapability]:
    """The platform capabilities ``user`` holds right now (active grants of an active account)."""
    if not user.is_active:
        return frozenset()
    rows = db.scalars(
        select(PlatformCapabilityGrant.capability).where(
            PlatformCapabilityGrant.user_id == user.id, PlatformCapabilityGrant.revoked_at.is_(None)
        )
    )
    return frozenset(PlatformCapability(c) for c in rows)


def session_mfa_valid_until(user: User, sess: UserSession) -> dt.datetime | None:
    """When this session stops counting as two-step verified, or None if it never did / no longer does.

    A session counts only if it was opened with TOTP *after* two-step sign-in was turned on: turning
    it off and on again (a new secret) disqualifies every older session.
    """
    verified, enabled = sess.mfa_verified_at, user.mfa_enabled_at
    if verified is None or enabled is None or verified < enabled:
        return None
    return verified + dt.timedelta(hours=get_settings().platform_session_mfa_max_age_hours)


def step_up_valid_until(sess: UserSession) -> dt.datetime | None:
    if sess.mfa_step_up_at is None:
        return None
    return sess.mfa_step_up_at + dt.timedelta(minutes=get_settings().platform_step_up_max_age_minutes)


def require_platform(
    db: Session,
    user: User,
    sess: UserSession | None,
    capability: PlatformCapability,
    *,
    write: bool,
    now: dt.datetime | None = None,
) -> None:
    """Refuse unless ``user`` holds ``capability`` on a fresh two-step session (and step-up, for writes)."""
    if capability is PlatformCapability.MASTER_DATA_ADMIN and not get_settings().masterdata_console_enabled:
        raise NotFound("Not found")
    if capability not in capabilities(db, user):
        raise NotFound("Not found")
    now = now or dt.datetime.now(dt.UTC)
    until = session_mfa_valid_until(user, sess) if sess is not None and sess.user_id == user.id else None
    if until is None or until <= now:
        raise ApiError(
            "Sign in again with your password and authenticator code to use the administration console.",
            code="admin_mfa_required",
            status_code=403,
        )
    if write:
        step_up = step_up_valid_until(sess) if sess is not None else None
        if step_up is None or step_up <= now:
            raise ApiError(
                "Enter a fresh code from your authenticator app to make this change.",
                code="admin_step_up_required",
                status_code=403,
            )
