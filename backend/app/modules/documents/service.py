"""Document vault: upload pipeline, metadata versioning, links, soft delete and signed downloads.

Pipeline (ADR-0004): permission → size cap → magic-byte validation → SHA-256 → malware scan →
storage class → encrypted write-once object → Document row → optional link → audit → background
processing (previews, OCR, extraction proposals).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.config import get_settings
from app.core.dates import GenealogicalDate, date_to_json
from app.core.errors import ApiError, Conflict, Forbidden, NotFound, Unauthorized, Unprocessable
from app.core.filetypes import validate_upload
from app.core.ids import uuid7
from app.core.scanner import get_scanner
from app.core.security import sign_payload, verify_signed
from app.core.storage import get_store
from app.models import (
    Document,
    DocumentDerivative,
    DocumentLink,
    DocumentMetadataVersion,
    ExtractionProposal,
    Household,
    LandParcel,
    Property,
    PropertyEvent,
)
from app.models.enums import (
    PROPERTY_CATEGORIES,
    VAULT_CATEGORIES,
    DerivativeKind,
    DocumentCategory,
    DocumentLinkTarget,
    PrivacyLevel,
    ProcessingStatus,
    ProposalStatus,
    RecordPrivacyLevel,
    ScanStatus,
    StorageClass,
)
from app.modules.documents import access
from app.modules.documents.previews import supports_preview
from app.modules.documents.schemas import (
    DocumentLinkIn,
    DocumentLinkOut,
    DocumentOut,
    DocumentUpdate,
    MetadataVersionOut,
)
from app.modules.genealogy import lookup

VARIANTS = ("original", "preview", "thumbnail", "stream")
# in-app playback of the original bytes (inline, no download); audio and video only (ADR-0027 §4)
STREAMABLE_PREFIXES = ("audio/", "video/")
METADATA_FIELDS = (
    "title",
    "description",
    "category",
    "privacy_level",
    "document_date",
    "language",
    "script",
    "issuing_authority",
)


# ---------------------------------------------------------------- helpers
def storage_class_for(category: DocumentCategory) -> StorageClass:
    return StorageClass.VAULT if category in VAULT_CATEGORIES else StorageClass.STANDARD


def _safe_filename(name: str | None) -> str:
    base = (name or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '"<>|:*?')
    return base.strip(" .")[:200] or "upload"


def wants_ocr(doc: Document) -> bool:
    from app.modules.extraction.extractors import extractor_for

    return (
        get_settings().ocr_enabled
        and extractor_for(doc.category) is not None
        and supports_preview(doc.mime_type)
    )


def _require_upload(ctx: TreeContext, category: DocumentCategory) -> None:
    ctx.require(Permission.DOCUMENT_UPLOAD)
    if category == DocumentCategory.GEDCOM:
        raise Unprocessable("GEDCOM files are imported through the GEDCOM import", code="use_gedcom_import")
    if category in PROPERTY_CATEGORIES and not (
        ctx.is_admin or ctx.has(Permission.PROPERTY_WRITE) or ctx.has(Permission.PROPERTY_DOCUMENTS)
    ):
        raise Forbidden("Uploading property records needs property write or property document permission")


def _can_manage(ctx: TreeContext, doc: Document) -> bool:
    if ctx.has(Permission.DOCUMENT_MANAGE):
        return True
    return (
        ctx.has(Permission.DOCUMENT_UPLOAD) and doc.created_by is not None and doc.created_by == ctx.user_id
    )


# ---------------------------------------------------------------- link targets
def check_link_target(ctx: TreeContext, target_type: DocumentLinkTarget, target_id: uuid.UUID) -> None:
    """The target must exist in this tree and be visible to the caller (else 404)."""
    if target_type == DocumentLinkTarget.PERSON:
        lookup.get_person(ctx, target_id)
    elif target_type == DocumentLinkTarget.EVENT:
        from app.modules.genealogy.service import get_event_checked

        get_event_checked(ctx, target_id)
    elif target_type == DocumentLinkTarget.RELATIONSHIP:
        rel = lookup.get_relationship(ctx, target_id)
        lookup.get_person(ctx, rel.person_a_id)
        lookup.get_person(ctx, rel.person_b_id)
    elif target_type == DocumentLinkTarget.PLACE:
        lookup.get_place(ctx, target_id)
    elif target_type == DocumentLinkTarget.SOURCE:
        from app.modules.evidence.service import get_source

        get_source(ctx, target_id)
    elif target_type == DocumentLinkTarget.HOUSEHOLD:
        lookup.get_in_tree(ctx, Household, target_id, "Household")
    elif target_type == DocumentLinkTarget.TRADITION:
        from app.modules.traditions.service import get_entry

        get_entry(ctx, target_id)
    else:  # property, land parcel, property event
        if not (ctx.has(Permission.PROPERTY_READ) or ctx.has(Permission.PROPERTY_WRITE)):
            raise NotFound("Link target not found")
        if target_type == DocumentLinkTarget.PROPERTY:
            property_id = target_id
        elif target_type == DocumentLinkTarget.LAND_PARCEL:
            property_id = lookup.get_in_tree(ctx, LandParcel, target_id, "Link target").property_id
        else:
            property_id = lookup.get_in_tree(ctx, PropertyEvent, target_id, "Link target").property_id
        prop = lookup.get_in_tree(ctx, Property, property_id, "Link target")
        from app.modules.property.service import can_view_property

        if not can_view_property(ctx, prop):
            raise NotFound("Link target not found")


def _add_link(ctx: TreeContext, doc: Document, body: DocumentLinkIn) -> DocumentLink:
    check_link_target(ctx, body.target_type, body.target_id)
    existing = ctx.db.scalar(
        select(DocumentLink).where(
            DocumentLink.tree_id == ctx.tree_id,
            DocumentLink.document_id == doc.id,
            DocumentLink.target_type == body.target_type,
            DocumentLink.target_id == body.target_id,
        )
    )
    if existing is not None:
        raise Conflict("The document is already linked to this record", code="duplicate_link")
    link = DocumentLink(
        tree_id=ctx.tree_id,
        document_id=doc.id,
        target_type=body.target_type,
        target_id=body.target_id,
        note=body.note,
        created_by=ctx.user_id,
    )
    ctx.db.add(link)
    ctx.db.flush()
    if body.target_type == DocumentLinkTarget.PERSON:
        from app.modules.documents import sharing

        # tagging a protected person narrows the record at once, never widens it (ADR-0027 §5)
        sharing.enforce_ceiling(ctx, doc, reason="tag")
    audit.log(
        ctx,
        "document.linked",
        target_type="document",
        target_id=doc.id,
        details={"target_type": body.target_type.value, "target_id": str(body.target_id)},
    )
    return link


# ---------------------------------------------------------------- upload
def upload(
    ctx: TreeContext,
    *,
    data: bytes,
    filename: str | None,
    category: DocumentCategory,
    title: str,
    description: str | None = None,
    privacy_level: RecordPrivacyLevel | PrivacyLevel | None = None,
    document_date: GenealogicalDate | None = None,
    language: str | None = None,
    script: str | None = None,
    issuing_authority: str | None = None,
    link: DocumentLinkIn | None = None,
    audience_branch_id: uuid.UUID | None = None,
    allow_download: bool | None = None,
) -> Document:
    _require_upload(ctx, category)
    if link is not None:
        check_link_target(ctx, link.target_type, link.target_id)  # fail before storing anything
    storage_class = storage_class_for(category)
    level, branch, downloadable = _initial_sharing(
        ctx, storage_class, link, privacy_level, audience_branch_id, allow_download
    )
    sniffed = validate_upload(data)
    checksum = hashlib.sha256(data).hexdigest()
    _reject_duplicate(ctx, checksum)

    result = get_scanner().scan(data)
    if not result.clean:
        meta = {"category": category.value, "size_bytes": len(data), "engine": result.engine}
        if result.signature:
            audit.record_detached(
                action="document.malware_rejected",
                actor_user_id=ctx.user_id,
                tree_id=ctx.tree_id,
                target_type="document",
                details={**meta, "signature": result.signature[:120]},
                ip=ctx.request.ip,
                user_agent=ctx.request.user_agent,
            )
            raise Unprocessable(
                "The file was rejected by the malware scanner and has not been stored",
                code="malware_detected",
            )
        audit.record_detached(
            action="document.scan_failed",
            actor_user_id=ctx.user_id,
            tree_id=ctx.tree_id,
            target_type="document",
            details=meta,
            ip=ctx.request.ip,
            user_agent=ctx.request.user_agent,
        )
        raise ApiError(
            "The malware scanner is unavailable; please try again later",
            code="scanner_unavailable",
            status_code=503,
        )

    doc_id = uuid7()
    key = f"{storage_class.value}/{ctx.tree_id}/{checksum[:2]}/{doc_id}/original"
    doc = Document(
        id=doc_id,
        tree_id=ctx.tree_id,
        category=category,
        storage_class=storage_class,
        title=title.strip(),
        description=description,
        original_filename=_safe_filename(filename),
        mime_type=sniffed.mime,
        size_bytes=len(data),
        checksum_sha256=checksum,
        storage_key=key,
        encryption_key_id=storage_class.value,
        document_date=date_to_json(document_date),
        language=language,
        script=script,
        issuing_authority=issuing_authority,
        privacy_level=level,
        audience_branch_id=branch,
        allow_download=downloadable,
        owner_membership_id=ctx.membership_id,
        scan_status=ScanStatus.CLEAN,
        scan_engine=result.engine,
        page_count=sniffed.page_count,
        created_by=ctx.user_id,
    )
    doc.preview_status = (
        ProcessingStatus.PENDING if supports_preview(sniffed.mime) else ProcessingStatus.SKIPPED
    )
    ocr = wants_ocr(doc)
    doc.ocr_status = ProcessingStatus.PENDING if ocr else ProcessingStatus.NOT_REQUESTED
    doc.extraction_status = ProcessingStatus.PENDING if ocr else ProcessingStatus.NOT_REQUESTED
    ctx.db.add(doc)
    ctx.db.flush()
    # the row is flushed first so a failed write rolls the whole upload back
    get_store().put_immutable(key, data, key_id=storage_class.value)
    if link is not None:
        _add_link(ctx, doc, link)
    audit.log(
        ctx,
        "document.uploaded",
        target_type="document",
        target_id=doc.id,
        details={
            "category": category.value,
            "storage_class": storage_class.value,
            "mime_type": sniffed.mime,
            "size_bytes": len(data),
        },
    )
    return doc


def _initial_sharing(
    ctx: TreeContext,
    storage_class: StorageClass,
    link: DocumentLinkIn | None,
    privacy_level: RecordPrivacyLevel | PrivacyLevel | None,
    audience_branch_id: uuid.UUID | None,
    allow_download: bool | None,
) -> tuple[RecordPrivacyLevel, uuid.UUID | None, bool]:
    """Audience of a new upload (ADR-0027 §9): what the uploader chose, never wider than the people it
    is tagged with; by default Only me for the vault and for records about a protected person."""
    from app.modules.documents import sharing

    caps = (
        sharing.caps_for_people(ctx, [link.target_id])
        if link is not None and link.target_type == DocumentLinkTarget.PERSON
        else []
    )
    sensitive = storage_class == StorageClass.VAULT or bool(caps)
    if privacy_level is None:
        level = (
            RecordPrivacyLevel.ONLY_ME if sensitive else RecordPrivacyLevel(ctx.tree.default_person_privacy)
        )
    else:
        level = RecordPrivacyLevel(privacy_level)
    if level == RecordPrivacyLevel.PUBLIC_DECEASED_ONLY:
        raise Unprocessable("Records cannot be public", code="public_not_supported")
    branch = audience_branch_id if level == RecordPrivacyLevel.FAMILY_BRANCH else None
    if level == RecordPrivacyLevel.FAMILY_BRANCH and branch is None:
        # inherited "branch" privacy (an event photo, a person's level): that person's own branch
        branch_caps = [c for c in caps if c.level == RecordPrivacyLevel.FAMILY_BRANCH]
        common = frozenset.intersection(*[c.branches for c in branch_caps]) if branch_caps else frozenset()
        branch = min(common, key=str) if common else None
    if branch is not None:
        from app.models import FamilyBranch

        if (
            ctx.db.scalar(
                select(FamilyBranch.id).where(FamilyBranch.tree_id == ctx.tree_id, FamilyBranch.id == branch)
            )
            is None
        ):
            raise NotFound("Branch not found")
    if not sharing.within(level, branch, caps):
        if privacy_level is not None:
            raise Unprocessable(
                "A person tagged in this record is kept more private; it cannot be shared this widely",
                code="privacy_too_open",
            )
        level, branch = sharing.narrowest(caps)
    downloadable = (not sensitive) if allow_download is None else allow_download
    return level, branch, downloadable


def _reject_duplicate(ctx: TreeContext, checksum: str) -> None:
    """Refuse re-uploading a file the caller can already see.

    SEC-10: documents hidden from the caller are ignored, so an upload never reveals that a hidden
    file with the same content exists (the other copy is stored independently).
    """
    for existing in ctx.db.scalars(
        select(Document).where(
            Document.tree_id == ctx.tree_id,
            Document.checksum_sha256 == checksum,
            Document.deleted_at.is_(None),
        )
    ):
        if access.can_view_document(ctx, existing):
            raise Conflict(
                "This file has already been uploaded to this tree",
                code="duplicate_document",
                details={"existing_document_id": str(existing.id)},
            )


def schedule_processing(ctx: TreeContext, doc: Document, *, force_ocr: bool = False) -> None:
    """Commit, then hand the document to the background pipeline (inline in sync job mode)."""
    from app.core.jobs import enqueue
    from app.modules.documents.processing import process_document

    ctx.db.commit()
    enqueue(process_document, str(doc.id), str(doc.tree_id), force_ocr)
    ctx.db.refresh(doc)


# ---------------------------------------------------------------- read
def links_for(ctx: TreeContext, doc_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[DocumentLink]]:
    out: dict[uuid.UUID, list[DocumentLink]] = {i: [] for i in doc_ids}
    if not doc_ids:
        return out
    for link in ctx.db.scalars(
        select(DocumentLink)
        .where(DocumentLink.tree_id == ctx.tree_id, DocumentLink.document_id.in_(doc_ids))
        .order_by(DocumentLink.created_at)
    ):
        out[link.document_id].append(link)
    return out


def _visible_links(ctx: TreeContext, links: list[DocumentLink]) -> list[DocumentLinkOut]:
    """Only reveal links whose target the viewer may see."""
    out = []
    for link in links:
        try:
            check_link_target(ctx, link.target_type, link.target_id)
        except (NotFound, Forbidden):
            continue
        out.append(DocumentLinkOut.model_validate(link))
    return out


def document_out(ctx: TreeContext, doc: Document, links: list[DocumentLink] | None = None) -> DocumentOut:
    if links is None:
        links = links_for(ctx, [doc.id])[doc.id]
    content = access.can_access_content(ctx, doc)
    downloadable = content and access.can_download(ctx, doc)
    kinds = set(
        ctx.db.scalars(
            select(DocumentDerivative.kind).where(
                DocumentDerivative.tree_id == ctx.tree_id, DocumentDerivative.document_id == doc.id
            )
        )
    )
    pending = 0
    if content:
        pending = int(
            ctx.db.scalar(
                select(func.count())
                .select_from(ExtractionProposal)
                .where(
                    ExtractionProposal.tree_id == ctx.tree_id,
                    ExtractionProposal.document_id == doc.id,
                    ExtractionProposal.status == ProposalStatus.PENDING,
                )
            )
            or 0
        )
    variants = (["original"] if downloadable else []) + [
        k.value for k in (DerivativeKind.PREVIEW, DerivativeKind.THUMBNAIL) if k in kinds
    ]
    if doc.mime_type.startswith(STREAMABLE_PREFIXES):
        variants.append("stream")
    from app.modules.documents.sharing import can_edit

    return DocumentOut.model_validate(doc).model_copy(
        update={
            "links": _visible_links(ctx, links),
            "can_access_content": content,
            "can_download": downloadable,
            "is_owner": access.is_owner(ctx, doc),
            "can_edit_sharing": can_edit(ctx, doc),
            "variants": variants if content else [],
            "has_ocr_text": content and DerivativeKind.OCR_TEXT in kinds,
            "pending_proposals": pending,
        }
    )


def list_documents(
    ctx: TreeContext,
    *,
    category: DocumentCategory | None = None,
    target_type: DocumentLinkTarget | None = None,
    target_id: uuid.UUID | None = None,
    q: str | None = None,
    include_deleted: bool = False,
) -> list[Document]:
    stmt = select(Document).where(Document.tree_id == ctx.tree_id)
    if include_deleted:
        if not ctx.has(Permission.DOCUMENT_MANAGE):
            raise Forbidden("Only document managers can list deleted documents")
        stmt = stmt.where(Document.deleted_at.is_not(None))
    else:
        stmt = stmt.where(Document.deleted_at.is_(None))
    if category is not None:
        stmt = stmt.where(Document.category == category)
    if (target_type is None) != (target_id is None):
        raise Unprocessable("target_type and target_id must be given together")
    if target_type is not None and target_id is not None:
        check_link_target(ctx, target_type, target_id)
        stmt = stmt.where(
            Document.id.in_(
                select(DocumentLink.document_id).where(
                    DocumentLink.tree_id == ctx.tree_id,
                    DocumentLink.target_type == target_type,
                    DocumentLink.target_id == target_id,
                )
            )
        )
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{_escape_like(q)}%", escape="\\"))
    rows = ctx.db.scalars(stmt.order_by(Document.created_at.desc(), Document.id)).all()
    return [d for d in rows if access.can_view_document(ctx, d)]


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------- metadata edits
def _snapshot(doc: Document) -> dict[str, Any]:
    snap: dict[str, Any] = {}
    for f in METADATA_FIELDS:
        v = getattr(doc, f)
        snap[f] = v.value if hasattr(v, "value") else v
    return snap


def update_metadata(ctx: TreeContext, document_id: uuid.UUID, body: DocumentUpdate) -> Document:
    doc = access.get_document(ctx, document_id)
    if not _can_manage(ctx, doc):
        raise Forbidden()
    changes = {f: getattr(body, f) for f in body.model_fields_set if f in METADATA_FIELDS}
    if "title" in changes and changes["title"] is None:
        raise Unprocessable("title cannot be empty")
    if "category" in changes:
        new_cat = changes["category"]
        if new_cat is None:
            raise Unprocessable("category cannot be empty")
        if storage_class_for(new_cat) != doc.storage_class:
            raise Unprocessable(
                "This category belongs to a different storage class; upload the file again under it",
                code="storage_class_change",
            )
        if new_cat in PROPERTY_CATEGORIES:
            _require_upload(ctx, new_cat)
    if "privacy_level" in changes and changes["privacy_level"] is None:
        raise Unprocessable("privacy_level cannot be empty")
    if "document_date" in changes:
        changes["document_date"] = date_to_json(changes["document_date"])
    current = _snapshot(doc)  # before any change, so the version history keeps the old values
    if "privacy_level" in changes:
        _change_level(ctx, doc, RecordPrivacyLevel(changes["privacy_level"]))
    effective = {k: v for k, v in changes.items() if (v.value if hasattr(v, "value") else v) != current[k]}
    if not effective:
        return doc
    ctx.db.add(
        DocumentMetadataVersion(
            tree_id=ctx.tree_id,
            document_id=doc.id,
            version=doc.metadata_version,
            snapshot=current,
            created_by=doc.updated_by or doc.created_by,
        )
    )
    for k, v in effective.items():
        setattr(doc, k, v)
    doc.metadata_version += 1
    doc.updated_by = ctx.user_id
    audit.log(
        ctx,
        "document.metadata_changed",
        target_type="document",
        target_id=doc.id,
        details={"fields": sorted(effective), "version": doc.metadata_version},
    )
    return doc


def _change_level(ctx: TreeContext, doc: Document, level: RecordPrivacyLevel) -> None:
    """``PATCH privacy_level`` follows the sharing rules (ADR-0027 §10): the owner may change it up to
    the ceiling; anyone else who manages documents may only narrow a record that is not private."""
    from app.modules.documents import sharing

    if level == RecordPrivacyLevel(doc.privacy_level):
        return
    if not sharing.can_edit(ctx, doc):
        raise Forbidden("You cannot change who can see this record")
    current = sharing._current(ctx, doc)
    if level in (RecordPrivacyLevel.ONLY_ME,):
        current.members = {}
    new = sharing.Proposal(
        level,
        current.audience_branch_id if level == RecordPrivacyLevel.FAMILY_BRANCH else None,
        current.allow_download,
        current.members,
    )
    sharing.apply(ctx, doc, new, confirm_wider=True)  # an explicit API call is the confirmation


def versions(ctx: TreeContext, document_id: uuid.UUID) -> list[MetadataVersionOut]:
    doc = access.get_document(ctx, document_id)
    rows = ctx.db.scalars(
        select(DocumentMetadataVersion)
        .where(DocumentMetadataVersion.tree_id == ctx.tree_id, DocumentMetadataVersion.document_id == doc.id)
        .order_by(DocumentMetadataVersion.version)
    ).all()
    out = [MetadataVersionOut.model_validate(r) for r in rows]
    out.append(
        MetadataVersionOut(
            version=doc.metadata_version,
            snapshot=_snapshot(doc),
            created_by=doc.updated_by or doc.created_by,
            created_at=doc.updated_at,
            current=True,
        )
    )
    return out


# ---------------------------------------------------------------- delete / restore
def delete(ctx: TreeContext, document_id: uuid.UUID) -> Document:
    ctx.require(Permission.DOCUMENT_MANAGE)
    doc = access.get_document(ctx, document_id)
    doc.deleted_at = dt.datetime.now(dt.UTC)
    doc.deleted_by = ctx.user_id
    audit.log(ctx, "document.deleted", target_type="document", target_id=doc.id)
    return doc


def restore(ctx: TreeContext, document_id: uuid.UUID) -> Document:
    ctx.require(Permission.DOCUMENT_MANAGE)
    doc = access.get_document(ctx, document_id, include_deleted=True)
    if doc.deleted_at is None:
        return doc
    _reject_duplicate(ctx, doc.checksum_sha256)
    doc.deleted_at = None
    doc.deleted_by = None
    audit.log(ctx, "document.restored", target_type="document", target_id=doc.id)
    return doc


# ---------------------------------------------------------------- links
def add_link(ctx: TreeContext, document_id: uuid.UUID, body: DocumentLinkIn) -> DocumentLink:
    doc = access.get_document(ctx, document_id)
    if not (ctx.has(Permission.DOCUMENT_UPLOAD) or ctx.has(Permission.DOCUMENT_MANAGE)):
        raise Forbidden()
    return _add_link(ctx, doc, body)


def remove_link(ctx: TreeContext, document_id: uuid.UUID, link_id: uuid.UUID) -> None:
    doc = access.get_document(ctx, document_id)
    link = ctx.db.scalar(
        select(DocumentLink).where(
            DocumentLink.tree_id == ctx.tree_id,
            DocumentLink.id == link_id,
            DocumentLink.document_id == doc.id,
        )
    )
    if link is None:
        raise NotFound("Link not found")
    if not (ctx.has(Permission.DOCUMENT_MANAGE) or (link.created_by and link.created_by == ctx.user_id)):
        raise Forbidden()
    ctx.db.delete(link)
    audit.log(
        ctx,
        "document.unlinked",
        target_type="document",
        target_id=doc.id,
        details={"target_type": link.target_type.value, "target_id": str(link.target_id)},
    )


# ---------------------------------------------------------------- derivatives
def derivative(ctx_db: Any, doc: Document, kind: DerivativeKind, page: int = 0) -> DocumentDerivative | None:
    return ctx_db.scalar(
        select(DocumentDerivative).where(
            DocumentDerivative.tree_id == doc.tree_id,
            DocumentDerivative.document_id == doc.id,
            DocumentDerivative.kind == kind,
            DocumentDerivative.page == page,
        )
    )


def put_derivative(
    db: Any, doc: Document, kind: DerivativeKind, data: bytes, mime: str, engine: str | None, page: int = 0
) -> DocumentDerivative:
    """Store an encrypted derivative under the document's storage class, replacing an older one."""
    store = get_store()
    old = derivative(db, doc, kind, page)
    if old is not None:
        store.delete(old.storage_key)
        db.delete(old)
        db.flush()
    key = f"{doc.storage_key.rsplit('/', 1)[0]}/{kind.value}-p{page}-{uuid7().hex[:16]}"
    store.put_immutable(key, data, key_id=doc.encryption_key_id)
    row = DocumentDerivative(
        tree_id=doc.tree_id,
        document_id=doc.id,
        kind=kind,
        page=page,
        storage_key=key,
        mime_type=mime,
        size_bytes=len(data),
        engine=engine,
    )
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------- downloads
def issue_download_url(ctx: TreeContext, document_id: uuid.UUID, variant: str) -> tuple[str, dt.datetime]:
    if variant not in VARIANTS:
        raise Unprocessable(f"variant must be one of {', '.join(VARIANTS)}")
    doc = access.get_document(ctx, document_id)
    _require_variant(ctx, doc, variant)
    if variant in ("preview", "thumbnail") and derivative(ctx.db, doc, DerivativeKind(variant)) is None:
        raise NotFound(f"No {variant} is available for this document")
    s = get_settings()
    ttl = min(s.download_url_ttl_seconds, 300)
    if ctx.user_id is None:
        raise Unauthorized()
    token = sign_payload(
        {
            "doc": str(doc.id),
            "tree": str(ctx.tree_id),
            "user": str(ctx.user_id),
            "variant": variant,
            "p": "dl",
        },
        ttl_seconds=ttl,
    )
    expires = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=ttl)
    audit.log(
        ctx,
        "document.download_url_issued",
        target_type="document",
        target_id=doc.id,
        details={"variant": variant},
    )
    return f"{s.api_prefix}/files/{token}", expires


def _require_variant(ctx: TreeContext, doc: Document, variant: str) -> None:
    if variant == "original":
        access.require_download(ctx, doc)
        return
    access.require_content(ctx, doc)
    if variant == "stream" and not doc.mime_type.startswith(STREAMABLE_PREFIXES):
        raise Unprocessable("Only audio and video can be played", code="not_streamable")


def resolve_download_token(token: str) -> dict[str, Any]:
    body = verify_signed(token)
    if body is None or body.get("p") != "dl":
        raise Forbidden("This download link is invalid or has expired", code="invalid_download_token")
    try:
        uuid.UUID(body["doc"])
        uuid.UUID(body["tree"])
        uuid.UUID(body["user"])
    except (KeyError, ValueError, TypeError):
        raise Forbidden("This download link is invalid or has expired", code="invalid_download_token")
    if body.get("variant") not in VARIANTS:
        raise Forbidden("This download link is invalid or has expired", code="invalid_download_token")
    return body


def read_content(ctx: TreeContext, document_id: uuid.UUID, variant: str) -> tuple[Document, bytes, str]:
    """Re-check authorisation at download time (revoked access must fail) and decrypt."""
    try:
        doc = access.get_document(ctx, document_id)
    except NotFound:
        raise Forbidden("This download link is no longer valid", code="invalid_download_token")
    allowed = access.can_download(ctx, doc) if variant == "original" else access.can_access_content(ctx, doc)
    if not allowed:
        raise Forbidden("You no longer have permission to download this document")
    store = get_store()
    if variant in ("original", "stream"):
        data, mime = store.get(doc.storage_key), doc.mime_type
    else:
        d = derivative(ctx.db, doc, DerivativeKind(variant))
        if d is None:
            raise NotFound(f"No {variant} is available for this document")
        data, mime = store.get(d.storage_key), d.mime_type
    audit.log(
        ctx, "document.downloaded", target_type="document", target_id=doc.id, details={"variant": variant}
    )
    return doc, data, mime


# ---------------------------------------------------------------- search provider
def search_documents(ctx: TreeContext, q: str, limit: int) -> list[Any]:
    from app.modules.search.schemas import SearchHit

    if not ctx.is_member or ctx.public:
        return []
    rows = ctx.db.scalars(
        select(Document)
        .where(
            Document.tree_id == ctx.tree_id,
            Document.deleted_at.is_(None),
            Document.title.ilike(f"%{_escape_like(q)}%", escape="\\"),
        )
        .order_by(Document.created_at.desc())
        .limit(limit * 3)
    ).all()
    hits = []
    for d in rows:
        if not access.can_view_document(ctx, d):
            continue
        exact = d.title.strip().lower() == q.strip().lower()
        hits.append(
            SearchHit(
                kind="document",
                id=d.id,
                title=d.title,
                subtitle=d.category.value,
                score=0.75 if exact else 0.6,
                match_tier="exact" if exact else "contains",
                match_reason=f'document title {"is" if exact else "contains"} "{q}"',
            )
        )
        if len(hits) >= limit:
            break
    return hits
