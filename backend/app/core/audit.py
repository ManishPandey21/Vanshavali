"""Audit logging helper (PRS §34). Never put sensitive values into ``details``."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None,
    tree_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        action=action,
        actor_user_id=actor_user_id,
        tree_id=tree_id,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        details=details or {},
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
    )
    db.add(ev)
    return ev


def record_detached(**kwargs: Any) -> None:
    """Record an audit event in its own transaction (survives the caller's rollback, e.g. failed logins)."""
    from app.core.db import get_sessionmaker

    with get_sessionmaker()() as db:
        record(db, **kwargs)
        db.commit()


def log(
    ctx: Any,
    action: str,
    *,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Audit an action performed within a TreeContext."""
    return record(
        ctx.db,
        action=action,
        actor_user_id=ctx.user_id,
        tree_id=ctx.tree_id,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        details=details,
        ip=ctx.request.ip,
        user_agent=ctx.request.user_agent,
    )
