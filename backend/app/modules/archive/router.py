from __future__ import annotations

from fastapi import APIRouter, Query, Response

from app.api.deps import TreeCtx
from app.modules.archive import service

router = APIRouter(prefix="/trees/{tree_id}", tags=["archive"])


@router.get(
    "/exports/archive",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}, "description": "Family archive ZIP (PRS §43)"}},
)
def export_archive(
    ctx: TreeCtx,
    exclude_living: bool = Query(default=True),
    include_sensitive: bool = Query(default=False),
    include_vault_documents: bool = Query(default=False),
) -> Response:
    """Download a complete family archive generated from the caller's privacy view."""
    blob, filename, _ = service.build_archive(
        ctx,
        exclude_living=exclude_living,
        include_sensitive=include_sensitive,
        include_vault_documents=include_vault_documents,
    )
    return Response(
        content=blob,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
