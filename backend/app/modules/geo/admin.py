"""Snapshot review and activation for system admins (ADR-0019 §3, ADR-0026).

validated → approved (one admin) → active (a *different* admin; the previous active snapshot of the
source becomes superseded). A superseded snapshot can be re-activated (rollback, one admin).
Staged, validated, failed and approved snapshots can be discarded; active and superseded never.
Every decision is audited with ids and labels only.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AdminContext
from app.core import audit
from app.core.errors import ApiError, Conflict, NotFound
from app.models import GeoSnapshot, User
from app.models.enums import GeoSnapshotStatus
from app.modules.geo.schemas import GeoSnapshotOut

S = GeoSnapshotStatus
DISCARDABLE = {S.STAGED, S.VALIDATED, S.FAILED, S.APPROVED}


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(wanted)))}


def _out(db: Session, s: GeoSnapshot, me: uuid.UUID | None) -> GeoSnapshotOut:
    names = _names(db, {s.approved_by, s.activated_by})
    return GeoSnapshotOut(
        id=s.id,
        source=s.source,
        label=s.label,
        status=s.status,
        source_url=s.source_url,
        downloaded_on=s.downloaded_on,
        licence=s.licence,
        attribution=s.attribution,
        files=s.files,
        report=s.report,
        staged_by=s.staged_by,
        approved_by_name=names.get(s.approved_by) if s.approved_by else None,
        approved_at=s.approved_at,
        activated_by_name=names.get(s.activated_by) if s.activated_by else None,
        activated_at=s.activated_at,
        created_at=s.created_at,
        approved_by_me=me is not None and s.approved_by == me,
    )


def list_snapshots(ctx: AdminContext) -> list[GeoSnapshotOut]:
    rows = ctx.db.scalars(select(GeoSnapshot).order_by(GeoSnapshot.source, GeoSnapshot.created_at.desc()))
    return [_out(ctx.db, s, ctx.user_id) for s in rows]


def _locked(db: Session, snapshot_id: uuid.UUID) -> GeoSnapshot:
    s = db.get(GeoSnapshot, snapshot_id, with_for_update=True)
    if s is None:
        raise NotFound("Snapshot not found")
    return s


def get_snapshot(ctx: AdminContext, snapshot_id: uuid.UUID) -> GeoSnapshotOut:
    s = ctx.db.get(GeoSnapshot, snapshot_id)
    if s is None:
        raise NotFound("Snapshot not found")
    return _out(ctx.db, s, ctx.user_id)


def _audit(
    db: Session, action: str, s: GeoSnapshot, *, actor: uuid.UUID | None, reason: str, **extra: str
) -> None:
    audit.record(
        db,
        action=action,
        actor_user_id=actor,
        target_type="geo_snapshot",
        target_id=s.id,
        details={"source": s.source.value, "label": s.label, "reason": reason[:500], **extra},
    )


def approve(ctx: AdminContext, snapshot_id: uuid.UUID, reason: str) -> GeoSnapshotOut:
    s = _locked(ctx.db, snapshot_id)
    if s.status != S.VALIDATED:
        raise Conflict("Only a validated snapshot can be approved", code="snapshot_not_validated")
    s.status = S.APPROVED
    s.approved_by = ctx.user_id
    s.approved_at = dt.datetime.now(dt.UTC)
    _audit(ctx.db, "geo.snapshot_approved", s, actor=ctx.user_id, reason=reason)
    return _out(ctx.db, s, ctx.user_id)


def _make_active(db: Session, s: GeoSnapshot, actor: uuid.UUID | None) -> None:
    current = db.scalar(
        select(GeoSnapshot)
        .where(GeoSnapshot.source == s.source, GeoSnapshot.status == S.ACTIVE)
        .with_for_update()
    )
    if current is not None:
        current.status = S.SUPERSEDED
        db.flush()  # free the one-active-per-source index before the new one takes it
    s.status = S.ACTIVE
    s.activated_by = actor
    s.activated_at = dt.datetime.now(dt.UTC)
    db.flush()


def activate(ctx: AdminContext, snapshot_id: uuid.UUID, reason: str) -> GeoSnapshotOut:
    s = _locked(ctx.db, snapshot_id)
    if s.status != S.APPROVED:
        raise Conflict("Only an approved snapshot can be activated", code="snapshot_not_approved")
    if s.approved_by == ctx.user_id:
        raise ApiError(
            "Another administrator must activate a snapshot you approved.",
            code="second_admin_required",
            status_code=403,
        )
    _make_active(ctx.db, s, ctx.user_id)
    _audit(ctx.db, "geo.snapshot_activated", s, actor=ctx.user_id, reason=reason)
    return _out(ctx.db, s, ctx.user_id)


def activate_by_operator(db: Session, snapshot_id: uuid.UUID, reason: str, operator: str) -> GeoSnapshot:
    """CLI path for the single-admin pilot: an operator activates a snapshot an admin approved."""
    s = _locked(db, snapshot_id)
    if s.status != S.APPROVED:
        raise Conflict("Only an approved snapshot can be activated", code="snapshot_not_approved")
    _make_active(db, s, None)
    _audit(db, "geo.snapshot_activated_by_operator", s, actor=None, reason=reason, operator=operator[:200])
    db.commit()
    return s


def rollback(ctx: AdminContext, snapshot_id: uuid.UUID, reason: str) -> GeoSnapshotOut:
    s = _locked(ctx.db, snapshot_id)
    if s.status != S.SUPERSEDED:
        raise Conflict("Only a superseded snapshot can be restored", code="snapshot_not_superseded")
    _make_active(ctx.db, s, ctx.user_id)
    _audit(ctx.db, "geo.snapshot_restored", s, actor=ctx.user_id, reason=reason)
    return _out(ctx.db, s, ctx.user_id)


def discard(ctx: AdminContext, snapshot_id: uuid.UUID, reason: str) -> None:
    s = _locked(ctx.db, snapshot_id)
    if s.status not in DISCARDABLE:
        raise Conflict(
            "Active and superseded snapshots are kept for lookups and rollback", code="snapshot_kept"
        )
    _audit(ctx.db, "geo.snapshot_discarded", s, actor=ctx.user_id, reason=reason)
    ctx.db.delete(s)
    ctx.db.flush()
