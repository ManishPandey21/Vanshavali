"""Granting and revoking platform capabilities (ADR-0028 §7). Operator CLI only.

Runs as the schema owner: ``platform_capability_grant`` is read-only to the application role, so
nothing reachable from the API can call these successfully. A capability belongs to one named person:
the account must have a verified email and two-step sign-in, and role or shared mailboxes are refused.
Every grant and revocation is audited without any tree.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.models import PlatformCapability, PlatformCapabilityGrant, User
from app.modules.identity.service import normalise_email


class GrantRefused(ValueError):
    """The CLI refuses this grant or revocation; the message says why."""


@dataclass(frozen=True)
class GrantRow:
    email: str
    holder_name: str
    capability: str
    granted_by: str
    granted_at: dt.datetime
    revoked_at: dt.datetime | None


def is_role_mailbox(email: str) -> bool:
    local = normalise_email(email).split("@", 1)[0].split("+", 1)[0]
    return local in {x.lower() for x in get_settings().platform_mailbox_denylist}


def _clean(value: str, what: str, limit: int) -> str:
    value = " ".join((value or "").split())
    if not value:
        raise GrantRefused(f"{what} is required")
    if len(value) > limit:
        raise GrantRefused(f"{what} is longer than {limit} characters")
    return value


def _user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == normalise_email(email)))
    if user is None:
        raise GrantRefused("no account with that email")
    return user


def _active(db: Session, user: User, capability: PlatformCapability) -> PlatformCapabilityGrant | None:
    return db.scalar(
        select(PlatformCapabilityGrant).where(
            PlatformCapabilityGrant.user_id == user.id,
            PlatformCapabilityGrant.capability == capability,
            PlatformCapabilityGrant.revoked_at.is_(None),
        )
    )


def grant(
    db: Session,
    *,
    email: str,
    capability: PlatformCapability,
    holder_name: str,
    reason: str,
    operator: str,
) -> PlatformCapabilityGrant:
    holder_name = _clean(holder_name, "the holder's name", 200)
    reason = _clean(reason, "a reason", 2000)
    operator = _clean(operator, "the operator's name", 200)
    if is_role_mailbox(email):
        raise GrantRefused("role or shared mailboxes cannot hold a capability; use a named person's account")
    user = _user(db, email)
    if not user.is_active:
        raise GrantRefused("the account is closed or disabled")
    if user.email_verified_at is None:
        raise GrantRefused("the account's email address is not verified")
    if user.mfa_enabled_at is None:
        raise GrantRefused("the account must turn on two-step sign-in (authenticator app) first")
    if _active(db, user, capability) is not None:
        raise GrantRefused("the account already holds this capability")
    row = PlatformCapabilityGrant(
        user_id=user.id, capability=capability, holder_name=holder_name, reason=reason, granted_by=operator
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action="platform.capability_granted",
        actor_user_id=None,
        target_type="user",
        target_id=user.id,
        details={"capability": capability.value, "grant_id": str(row.id), "operator": operator},
    )
    return row


def revoke(
    db: Session, *, email: str, capability: PlatformCapability, reason: str, operator: str
) -> PlatformCapabilityGrant:
    reason = _clean(reason, "a reason", 2000)
    operator = _clean(operator, "the operator's name", 200)
    user = _user(db, email)
    row = _active(db, user, capability)
    if row is None:
        raise GrantRefused("the account does not hold this capability")
    row.revoked_at = dt.datetime.now(dt.UTC)
    row.revoked_by = operator
    row.revoke_reason = reason
    audit.record(
        db,
        action="platform.capability_revoked",
        actor_user_id=None,
        target_type="user",
        target_id=user.id,
        details={"capability": capability.value, "grant_id": str(row.id), "operator": operator},
    )
    return row


def list_grants(db: Session, *, include_revoked: bool = False) -> list[GrantRow]:
    stmt = select(PlatformCapabilityGrant, User.email).join(User, User.id == PlatformCapabilityGrant.user_id)
    if not include_revoked:
        stmt = stmt.where(PlatformCapabilityGrant.revoked_at.is_(None))
    return [
        GrantRow(
            email=email,
            holder_name=g.holder_name,
            capability=PlatformCapability(g.capability).value,
            granted_by=g.granted_by,
            granted_at=g.granted_at,
            revoked_at=g.revoked_at,
        )
        for g, email in db.execute(stmt.order_by(PlatformCapabilityGrant.granted_at))
    ]
