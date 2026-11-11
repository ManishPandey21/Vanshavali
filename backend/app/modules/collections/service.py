"""Standalone photo collections (ADR-0027 §6, increment 4).

* A collection is a shareable record: Only me (the default), Selected members, Selected branch or
  All family members; never public. Its owner is the creator's membership.
* Its items are photos from the vault. Adding a photo never changes who can see the photo: a viewer
  sees an item only when they may see the collection **and** the photo, and counts and the cover
  are computed for each viewer.
* Only the owner changes the contents. Admins may only narrow a shared collection (§10).
* The owner is told which photos part of the collection's audience cannot see (§6).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission, permissions_for
from app.authz.privacy import is_record_owner, record_allows
from app.core import audit
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models import (
    AccessGrant,
    Document,
    FamilyBranch,
    PhotoCollection,
    PhotoCollectionItem,
    TreeMembership,
)
from app.models.enums import DocumentCategory, GrantResource, RecordPrivacyLevel, Role
from app.modules.collections.schemas import (
    CollectionIn,
    CollectionItemIn,
    CollectionItemOut,
    CollectionItemUpdate,
    CollectionOut,
    CollectionSummaryOut,
    CollectionUpdate,
)
from app.modules.documents import access
from app.modules.documents import service as documents
from app.modules.sharing import core
from app.modules.sharing.core import Proposal

MAX_ITEMS = 500
L = RecordPrivacyLevel


# ---------------------------------------------------------------- access
def collection_allows(
    ctx: TreeContext,
    c: PhotoCollection,
    level: RecordPrivacyLevel | str | None = None,
    branch_id: uuid.UUID | None = None,
) -> bool:
    """Can the viewer see the collection (at its own setting, or at a proposed one)?"""
    if ctx.public or not ctx.is_member or c.tree_id != ctx.tree_id:
        return False
    if c.suspended_at is not None:
        return is_record_owner(ctx, c.owner_membership_id)  # ADR-0027 §8.2
    proposed = level is not None
    effective = L(level) if level is not None else L(c.privacy_level)
    branch = branch_id if proposed else c.audience_branch_id
    return record_allows(
        ctx,
        effective,
        owner_membership_id=c.owner_membership_id,
        audience_branch_id=branch if effective == L.FAMILY_BRANCH else None,
        grant=(GrantResource.COLLECTION, c.id),
    )


def is_owner(ctx: TreeContext, c: PhotoCollection) -> bool:
    return is_record_owner(ctx, c.owner_membership_id)


class CollectionRecord(core.RecordAdapter):
    resource = GrantResource.COLLECTION
    audit_type = "collection"
    supports_download = False  # downloads belong to each photo
    record: PhotoCollection

    def audience_branch(self) -> uuid.UUID | None:
        return self.record.audience_branch_id if self.level == L.FAMILY_BRANCH else None

    def allow_download(self) -> bool:
        return False

    def linked_people(self, ctx: TreeContext) -> list[uuid.UUID]:
        return []  # the photos carry their own ceilings; the collection does not tag anyone

    def can_view(self, mctx: TreeContext, p: Proposal) -> bool:
        return collection_allows(mctx, self.record, p.privacy_level, p.audience_branch_id)

    def manager_may_narrow(self, ctx: TreeContext) -> bool:
        return ctx.is_admin

    def store(self, ctx: TreeContext, p: Proposal) -> None:
        self.record.privacy_level = p.privacy_level
        self.record.audience_branch_id = p.audience_branch_id


def get_collection(ctx: TreeContext, collection_id: uuid.UUID) -> PhotoCollection:
    c = ctx.db.scalar(
        select(PhotoCollection).where(
            PhotoCollection.tree_id == ctx.tree_id, PhotoCollection.id == collection_id
        )
    )
    if c is None or not collection_allows(ctx, c):
        raise NotFound("Collection not found")
    return c


def _require_owner(ctx: TreeContext, c: PhotoCollection) -> None:
    if not is_owner(ctx, c):
        raise Forbidden("Only the owner of this collection can change it")


# ---------------------------------------------------------------- reading
def _items(ctx: TreeContext, collection_ids: list[uuid.UUID]) -> list[tuple[PhotoCollectionItem, Document]]:
    if not collection_ids:
        return []
    rows = ctx.db.execute(
        select(PhotoCollectionItem, Document)
        .join(
            Document,
            (Document.id == PhotoCollectionItem.document_id)
            & (Document.tree_id == PhotoCollectionItem.tree_id),
        )
        .where(
            PhotoCollectionItem.tree_id == ctx.tree_id,
            PhotoCollectionItem.collection_id.in_(collection_ids),
            Document.deleted_at.is_(None),
        )
        .order_by(PhotoCollectionItem.sort_order, PhotoCollectionItem.created_at)
    ).all()
    # each viewer sees only the photos they may see (ADR-0027 §6)
    return [(i, d) for i, d in rows if access.can_view_document(ctx, d)]


def _summary(
    ctx: TreeContext, c: PhotoCollection, visible: list[tuple[PhotoCollectionItem, Document]]
) -> CollectionSummaryOut:
    cover = next((d.id for i, d in visible if i.is_cover), None) or (visible[0][1].id if visible else None)
    return CollectionSummaryOut(
        id=c.id,
        title=c.title,
        description=c.description,
        privacy_level=L(c.privacy_level),
        item_count=len(visible),
        cover_document_id=cover,
        is_owner=is_owner(ctx, c),
        can_edit_sharing=CollectionRecord(c).can_edit(ctx),
        updated_at=c.updated_at,
    )


def list_collections(ctx: TreeContext) -> list[CollectionSummaryOut]:
    ctx.require(Permission.TREE_READ)
    rows = [
        c
        for c in ctx.db.scalars(
            select(PhotoCollection)
            .where(PhotoCollection.tree_id == ctx.tree_id)
            .order_by(PhotoCollection.updated_at.desc(), PhotoCollection.id)
        )
        if collection_allows(ctx, c)
    ]
    items = _items(ctx, [c.id for c in rows])
    by: dict[uuid.UUID, list[tuple[PhotoCollectionItem, Document]]] = {c.id: [] for c in rows}
    for i, d in items:
        by[i.collection_id].append((i, d))
    return [_summary(ctx, c, by[c.id]) for c in rows]


def _audience_contexts(ctx: TreeContext, c: PhotoCollection) -> list[TreeContext]:
    """A context for every member who can see the collection now, with their real grants."""
    out = []
    for m in ctx.db.scalars(select(TreeMembership).where(TreeMembership.tree_id == ctx.tree_id)):
        roles = frozenset(Role(r) for r in m.roles)
        mctx = TreeContext(
            db=ctx.db, tree=ctx.tree, user=None, membership=m, roles=roles, permissions=permissions_for(roles)
        )
        mctx.user = core._Stub(m.user_id)  # type: ignore[assignment]
        if collection_allows(mctx, c):
            out.append(mctx)
    return out


def collection_out(ctx: TreeContext, c: PhotoCollection) -> CollectionOut:
    visible = _items(ctx, [c.id])
    owner = is_owner(ctx, c)
    audience = _audience_contexts(ctx, c) if owner else []
    links = documents.links_for(ctx, [d.id for _, d in visible])
    items = []
    not_shared = 0
    for i, d in visible:
        shared = None
        if owner:
            shared = all(access.can_view_document(m, d) for m in audience)
            not_shared += 0 if shared else 1
        items.append(
            CollectionItemOut(
                id=i.id,
                document_id=d.id,
                caption=i.caption,
                is_cover=i.is_cover,
                sort_order=i.sort_order,
                document=documents.document_out(ctx, d, links[d.id]),
                shared_with_collection_audience=shared,
            )
        )
    return CollectionOut(
        **_summary(ctx, c, visible).model_dump(), items=items, items_not_shared=not_shared if owner else None
    )


# ---------------------------------------------------------------- writing
def create_collection(ctx: TreeContext, body: CollectionIn) -> PhotoCollection:
    ctx.require(Permission.DOCUMENT_UPLOAD)  # members who add photos keep collections of them
    level = L(body.privacy_level)
    if level == L.PUBLIC_DECEASED_ONLY:
        raise Unprocessable("Collections cannot be public", code="public_not_supported")
    if level not in core.CHOOSABLE:
        raise Unprocessable(
            "Choose Only me, Selected members, Selected branch or All family members", code="legacy_level"
        )
    branch = body.audience_branch_id if level == L.FAMILY_BRANCH else None
    if level == L.FAMILY_BRANCH:
        if branch is None:
            raise Unprocessable("Choose the family branch to share with", code="branch_required")
        if (
            ctx.db.scalar(
                select(FamilyBranch.id).where(FamilyBranch.tree_id == ctx.tree_id, FamilyBranch.id == branch)
            )
            is None
        ):
            raise NotFound("Branch not found")
    c = PhotoCollection(
        tree_id=ctx.tree_id,
        title=body.title.strip(),
        description=body.description,
        privacy_level=level,
        audience_branch_id=branch,
        owner_membership_id=ctx.membership_id,
        created_by=ctx.user_id,
    )
    ctx.db.add(c)
    ctx.db.flush()
    audit.log(
        ctx, "collection.created", target_type="collection", target_id=c.id, details={"level": level.value}
    )
    return c


def update_collection(ctx: TreeContext, collection_id: uuid.UUID, body: CollectionUpdate) -> PhotoCollection:
    c = get_collection(ctx, collection_id)
    _require_owner(ctx, c)
    fields = body.model_fields_set
    if "title" in fields and body.title is not None:
        c.title = body.title.strip()
    if "description" in fields:
        c.description = body.description
    c.updated_by = ctx.user_id
    ctx.db.flush()
    audit.log(
        ctx,
        "collection.changed",
        target_type="collection",
        target_id=c.id,
        details={"fields": sorted(fields)},
    )
    return c


def delete_collection(ctx: TreeContext, collection_id: uuid.UUID) -> None:
    """Delete the collection; its photos stay in the vault with their own audience."""
    c = get_collection(ctx, collection_id)
    _require_owner(ctx, c)
    for g in ctx.db.scalars(
        select(AccessGrant).where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.resource_type == GrantResource.COLLECTION,
            AccessGrant.resource_id == c.id,
        )
    ):
        ctx.db.delete(g)
    ctx.db.delete(c)  # items cascade
    ctx.db.flush()
    audit.log(ctx, "collection.deleted", target_type="collection", target_id=collection_id)


def _count(ctx: TreeContext, collection_id: uuid.UUID) -> int:
    return int(
        ctx.db.scalar(
            select(func.count())
            .select_from(PhotoCollectionItem)
            .where(
                PhotoCollectionItem.tree_id == ctx.tree_id, PhotoCollectionItem.collection_id == collection_id
            )
        )
        or 0
    )


def _set_cover(ctx: TreeContext, c: PhotoCollection, item: PhotoCollectionItem) -> None:
    for other in ctx.db.scalars(
        select(PhotoCollectionItem).where(
            PhotoCollectionItem.tree_id == ctx.tree_id,
            PhotoCollectionItem.collection_id == c.id,
            PhotoCollectionItem.id != item.id,
            PhotoCollectionItem.is_cover.is_(True),
        )
    ):
        other.is_cover = False
    item.is_cover = True


def add_item(ctx: TreeContext, collection_id: uuid.UUID, body: CollectionItemIn) -> PhotoCollectionItem:
    c = get_collection(ctx, collection_id)
    _require_owner(ctx, c)
    doc = access.get_document(ctx, body.document_id)  # only photos the owner can see (404 otherwise)
    if doc.category != DocumentCategory.PHOTO or not doc.mime_type.startswith("image/"):
        raise Unprocessable("Only photos can be added to a collection", code="not_an_image")
    n = _count(ctx, c.id)
    if n >= MAX_ITEMS:
        raise Unprocessable(f"A collection holds at most {MAX_ITEMS} photos", code="collection_full")
    exists = ctx.db.scalar(
        select(PhotoCollectionItem.id).where(
            PhotoCollectionItem.tree_id == ctx.tree_id,
            PhotoCollectionItem.collection_id == c.id,
            PhotoCollectionItem.document_id == doc.id,
        )
    )
    if exists is not None:
        raise Conflict("This photo is already in the collection", code="duplicate_item")
    item = PhotoCollectionItem(
        tree_id=ctx.tree_id,
        collection_id=c.id,
        document_id=doc.id,
        caption=(body.caption or "").strip() or None,
        sort_order=n,
        created_by=ctx.user_id,
    )
    ctx.db.add(item)
    ctx.db.flush()
    if body.is_cover or n == 0:
        _set_cover(ctx, c, item)
    c.updated_by = ctx.user_id
    ctx.db.flush()
    # ids only: never the photo's title or the collection's
    audit.log(
        ctx,
        "collection.photo_added",
        target_type="collection",
        target_id=c.id,
        details={"document_id": str(doc.id)},
    )
    return item


def _get_item(ctx: TreeContext, c: PhotoCollection, item_id: uuid.UUID) -> PhotoCollectionItem:
    item = ctx.db.scalar(
        select(PhotoCollectionItem).where(
            PhotoCollectionItem.tree_id == ctx.tree_id,
            PhotoCollectionItem.collection_id == c.id,
            PhotoCollectionItem.id == item_id,
        )
    )
    if item is None:
        raise NotFound("Photo not found")
    access.get_document(ctx, item.document_id)  # a photo the owner can no longer see → 404
    return item


def update_item(
    ctx: TreeContext, collection_id: uuid.UUID, item_id: uuid.UUID, body: CollectionItemUpdate
) -> PhotoCollectionItem:
    c = get_collection(ctx, collection_id)
    _require_owner(ctx, c)
    item = _get_item(ctx, c, item_id)
    if "caption" in body.model_fields_set:
        item.caption = (body.caption or "").strip() or None
    if body.is_cover:
        _set_cover(ctx, c, item)
    elif body.is_cover is False:
        item.is_cover = False
    ctx.db.flush()
    return item


def remove_item(ctx: TreeContext, collection_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Take a photo out of the collection. The photo stays in the vault."""
    c = get_collection(ctx, collection_id)
    _require_owner(ctx, c)
    item = _get_item(ctx, c, item_id)
    doc_id = item.document_id
    ctx.db.delete(item)
    ctx.db.flush()
    audit.log(
        ctx,
        "collection.photo_removed",
        target_type="collection",
        target_id=c.id,
        details={"document_id": str(doc_id)},
    )


# ---------------------------------------------------------------- search and export (increment 5)
def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_collections(ctx: TreeContext, q: str, limit: int) -> list[Any]:
    """Search provider: collections whose title or description matches and that the caller may see.
    A collection the caller may not see is never a hit, and nothing about its photos is returned."""
    from app.modules.search.schemas import SearchHit

    if ctx.public or not ctx.is_member or not q.strip():
        return []
    pattern = f"%{_escape_like(q.strip())}%"
    rows = ctx.db.scalars(
        select(PhotoCollection)
        .where(
            PhotoCollection.tree_id == ctx.tree_id,
            or_(
                PhotoCollection.title.ilike(pattern, escape="\\"),
                PhotoCollection.description.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(PhotoCollection.updated_at.desc(), PhotoCollection.id)
        .limit(limit * 3)
    ).all()
    hits = []
    for c in rows:
        if not collection_allows(ctx, c):
            continue
        exact = c.title.strip().lower() == q.strip().lower()
        in_title = q.strip().lower() in c.title.lower()
        hits.append(
            SearchHit(
                kind="collection",
                id=c.id,
                title=c.title,
                subtitle=None,
                score=0.75 if exact else (0.6 if in_title else 0.45),
                match_tier="exact" if exact else "contains",
                match_reason=(
                    f'collection title {"is" if exact else "contains"} "{q}"'
                    if in_title
                    else f'collection description contains "{q}"'
                ),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def export_collections(ctx: TreeContext, listed_document_ids: set[str]) -> list[dict[str, Any]]:
    """Collections for the archive export, from the exporter's view (ADR-0027 §4, §6).

    Only collections the exporter may see, and in each only the photos they may see. Items refer to
    photos by id in ``documents/index.json``; whether a photo's bytes are in the export is decided
    there by the download rule, never here.
    """
    rows = [
        c
        for c in ctx.db.scalars(
            select(PhotoCollection)
            .where(PhotoCollection.tree_id == ctx.tree_id)
            .order_by(PhotoCollection.created_at)
        )
        if collection_allows(ctx, c)
    ]
    items = _items(ctx, [c.id for c in rows])
    by: dict[uuid.UUID, list[dict[str, Any]]] = {c.id: [] for c in rows}
    for i, d in items:
        by[i.collection_id].append(
            {
                "document_id": str(d.id),
                "caption": i.caption,
                "is_cover": i.is_cover,
                "sort_order": i.sort_order,
                "in_documents_index": str(d.id) in listed_document_ids,
            }
        )
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "description": c.description,
            "privacy_level": L(c.privacy_level).value,
            "items": by[c.id],
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in rows
    ]
