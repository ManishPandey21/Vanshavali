from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import TreeCtx
from app.api.schemas import Message, Page, decode_cursor, encode_cursor
from app.modules.profile_details import service
from app.modules.profile_details.schemas import (
    AddressIn,
    AddressOut,
    AddressUpdate,
    ContactIn,
    ContactOut,
    ContactReveal,
    ContactUpdate,
    MoveAddressIn,
    MoveAddressOut,
    RevisionSnapshot,
)

router = APIRouter(prefix="/trees/{tree_id}/people/{person_id}", tags=["profile details"])


@router.get("/addresses", response_model=Page[AddressOut])
def list_addresses(
    person_id: uuid.UUID,
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[AddressOut]:
    offset = decode_cursor(cursor)
    rows = service.list_addresses(ctx, person_id, offset=offset, limit=limit + 1)
    return Page(
        items=[service.project_address(row, ctx) for row in rows[:limit]],
        next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None,
    )


@router.post("/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(person_id: uuid.UUID, body: AddressIn, ctx: TreeCtx) -> AddressOut:
    return service.project_address(service.create_address(ctx, person_id, body), ctx)


@router.patch("/addresses/{address_id}", response_model=AddressOut)
def update_address(
    person_id: uuid.UUID, address_id: uuid.UUID, body: AddressUpdate, ctx: TreeCtx
) -> AddressOut:
    return service.project_address(service.update_address(ctx, person_id, address_id, body), ctx)


@router.post("/addresses/{address_id}/move", response_model=MoveAddressOut)
def move_address(
    person_id: uuid.UUID, address_id: uuid.UUID, body: MoveAddressIn, ctx: TreeCtx
) -> MoveAddressOut:
    former, new = service.move_address(ctx, person_id, address_id, body)
    return MoveAddressOut(
        former_address=service.project_address(former, ctx), new_address=service.project_address(new, ctx)
    )


@router.get("/addresses/{address_id}/history", response_model=Page[RevisionSnapshot])
def address_history(
    person_id: uuid.UUID,
    address_id: uuid.UUID,
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[RevisionSnapshot]:
    offset = decode_cursor(cursor)
    rows = service.address_history(ctx, person_id, address_id, offset=offset, limit=limit + 1)
    return Page(
        items=[RevisionSnapshot.model_validate(item) for item in rows[:limit]],
        next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None,
    )


@router.get("/contacts", response_model=Page[ContactOut])
def list_contacts(
    person_id: uuid.UUID,
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[ContactOut]:
    offset = decode_cursor(cursor)
    rows = service.list_contacts(ctx, person_id, offset=offset, limit=limit + 1)
    return Page(
        items=service.project_contacts(ctx, rows[:limit]),
        next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None,
    )


@router.post("/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(person_id: uuid.UUID, body: ContactIn, ctx: TreeCtx) -> ContactOut:
    return service.project_contact(ctx, service.create_contact(ctx, person_id, body))


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    person_id: uuid.UUID, contact_id: uuid.UUID, body: ContactUpdate, ctx: TreeCtx
) -> ContactOut:
    return service.project_contact(ctx, service.update_contact(ctx, person_id, contact_id, body))


@router.get("/contacts/{contact_id}/reveal", response_model=ContactReveal)
def reveal_contact(person_id: uuid.UUID, contact_id: uuid.UUID, ctx: TreeCtx) -> ContactReveal:
    value, profile_url = service.reveal_contact(ctx, person_id, contact_id)
    return ContactReveal(id=contact_id, value=value, profile_url=profile_url)


@router.get("/contacts/{contact_id}/history", response_model=Page[RevisionSnapshot])
def contact_history(
    person_id: uuid.UUID,
    contact_id: uuid.UUID,
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[RevisionSnapshot]:
    offset = decode_cursor(cursor)
    rows = service.contact_history(ctx, person_id, contact_id, offset=offset, limit=limit + 1)
    return Page(
        items=[RevisionSnapshot.model_validate(item) for item in rows[:limit]],
        next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None,
    )


@router.delete("/contacts/{contact_id}", response_model=Message)
def delete_contact(
    person_id: uuid.UUID,
    contact_id: uuid.UUID,
    ctx: TreeCtx,
    revision: int = Query(ge=1),
    reason: str | None = Query(default=None, max_length=500),
) -> Message:
    service.withdraw_contact(ctx, person_id, contact_id, revision, reason)
    return Message(message="Contact method removed")
