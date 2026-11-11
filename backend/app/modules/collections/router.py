"""Standalone photo collections (ADR-0027 §6). Members only; never public."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.modules.collections import service
from app.modules.collections.schemas import (
    CollectionIn,
    CollectionItemIn,
    CollectionItemUpdate,
    CollectionOut,
    CollectionSummaryOut,
    CollectionUpdate,
)
from app.modules.search import providers
from app.modules.sharing import core
from app.modules.sharing.schemas import SharingOut, SharingUpdate

router = APIRouter(prefix="/trees/{tree_id}", tags=["collections"])
providers.register("collection", service.search_collections)


@router.get("/collections", response_model=list[CollectionSummaryOut])
def list_collections(ctx: TreeCtx) -> list[CollectionSummaryOut]:
    """Collections the caller may see; counts and covers use only the photos they may see."""
    return service.list_collections(ctx)


@router.post("/collections", response_model=CollectionOut, status_code=status.HTTP_201_CREATED)
def create_collection(body: CollectionIn, ctx: TreeCtx) -> CollectionOut:
    return service.collection_out(ctx, service.create_collection(ctx, body))


@router.get("/collections/{collection_id}", response_model=CollectionOut)
def get_collection(collection_id: uuid.UUID, ctx: TreeCtx) -> CollectionOut:
    return service.collection_out(ctx, service.get_collection(ctx, collection_id))


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
def update_collection(collection_id: uuid.UUID, body: CollectionUpdate, ctx: TreeCtx) -> CollectionOut:
    return service.collection_out(ctx, service.update_collection(ctx, collection_id, body))


@router.delete("/collections/{collection_id}", response_model=Message)
def delete_collection(collection_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_collection(ctx, collection_id)
    return Message(message="Collection deleted; its photos stay in the vault")


@router.post(
    "/collections/{collection_id}/items", response_model=CollectionOut, status_code=status.HTTP_201_CREATED
)
def add_item(collection_id: uuid.UUID, body: CollectionItemIn, ctx: TreeCtx) -> CollectionOut:
    service.add_item(ctx, collection_id, body)
    return service.collection_out(ctx, service.get_collection(ctx, collection_id))


@router.patch("/collections/{collection_id}/items/{item_id}", response_model=CollectionOut)
def update_item(
    collection_id: uuid.UUID, item_id: uuid.UUID, body: CollectionItemUpdate, ctx: TreeCtx
) -> CollectionOut:
    service.update_item(ctx, collection_id, item_id, body)
    return service.collection_out(ctx, service.get_collection(ctx, collection_id))


@router.delete("/collections/{collection_id}/items/{item_id}", response_model=Message)
def remove_item(collection_id: uuid.UUID, item_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.remove_item(ctx, collection_id, item_id)
    return Message(message="Photo removed from the collection; it stays in the vault")


# ---------------------------------------------------------------- Visibility & Sharing (ADR-0027)
@router.get("/collections/{collection_id}/sharing", response_model=SharingOut)
def get_sharing(collection_id: uuid.UUID, ctx: TreeCtx) -> SharingOut:
    return core.sharing_out(ctx, service.CollectionRecord(service.get_collection(ctx, collection_id)))


@router.put("/collections/{collection_id}/sharing", response_model=SharingOut)
def update_sharing(collection_id: uuid.UUID, body: SharingUpdate, ctx: TreeCtx) -> SharingOut:
    """Who can see the collection. Its photos keep their own audience (ADR-0027 §6)."""
    rec = service.CollectionRecord(service.get_collection(ctx, collection_id))
    core.require_editable(ctx, rec)
    core.apply(ctx, rec, core.proposal(ctx, rec, body), confirm_wider=body.confirm_wider)
    return core.sharing_out(ctx, rec)


@router.post("/collections/{collection_id}/sharing/preview", response_model=SharingOut)
def preview_sharing(collection_id: uuid.UUID, body: SharingUpdate, ctx: TreeCtx) -> SharingOut:
    rec = service.CollectionRecord(service.get_collection(ctx, collection_id))
    core.require_editable(ctx, rec)
    return core.sharing_out(ctx, rec, core.proposal(ctx, rec, body))
