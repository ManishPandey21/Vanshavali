"""Document authorisation (ADR-0004 §5, ADR-0006 §5, ADR-0027).

Three questions, each stricter than the last:

* **View** (metadata, links, album entry, search hit): the document's audience admits the viewer
  (``record_allows``: owner always; ``ONLY_ME`` nobody else; ``SELECTED_MEMBERS`` grantees only;
  "Selected branch" that branch; every other level as ADR-0006, explicit grants counting). For the
  legacy ``PRIVATE_TREE_ADMINS`` vault default, custodians for the category also see it. The two
  private audiences never admit anyone by role.
* **Content** (thumbnail, preview, in-app playback, OCR text, extracted values): view, plus — for
  the VAULT storage class — ``document.vault`` (``property.documents`` for property categories), an
  explicit ``download`` grant, or being the owner.
* **Download** (the original as an attachment; ZIP, PDF and video exports): content, plus the owner,
  ``allow_download`` on the record, or a ``download`` grant.

Not visible → 404 (existence is not revealed). Visible but not permitted → 403.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import is_private_record_level, is_record_owner, record_allows
from app.core.errors import Forbidden, NotFound
from app.models import Document
from app.models.enums import (
    PROPERTY_CATEGORIES,
    GrantPermission,
    GrantResource,
    PrivacyLevel,
    StorageClass,
)


def _custodian_for(ctx: TreeContext, doc: Document) -> bool:
    if is_private_record_level(doc.privacy_level):
        return False  # ADR-0027 §1: no role reaches a private record
    if ctx.has(Permission.DOCUMENT_VAULT):
        return True
    return doc.category in PROPERTY_CATEGORIES and ctx.has(Permission.PROPERTY_DOCUMENTS)


def is_owner(ctx: TreeContext, doc: Document) -> bool:
    return is_record_owner(ctx, doc.owner_membership_id)


def can_view_document(ctx: TreeContext, doc: Document) -> bool:
    if ctx.public or not ctx.is_member:
        return False
    if doc.tree_id != ctx.tree_id:
        return False
    if record_allows(
        ctx,
        doc.privacy_level,
        owner_membership_id=doc.owner_membership_id,
        audience_branch_id=doc.audience_branch_id,
        grant=(GrantResource.DOCUMENT, doc.id),
    ):
        return True
    return doc.privacy_level == PrivacyLevel.PRIVATE_TREE_ADMINS and _custodian_for(ctx, doc)


def can_access_content(ctx: TreeContext, doc: Document) -> bool:
    """Thumbnail, preview, playback and OCR text."""
    if not can_view_document(ctx, doc):
        return False
    if doc.storage_class != StorageClass.VAULT or is_owner(ctx, doc):
        return True
    if _custodian_for(ctx, doc):
        return True
    return ctx.has_grant(GrantResource.DOCUMENT, doc.id, GrantPermission.DOWNLOAD)


def can_download(ctx: TreeContext, doc: Document) -> bool:
    """The original file, and inclusion in exports (ADR-0027 §4)."""
    if not can_access_content(ctx, doc):
        return False
    if is_owner(ctx, doc) or doc.allow_download:
        return True
    if doc.storage_class == StorageClass.VAULT and _custodian_for(ctx, doc):
        return True  # the vault rule is the custodians' download right (never on private records)
    return ctx.has_grant(GrantResource.DOCUMENT, doc.id, GrantPermission.DOWNLOAD)


def get_document(ctx: TreeContext, document_id: uuid.UUID, *, include_deleted: bool = False) -> Document:
    doc = ctx.db.scalar(select(Document).where(Document.tree_id == ctx.tree_id, Document.id == document_id))
    if doc is None or (doc.deleted_at is not None and not include_deleted):
        raise NotFound("Document not found")
    if not can_view_document(ctx, doc):
        raise NotFound("Document not found")
    return doc


def require_owner_if_private(ctx: TreeContext, doc: Document) -> None:
    """ADR-0027 §10: a grantee changes nothing on a private record, whatever their role.

    On "Only me" and "Selected members" records, only the content owner may edit, delete, restore,
    link, tag, reprocess or review extraction. Members it is shared with may only read (and download
    when allowed). Shared audiences keep the existing role rules.
    """
    if is_private_record_level(doc.privacy_level) and not is_owner(ctx, doc):
        raise Forbidden("Only the record's owner can change a private record", code="not_content_owner")


def require_content(ctx: TreeContext, doc: Document) -> None:
    if not can_access_content(ctx, doc):
        raise Forbidden("You do not have permission to open the contents of this document")


def require_download(ctx: TreeContext, doc: Document) -> None:
    if not can_download(ctx, doc):
        raise Forbidden("You do not have permission to download this document", code="download_not_allowed")
