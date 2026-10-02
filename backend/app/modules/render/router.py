from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbDep, TreeCtx, request_info
from app.api.schemas import Message
from app.authz.context import load_tree_context
from app.core.errors import Forbidden, NotFound
from app.models.enums import RenderArtifactKind
from app.modules.render import service
from app.modules.render.schemas import RenderDownloadOut, RenderJobIn, RenderJobOut

router = APIRouter(prefix="/trees/{tree_id}", tags=["render"])
files_router = APIRouter(tags=["render"])


@router.post("/render-jobs", response_model=RenderJobOut, status_code=status.HTTP_202_ACCEPTED)
def create_render_job(body: RenderJobIn, ctx: TreeCtx) -> RenderJobOut:
    """Queue an animated export (poster preview, or poster + MP4). Rendering runs on the render
    worker; poll the job for status and progress."""
    return service.job_out(ctx, service.create_job(ctx, body))


@router.get("/render-jobs", response_model=list[RenderJobOut])
def list_render_jobs(ctx: TreeCtx, limit: int = Query(default=30, ge=1, le=100)) -> list[RenderJobOut]:
    """Your exports (tree admins see everyone's)."""
    return [service.job_out(ctx, j) for j in service.list_jobs(ctx, limit)]


@router.get("/render-jobs/{job_id}", response_model=RenderJobOut)
def get_render_job(job_id: uuid.UUID, ctx: TreeCtx) -> RenderJobOut:
    return service.job_out(ctx, service.get_job(ctx, job_id))


@router.post("/render-jobs/{job_id}/cancel", response_model=RenderJobOut)
def cancel_render_job(job_id: uuid.UUID, ctx: TreeCtx) -> RenderJobOut:
    return service.job_out(ctx, service.cancel_job(ctx, job_id))


@router.delete("/render-jobs/{job_id}", response_model=Message)
def delete_render_job(job_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_job(ctx, job_id)
    return Message(message="Export deleted")


@router.post("/render-jobs/{job_id}/artifacts/{artifact_id}/download-url", response_model=RenderDownloadOut)
def render_download_url(job_id: uuid.UUID, artifact_id: uuid.UUID, ctx: TreeCtx) -> RenderDownloadOut:
    url, expires = service.issue_download(ctx, job_id, artifact_id)
    return RenderDownloadOut(url=url, expires_at=expires)


@files_router.get("/render-files/{token}", response_class=Response)
def serve_render_file(token: str, request: Request, user: CurrentUser, db: DbDep) -> Response:
    """Serve a rendered poster or video for a signed, short-lived token bound to the user."""
    body = service.resolve_token(token)
    if body["user"] != str(user.id):
        raise Forbidden("This download link was issued to a different user", code="invalid_download_token")
    try:
        ctx = load_tree_context(db, uuid.UUID(body["tree"]), user, request_info(request))
    except NotFound:
        raise Forbidden("This download link is no longer valid", code="invalid_download_token")
    job, art, data = service.read_artifact(ctx, uuid.UUID(body["job"]), uuid.UUID(body["art"]))
    is_video = art.kind == RenderArtifactKind.VIDEO_MP4
    name = f"vanshavali-{job.chart_type.value}-{str(job.id)[:8]}.{'mp4' if is_video else 'png'}"
    return Response(
        content=data,
        media_type=art.mime_type,
        headers={
            "Content-Disposition": f'{"attachment" if is_video else "inline"}; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, private",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )
