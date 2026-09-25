"""Document authorisation (ADR-0004 §5, ADR-0006 §5).

* **Metadata** is visible when the document's privacy level admits the viewer (explicit grants
  count), or — for vault documents kept at the default ``PRIVATE_TREE_ADMINS`` — when the viewer is
  a custodian for that category, or when the viewer uploaded it.
* **Content** (original bytes, previews, OCR text, extracted values) additionally needs, for the
  VAULT storage class, ``document.vault`` (owner, family admin, document custodian), or
  ``property.documents`` for property categories (property custodian), or an explicit
  ``download`` grant on the document. Researchers and viewers never get vault bytes by default.

Not visible → 404 (existence is not revealed). Visible but no content permission → 403.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import level_allows
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
    if ctx.has(Permission.DOCUMENT_VAULT):
        return True
    return doc.category in PROPERTY_CATEGORIES and ctx.has(Permission.PROPERTY_DOCUMENTS)


def can_view_document(ctx: TreeContext, doc: Document) -> bool:
    if ctx.public or not ctx.is_member:
        return False
    if doc.tree_id != ctx.tree_id:
        return False
    if level_allows(ctx, doc.privacy_level, grant=(GrantResource.DOCUMENT, doc.id)):
        return True
    if doc.privacy_level == PrivacyLevel.PRIVATE_TREE_ADMINS and _custodian_for(ctx, doc):
        return True
    return ctx.user_id is not None and doc.created_by == ctx.user_id


def can_access_content(ctx: TreeContext, doc: Document) -> bool:
    if not can_view_document(ctx, doc):
        return False
    if doc.storage_class != StorageClass.VAULT:
        return True
    if _custodian_for(ctx, doc):
        return True
    return ctx.has_grant(GrantResource.DOCUMENT, doc.id, GrantPermission.DOWNLOAD)


def get_document(ctx: TreeContext, document_id: uuid.UUID, *, include_deleted: bool = False) -> Document:
    doc = ctx.db.scalar(select(Document).where(Document.tree_id == ctx.tree_id, Document.id == document_id))
    if doc is None or (doc.deleted_at is not None and not include_deleted):
        raise NotFound("Document not found")
    if not can_view_document(ctx, doc):
        raise NotFound("Document not found")
    return doc


def require_content(ctx: TreeContext, doc: Document) -> None:
    if not can_access_content(ctx, doc):
        raise Forbidden("You do not have permission to open the contents of this document")
