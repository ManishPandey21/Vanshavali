"""Geography snapshots in the Super Admin console (ADR-0019 §3). ``MasterDataAdmin`` on every
handler: system admins with two-step sign-in only; everyone else gets 404."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import MasterDataAdmin
from app.modules.geo import admin
from app.modules.geo.schemas import GeoDecisionIn, GeoSnapshotOut

router = APIRouter(prefix="/admin/master-data/geo", tags=["master-data-admin"])


@router.get("/snapshots", response_model=list[GeoSnapshotOut])
def list_snapshots(ctx: MasterDataAdmin) -> list[GeoSnapshotOut]:
    """Every staged, validated, failed, approved, active and superseded snapshot, with its report."""
    return admin.list_snapshots(ctx)


@router.get("/snapshots/{snapshot_id}", response_model=GeoSnapshotOut)
def get_snapshot(snapshot_id: uuid.UUID, ctx: MasterDataAdmin) -> GeoSnapshotOut:
    return admin.get_snapshot(ctx, snapshot_id)


@router.post("/snapshots/{snapshot_id}/approve", response_model=GeoSnapshotOut)
def approve(snapshot_id: uuid.UUID, body: GeoDecisionIn, ctx: MasterDataAdmin) -> GeoSnapshotOut:
    """Approve a validated snapshot after reviewing its report."""
    return admin.approve(ctx, snapshot_id, body.reason)


@router.post("/snapshots/{snapshot_id}/activate", response_model=GeoSnapshotOut)
def activate(snapshot_id: uuid.UUID, body: GeoDecisionIn, ctx: MasterDataAdmin) -> GeoSnapshotOut:
    """Make an approved snapshot the one users see. The approver cannot activate it (four-eyes)."""
    return admin.activate(ctx, snapshot_id, body.reason)


@router.post("/snapshots/{snapshot_id}/rollback", response_model=GeoSnapshotOut)
def rollback(snapshot_id: uuid.UUID, body: GeoDecisionIn, ctx: MasterDataAdmin) -> GeoSnapshotOut:
    """Restore a superseded snapshot as the active one."""
    return admin.rollback(ctx, snapshot_id, body.reason)


@router.post("/snapshots/{snapshot_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
def discard(snapshot_id: uuid.UUID, body: GeoDecisionIn, ctx: MasterDataAdmin) -> Response:
    """Delete a snapshot that never became active (and its rows)."""
    admin.discard(ctx, snapshot_id, body.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
