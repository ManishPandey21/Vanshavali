from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import Response

from app.api.deps import TreeCtx
from app.authz.permissions import Permission
from app.core.config import get_settings
from app.core.errors import ApiError
from app.modules.consent.attestation import require_attestation
from app.modules.gedcom import service
from app.modules.gedcom.schemas import CommitIn, ImportJobOut, ImportJobSummary

router = APIRouter(prefix="/trees/{tree_id}", tags=["gedcom"])

_CHUNK = 1024 * 1024


def _read_capped(file: UploadFile) -> bytes:
    # a GEDCOM package (zip with photos) may be larger than a single file; the service re-checks
    limit = max(get_settings().max_upload_bytes, get_settings().max_gedcom_package_bytes)
    buf = bytearray()
    while True:
        chunk = file.file.read(_CHUNK)
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            raise ApiError(
                "The file is larger than the upload limit",
                code="file_too_large",
                status_code=413,
                details={"max_bytes": limit},
            )
    return bytes(buf)


@router.post("/imports", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED)
def upload_gedcom(ctx: TreeCtx, file: UploadFile = File(...)) -> ImportJobOut:
    ctx.require(Permission.GEDCOM_IMPORT)  # before reading the body
    require_attestation(ctx)  # ADR-0011: an import adds people too
    data = _read_capped(file)
    job = service.upload(ctx, file.filename, data)
    return service.job_out(ctx, job)


@router.get("/imports", response_model=list[ImportJobSummary])
def list_imports(ctx: TreeCtx) -> list[ImportJobSummary]:
    return service.list_jobs(ctx)


@router.get("/imports/{import_id}", response_model=ImportJobOut)
def get_import(
    import_id: uuid.UUID,
    ctx: TreeCtx,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> ImportJobOut:
    return service.job_out(ctx, service.get_job(ctx, import_id), offset, limit)


@router.post("/imports/{import_id}/commit", response_model=ImportJobOut)
def commit_import(import_id: uuid.UUID, body: CommitIn, ctx: TreeCtx) -> ImportJobOut:
    job = service.commit(ctx, import_id, body)
    return service.job_out(ctx, job, 0, 0)


@router.post("/imports/{import_id}/cancel", response_model=ImportJobSummary)
def cancel_import(import_id: uuid.UUID, ctx: TreeCtx) -> ImportJobSummary:
    return service.summary(service.cancel(ctx, import_id))


@router.get(
    "/exports/gedcom",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}, "description": "GEDCOM 7.0 file"}},
)
def export_gedcom(
    ctx: TreeCtx,
    exclude_living: bool = Query(default=True),
    include_sensitive: bool = Query(default=False),
) -> Response:
    data, filename = service.export(ctx, exclude_living=exclude_living, include_sensitive=include_sensitive)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
