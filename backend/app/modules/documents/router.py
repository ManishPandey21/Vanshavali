from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.deps import CurrentUser, DbDep, TreeCtx, request_info
from app.api.schemas import Message, Page, decode_cursor, encode_cursor
from app.authz.context import load_tree_context
from app.core.config import get_settings
from app.core.dates import GenealogicalDate
from app.core.errors import Forbidden, NotFound, Unprocessable
from app.models.enums import DocumentCategory, DocumentLinkTarget, PrivacyLevel
from app.modules.documents import service
from app.modules.documents.schemas import (
    DocumentLinkIn,
    DocumentLinkOut,
    DocumentOut,
    DocumentUpdate,
    DownloadUrlOut,
    MetadataVersionOut,
)
from app.modules.search import providers

router = APIRouter(prefix="/trees/{tree_id}", tags=["documents"])
files_router = APIRouter(tags=["documents"])

providers.register("document", service.search_documents)

_CHUNK = 1 << 20


def _read_capped(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_bytes
    buf = bytearray()
    while True:
        chunk = file.file.read(_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > limit:
            raise Unprocessable(f"The file is larger than {limit // (1024 * 1024)} MB", code="file_too_large")
    return bytes(buf)


def _parse_date(raw: str | None) -> GenealogicalDate | None:
    if raw is None or not raw.strip():
        return None
    try:
        return GenealogicalDate.model_validate_json(raw)
    except ValidationError as exc:
        raise Unprocessable(
            "document_date must be a JSON genealogical date",
            code="validation_error",
            details=[{"loc": ["body", "document_date", *e["loc"]], "msg": e["msg"]} for e in exc.errors()],
        )


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    ctx: TreeCtx,
    file: Annotated[UploadFile, File(description="The document (PDF, image, audio or video)")],
    category: Annotated[DocumentCategory, Form()],
    title: Annotated[str, Form(min_length=1, max_length=400)],
    description: Annotated[str | None, Form(max_length=20000)] = None,
    privacy_level: Annotated[PrivacyLevel | None, Form()] = None,
    document_date: Annotated[str | None, Form(description="GenealogicalDate as JSON")] = None,
    language: Annotated[str | None, Form(max_length=16)] = None,
    script: Annotated[str | None, Form(max_length=20)] = None,
    issuing_authority: Annotated[str | None, Form(max_length=300)] = None,
    link_target_type: Annotated[DocumentLinkTarget | None, Form()] = None,
    link_target_id: Annotated[uuid.UUID | None, Form()] = None,
) -> DocumentOut:
    if (link_target_type is None) != (link_target_id is None):
        raise Unprocessable("link_target_type and link_target_id must be given together")
    date = _parse_date(document_date)
    data = _read_capped(file)
    link = (
        DocumentLinkIn(target_type=link_target_type, target_id=link_target_id)
        if link_target_type is not None and link_target_id is not None
        else None
    )
    doc = service.upload(
        ctx,
        data=data,
        filename=file.filename,
        category=category,
        title=title,
        description=description,
        privacy_level=privacy_level,
        document_date=date,
        language=language,
        script=script,
        issuing_authority=issuing_authority,
        link=link,
    )
    service.schedule_processing(ctx, doc)
    return service.document_out(ctx, doc)


@router.get("/documents", response_model=Page[DocumentOut])
def list_documents(
    ctx: TreeCtx,
    category: DocumentCategory | None = None,
    target_type: DocumentLinkTarget | None = None,
    target_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    deleted: bool = False,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[DocumentOut]:
    """Documents visible to the caller. ``target_type``+``target_id`` → "documents about X"."""
    offset = decode_cursor(cursor)
    rows = service.list_documents(
        ctx, category=category, target_type=target_type, target_id=target_id, q=q, include_deleted=deleted
    )
    page = rows[offset : offset + limit]
    links = service.links_for(ctx, [d.id for d in page])
    return Page(
        items=[service.document_out(ctx, d, links[d.id]) for d in page],
        next_cursor=encode_cursor(offset + limit) if len(rows) > offset + limit else None,
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, ctx: TreeCtx) -> DocumentOut:
    from app.modules.documents.access import get_document as _get

    return service.document_out(ctx, _get(ctx, document_id))


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def update_document(document_id: uuid.UUID, body: DocumentUpdate, ctx: TreeCtx) -> DocumentOut:
    return service.document_out(ctx, service.update_metadata(ctx, document_id, body))


@router.get("/documents/{document_id}/versions", response_model=list[MetadataVersionOut])
def metadata_versions(document_id: uuid.UUID, ctx: TreeCtx) -> list[MetadataVersionOut]:
    return service.versions(ctx, document_id)


@router.delete("/documents/{document_id}", response_model=Message)
def delete_document(document_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete(ctx, document_id)
    return Message(message="Document moved to the recycle bin (restorable by a document manager)")


@router.post("/documents/{document_id}/restore", response_model=DocumentOut)
def restore_document(document_id: uuid.UUID, ctx: TreeCtx) -> DocumentOut:
    return service.document_out(ctx, service.restore(ctx, document_id))


@router.post(
    "/documents/{document_id}/links", response_model=DocumentLinkOut, status_code=status.HTTP_201_CREATED
)
def add_link(document_id: uuid.UUID, body: DocumentLinkIn, ctx: TreeCtx) -> DocumentLinkOut:
    return DocumentLinkOut.model_validate(service.add_link(ctx, document_id, body))


@router.delete("/documents/{document_id}/links/{link_id}", response_model=Message)
def remove_link(document_id: uuid.UUID, link_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.remove_link(ctx, document_id, link_id)
    return Message(message="Link removed")


@router.post("/documents/{document_id}/download-url", response_model=DownloadUrlOut)
def download_url(
    document_id: uuid.UUID,
    ctx: TreeCtx,
    variant: str = Query(default="original", pattern="^(original|preview|thumbnail)$"),
) -> DownloadUrlOut:
    url, expires = service.issue_download_url(ctx, document_id, variant)
    return DownloadUrlOut(url=url, expires_at=expires, variant=variant)


# ---------------------------------------------------------------- signed file delivery
def _disposition(kind: str, filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode() or "document"
    ascii_name = ascii_name.replace('"', "").replace("\\", "")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


@files_router.get("/files/{token}", response_class=Response)
def serve_file(token: str, request: Request, user: CurrentUser, db: DbDep) -> Response:
    """Serve decrypted bytes for a signed, short-lived token.

    The token is bound to (document, tree, user, variant, expiry). The session user must be the
    user the token was issued to, and authorisation is evaluated again now, so revoked access
    or a deleted document fails even while the token has not expired.
    """
    body = service.resolve_download_token(token)
    if body["user"] != str(user.id):
        raise Forbidden("This download link was issued to a different user", code="invalid_download_token")
    try:
        ctx = load_tree_context(db, uuid.UUID(body["tree"]), user, request_info(request))
    except NotFound:
        raise Forbidden("This download link is no longer valid", code="invalid_download_token")
    variant = body["variant"]
    doc, data, mime = service.read_content(ctx, uuid.UUID(body["doc"]), variant)
    if variant == "original":
        disposition = _disposition("attachment", doc.original_filename)
    else:
        stem = doc.original_filename.rsplit(".", 1)[0] or "document"
        disposition = _disposition("inline", f"{stem}-{variant}.jpg")
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store, private",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )
