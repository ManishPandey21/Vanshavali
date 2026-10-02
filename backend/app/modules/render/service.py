"""Render jobs and artifacts (ADR-0017; docs/architecture/remotion-rendering.md).

Lifecycle: ``queued`` → ``running`` → ``succeeded`` | ``failed``; ``cancelled`` by the requester
while queued or running. The payload is built *as the requester* when the job is created, stored
encrypted, rendered on the render queue and purged when the job ends. Artifacts are encrypted too
and downloadable only by the requester (and tree admins) through short-lived signed URLs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit, events
from app.core.config import get_settings
from app.core.db import bind_tree, get_sessionmaker
from app.core.errors import ApiError, Forbidden, NotFound, Unauthorized, Unprocessable
from app.core.jobs import enqueue
from app.core.security import sign_payload, verify_signed
from app.core.storage import StorageError, get_store
from app.models import RenderArtifact, RenderJob
from app.models.enums import ANIMATED_CHARTS, RenderArtifactKind, RenderOutput, RenderStatus
from app.modules.render import payloads
from app.modules.render.renderers import RenderError, get_renderer
from app.modules.render.schemas import RenderArtifactOut, RenderJobIn, RenderJobOut

log = logging.getLogger("app.render")

ACTIVE = (RenderStatus.QUEUED, RenderStatus.RUNNING)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _key(tree_id: uuid.UUID, job_id: uuid.UUID, name: str) -> str:
    return f"STANDARD/{tree_id}/render/{job_id}/{name}"


def _require_enabled() -> None:
    if get_settings().render_backend == "disabled":
        raise ApiError(
            "Animated exports are not enabled on this server", code="render_unavailable", status_code=503
        )


def _visible_job(ctx: TreeContext, job_id: uuid.UUID) -> RenderJob:
    job = ctx.db.scalar(select(RenderJob).where(RenderJob.tree_id == ctx.tree_id, RenderJob.id == job_id))
    # a render shows what its requester could see: only they (and tree admins) may see it
    if job is None or (job.requested_by != ctx.user_id and not ctx.is_admin):
        raise NotFound("Render job not found")
    return job


def job_out(ctx: TreeContext, job: RenderJob) -> RenderJobOut:
    arts = list(
        ctx.db.scalars(
            select(RenderArtifact).where(
                RenderArtifact.tree_id == ctx.tree_id, RenderArtifact.job_id == job.id
            )
        )
    )
    return RenderJobOut.model_validate(job).model_copy(
        update={
            "artifacts": [RenderArtifactOut.model_validate(a) for a in arts],
            "mine": job.requested_by == ctx.user_id,
        }
    )


def create_job(ctx: TreeContext, body: RenderJobIn) -> RenderJob:
    if ctx.public or ctx.user_id is None:
        raise Forbidden()
    ctx.require(Permission.TREE_READ)
    _require_enabled()
    if body.chart_type not in ANIMATED_CHARTS:
        raise Unprocessable("This chart has no animated export", code="not_animatable")
    s = get_settings()
    active = ctx.db.scalar(
        select(func.count())
        .select_from(RenderJob)
        .where(
            RenderJob.tree_id == ctx.tree_id,
            RenderJob.requested_by == ctx.user_id,
            RenderJob.status.in_(ACTIVE),
        )
    )
    if (active or 0) >= s.render_max_active_per_user:
        raise Unprocessable("Wait for your other exports to finish first", code="too_many_active_renders")
    today = ctx.db.scalar(
        select(func.count())
        .select_from(RenderJob)
        .where(RenderJob.tree_id == ctx.tree_id, RenderJob.created_at >= _now() - dt.timedelta(days=1))
    )
    if (today or 0) >= s.render_max_per_day_per_tree:
        raise Unprocessable("This tree has reached today's limit of exports", code="render_quota_reached")
    composition, props = payloads.build(ctx, body.chart_type, body.settings)
    raw = json.dumps({"composition": composition, "props": props}, ensure_ascii=False).encode()
    if len(raw) > s.render_max_payload_bytes:
        raise Unprocessable(
            "This export is too large; choose fewer generations or photos", code="payload_too_large"
        )
    job = RenderJob(
        tree_id=ctx.tree_id,
        requested_by=ctx.user_id,
        chart_type=body.chart_type,
        output=body.output,
        settings=body.settings.model_dump(mode="json"),
        created_by=ctx.user_id,
    )
    ctx.db.add(job)
    ctx.db.flush()
    key = _key(ctx.tree_id, job.id, "payload.json")
    get_store().put_immutable(key, raw, key_id="STANDARD")
    job.payload_storage_key = key
    job.payload_sha256 = hashlib.sha256(raw).hexdigest()
    audit.log(
        ctx,
        "render.requested",
        target_type="render_job",
        target_id=job.id,
        details={"chart_type": body.chart_type.value, "output": body.output.value},
    )
    ctx.db.commit()
    enqueue(
        run_render,
        str(job.id),
        str(ctx.tree_id),
        queue=s.render_queue_name,
        timeout=s.render_timeout_seconds + 60,
    )
    ctx.db.refresh(job)
    return job


def list_jobs(ctx: TreeContext, limit: int = 50) -> list[RenderJob]:
    stmt = select(RenderJob).where(RenderJob.tree_id == ctx.tree_id)
    if not ctx.is_admin:
        stmt = stmt.where(RenderJob.requested_by == ctx.user_id)
    return list(ctx.db.scalars(stmt.order_by(RenderJob.created_at.desc()).limit(limit)))


def get_job(ctx: TreeContext, job_id: uuid.UUID) -> RenderJob:
    return _visible_job(ctx, job_id)


def cancel_job(ctx: TreeContext, job_id: uuid.UUID) -> RenderJob:
    job = _visible_job(ctx, job_id)
    if job.requested_by != ctx.user_id and not ctx.is_admin:
        raise Forbidden()
    if job.status in ACTIVE:
        job.status, job.finished_at, job.error_code = RenderStatus.CANCELLED, _now(), "cancelled"
        _purge_payload(job)
        audit.log(ctx, "render.cancelled", target_type="render_job", target_id=job.id)
    return job


def _purge_payload(job: RenderJob) -> None:
    if job.payload_storage_key:
        try:
            get_store().purge(job.payload_storage_key)
        except (StorageError, OSError):
            log.warning("render payload of job %s could not be removed", job.id)
        job.payload_storage_key = None


# ---------------------------------------------------------------- worker
def run_render(job_id: str, tree_id: str) -> str:
    """Render job (render queue). Progress and status are committed as they change."""
    maker = get_sessionmaker()
    with maker() as db:
        bind_tree(db, tree_id)
        job = db.scalar(
            select(RenderJob)
            .where(RenderJob.tree_id == uuid.UUID(tree_id), RenderJob.id == uuid.UUID(job_id))
            .with_for_update(skip_locked=True)
        )
        if job is None or job.status != RenderStatus.QUEUED or not job.payload_storage_key:
            return "skipped"
        job.status, job.started_at, job.attempts = RenderStatus.RUNNING, _now(), job.attempts + 1
        db.commit()
        start = time.perf_counter()
        last = [0.0]

        def progress(p: float) -> None:
            pct = max(0, min(99, int(p * 100)))
            if pct - last[0] >= 5:
                last[0] = pct
                with maker() as pdb:
                    bind_tree(pdb, tree_id)
                    row = pdb.get(RenderJob, job.id)
                    if row is not None and row.status == RenderStatus.RUNNING:
                        row.progress = pct
                        pdb.commit()

        try:
            raw = get_store().get(job.payload_storage_key)
            payload: dict[str, Any] = json.loads(raw)
            renderer = get_renderer()
            result = renderer.render(payload["composition"], payload["props"], job.output.value, progress)
            db.refresh(job)
            if job.status == RenderStatus.CANCELLED:
                return "cancelled"
            _store_artifact(db, job, RenderArtifactKind.POSTER_PNG, result.poster, "image/png", result)
            if job.output == RenderOutput.MP4 and result.video is not None:
                _store_artifact(db, job, RenderArtifactKind.VIDEO_MP4, result.video, "video/mp4", result)
            job.status, job.progress, job.renderer = RenderStatus.SUCCEEDED, 100, result.renderer
            job.error_code = job.error_message = None
            events.record_job("render", "succeeded", time.perf_counter() - start)
        except RenderError as exc:
            job.status, job.error_code, job.error_message = RenderStatus.FAILED, exc.code, exc.message or None
            events.record_job("render", "failed", time.perf_counter() - start)
        except Exception as exc:  # unexpected: record a type only (no payload content)
            log.exception("render job %s failed", job.id)
            job.status, job.error_code = RenderStatus.FAILED, f"internal_{type(exc).__name__}"[:80].lower()
            job.error_message = "The export could not be rendered"
            events.record_job("render", "failed", time.perf_counter() - start)
        job.finished_at = _now()
        _purge_payload(job)
        db.commit()
        return job.status.value


def _store_artifact(
    db: Any, job: RenderJob, kind: RenderArtifactKind, data: bytes, mime: str, result: Any
) -> None:
    key = _key(job.tree_id, job.id, "poster.png" if kind == RenderArtifactKind.POSTER_PNG else "video.mp4")
    get_store().put_immutable(key, data, key_id="STANDARD")
    db.add(
        RenderArtifact(
            tree_id=job.tree_id,
            job_id=job.id,
            kind=kind,
            storage_key=key,
            mime_type=mime,
            size_bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            width=result.width,
            height=result.height,
            duration_s=result.duration_s if kind == RenderArtifactKind.VIDEO_MP4 else None,
            created_by=job.requested_by,
        )
    )
    db.flush()


# ---------------------------------------------------------------- downloads
def issue_download(ctx: TreeContext, job_id: uuid.UUID, artifact_id: uuid.UUID) -> tuple[str, dt.datetime]:
    job = _visible_job(ctx, job_id)
    art = ctx.db.scalar(
        select(RenderArtifact).where(
            RenderArtifact.tree_id == ctx.tree_id,
            RenderArtifact.job_id == job.id,
            RenderArtifact.id == artifact_id,
        )
    )
    if art is None:
        raise NotFound("Artifact not found")
    if ctx.user_id is None:
        raise Unauthorized()
    s = get_settings()
    ttl = min(s.download_url_ttl_seconds, 300)
    token = sign_payload(
        {
            "p": "rd",
            "job": str(job.id),
            "art": str(art.id),
            "tree": str(ctx.tree_id),
            "user": str(ctx.user_id),
        },
        ttl_seconds=ttl,
    )
    audit.log(
        ctx,
        "render.download_url_issued",
        target_type="render_job",
        target_id=job.id,
        details={"kind": art.kind.value},
    )
    return f"{s.api_prefix}/render-files/{token}", _now() + dt.timedelta(seconds=ttl)


def resolve_token(token: str) -> dict[str, Any]:
    body = verify_signed(token)
    if body is None or body.get("p") != "rd":
        raise Forbidden("This download link is invalid or has expired", code="invalid_download_token")
    try:
        for k in ("job", "art", "tree", "user"):
            uuid.UUID(body[k])
    except (KeyError, ValueError, TypeError):
        raise Forbidden("This download link is invalid or has expired", code="invalid_download_token")
    return body


def read_artifact(
    ctx: TreeContext, job_id: uuid.UUID, artifact_id: uuid.UUID
) -> tuple[RenderJob, RenderArtifact, bytes]:
    """Authorisation is evaluated again at download time."""
    try:
        job = _visible_job(ctx, job_id)
    except NotFound:
        raise Forbidden("This download link is no longer valid", code="invalid_download_token")
    art = ctx.db.scalar(
        select(RenderArtifact).where(
            RenderArtifact.tree_id == ctx.tree_id,
            RenderArtifact.job_id == job.id,
            RenderArtifact.id == artifact_id,
        )
    )
    if art is None:
        raise Forbidden("This download link is no longer valid", code="invalid_download_token")
    data = get_store().get(art.storage_key)
    audit.log(
        ctx, "render.downloaded", target_type="render_job", target_id=job.id, details={"kind": art.kind.value}
    )
    return job, art, data


def delete_job(ctx: TreeContext, job_id: uuid.UUID) -> None:
    job = _visible_job(ctx, job_id)
    if job.status in ACTIVE:
        cancel_job(ctx, job_id)
    for art in ctx.db.scalars(
        select(RenderArtifact).where(RenderArtifact.tree_id == ctx.tree_id, RenderArtifact.job_id == job.id)
    ):
        try:
            get_store().purge(art.storage_key)
        except (StorageError, OSError):
            log.warning("render artifact %s could not be removed", art.id)
    _purge_payload(job)
    ctx.db.delete(job)
    audit.log(ctx, "render.deleted", target_type="render_job", target_id=job.id)
