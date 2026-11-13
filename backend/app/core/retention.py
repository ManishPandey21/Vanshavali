"""Retention of sign-in records and audit-log network identifiers (ADR-0033).

Entry points: ``python -m app.cli.maintenance purge-sign-in-records`` and ``scrub-audit-network``,
run daily. Both are idempotent and work as the restricted application role: ``user_session`` and
``audit_event`` are not row-level secured, and the audit trigger allows exactly the scrub below.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, or_, select, update

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models import AuditEvent, UserSession


def purge_ended_sessions(*, now: dt.datetime | None = None, older_than_days: int | None = None) -> int:
    """Delete sign-in records whose session ended (revoked or expired) more than the period ago."""
    now = now or dt.datetime.now(dt.UTC)
    days = get_settings().session_record_retention_days if older_than_days is None else older_than_days
    cutoff = now - dt.timedelta(days=days)
    ended_at = func.coalesce(
        UserSession.revoked_at, func.least(UserSession.idle_expires_at, UserSession.absolute_expires_at)
    )
    with get_sessionmaker()() as db:
        result = db.execute(delete(UserSession).where(ended_at < cutoff))
        db.commit()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


def scrub_audit_network(
    *, now: dt.datetime | None = None, older_than_days: int | None = None, batch_size: int = 5000
) -> int:
    """Erase ``ip`` and ``user_agent`` from audit entries older than the period, in batches.

    The change history (actor, action, target, summary, details, time) is kept. The database trigger
    refuses this for entries younger than its 365-day floor, whatever the setting says.
    """
    now = now or dt.datetime.now(dt.UTC)
    days = get_settings().audit_network_retention_days if older_than_days is None else older_than_days
    cutoff = now - dt.timedelta(days=days)
    total = 0
    maker = get_sessionmaker()
    while True:
        with maker() as db:
            ids = (
                select(AuditEvent.id)
                .where(
                    AuditEvent.created_at < cutoff,
                    or_(AuditEvent.ip.is_not(None), AuditEvent.user_agent.is_not(None)),
                )
                .limit(batch_size)
            )
            result = db.execute(
                update(AuditEvent)
                .where(AuditEvent.id.in_(ids.scalar_subquery()))
                .values(ip=None, user_agent=None)
                .execution_options(synchronize_session=False)
            )
            db.commit()
            n = int(result.rowcount or 0)  # type: ignore[attr-defined]
        total += n
        if n < batch_size:
            return total
