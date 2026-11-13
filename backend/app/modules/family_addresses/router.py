from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import TreeCtx
from app.api.schemas import Message, Page, decode_cursor, encode_cursor
from app.modules.family_addresses import service
from app.modules.family_addresses.schemas import (
    ActivateSharingIn,
    AddressReuseIn,
    AffectedAddressOut,
    FamilyAddressCreateIn,
    FamilyAddressGrantIn,
    FamilyAddressGrantOut,
    FamilyAddressOut,
    FamilyAddressSourceOut,
    FamilyAddressVersionIn,
    ReleaseConsentIn,
    ReleaseConsentOut,
    ReleasePreviewOut,
)
from app.modules.profile_details.schemas import AddressOut, AdoptFamilyAddressVersionIn

router = APIRouter(prefix="/trees/{tree_id}", tags=["family addresses"])


@router.get("/family-addresses", response_model=Page[FamilyAddressOut])
def list_family_addresses(
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[FamilyAddressOut]:
    offset = decode_cursor(cursor)
    rows = service.list_family_addresses(ctx)
    page = rows[offset : offset + limit + 1]
    return Page(
        items=[service.project(ctx, row) for row in page[:limit]],
        next_cursor=encode_cursor(offset + limit) if len(page) > limit else None,
    )


@router.get("/family-addresses/sources", response_model=Page[FamilyAddressSourceOut])
def list_sources(
    ctx: TreeCtx,
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[FamilyAddressSourceOut]:
    offset = decode_cursor(cursor)
    rows = service.list_sources(ctx, query=q)
    page = rows[offset : offset + limit + 1]
    return Page(
        items=page[:limit],
        next_cursor=encode_cursor(offset + limit) if len(page) > limit else None,
    )


@router.post("/family-addresses", response_model=FamilyAddressOut, status_code=status.HTTP_201_CREATED)
def create_family_address(body: FamilyAddressCreateIn, ctx: TreeCtx) -> FamilyAddressOut:
    return service.project(ctx, service.create(ctx, body))


@router.get("/family-addresses/{family_address_id}", response_model=FamilyAddressOut)
def get_family_address(family_address_id: uuid.UUID, ctx: TreeCtx) -> FamilyAddressOut:
    row = service.get(ctx, family_address_id)
    return service.project(ctx, row)


@router.post("/family-addresses/{family_address_id}/versions", response_model=FamilyAddressOut)
def create_family_address_version(
    family_address_id: uuid.UUID, body: FamilyAddressVersionIn, ctx: TreeCtx
) -> FamilyAddressOut:
    return service.project(ctx, service.create_version(ctx, family_address_id, body))


@router.get("/family-addresses/{family_address_id}/affected", response_model=Page[AffectedAddressOut])
def affected_addresses(
    family_address_id: uuid.UUID,
    target_version: int,
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[AffectedAddressOut]:
    offset = decode_cursor(cursor)
    rows = service.affected(ctx, family_address_id, target_version)
    page = rows[offset : offset + limit + 1]
    return Page(
        items=page[:limit],
        next_cursor=encode_cursor(offset + limit) if len(page) > limit else None,
    )


@router.delete("/family-addresses/{family_address_id}", response_model=Message)
def retire_family_address(family_address_id: uuid.UUID, ctx: TreeCtx, revision: int = Query(ge=1)) -> Message:
    service.retire(ctx, family_address_id, revision)
    return Message(message="Family address retired")


@router.post(
    "/family-addresses/{family_address_id}/release-consents",
    response_model=ReleaseConsentOut,
    status_code=status.HTTP_201_CREATED,
)
def consent_to_release(
    family_address_id: uuid.UUID, body: ReleaseConsentIn, ctx: TreeCtx
) -> ReleaseConsentOut:
    return service.project_consent(service.give_release_consent(ctx, family_address_id, body))


@router.post(
    "/family-addresses/{family_address_id}/release-preview",
    response_model=ReleasePreviewOut,
)
def preview_release(family_address_id: uuid.UUID, body: ReleaseConsentIn, ctx: TreeCtx) -> ReleasePreviewOut:
    return service.preview_release(ctx, family_address_id, body)


@router.delete("/family-addresses/release-consents/{consent_id}", response_model=Message)
def withdraw_release_consent(consent_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.withdraw_consent(ctx, consent_id)
    return Message(message="Release consent withdrawn")


@router.post("/family-addresses/{family_address_id}/activate-sharing", response_model=FamilyAddressOut)
def activate_sharing(family_address_id: uuid.UUID, body: ActivateSharingIn, ctx: TreeCtx) -> FamilyAddressOut:
    return service.project(ctx, service.activate_sharing(ctx, family_address_id, body))


@router.get("/family-addresses/{family_address_id}/grants", response_model=Page[FamilyAddressGrantOut])
def list_family_address_grants(
    family_address_id: uuid.UUID,
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[FamilyAddressGrantOut]:
    offset = decode_cursor(cursor)
    rows = service.list_grants(ctx, family_address_id)
    page = rows[offset : offset + limit + 1]
    return Page(
        items=page[:limit],
        next_cursor=encode_cursor(offset + limit) if len(page) > limit else None,
    )


@router.post(
    "/family-addresses/{family_address_id}/grants",
    response_model=FamilyAddressGrantOut,
    status_code=status.HTTP_201_CREATED,
)
def grant_family_address_access(
    family_address_id: uuid.UUID, body: FamilyAddressGrantIn, ctx: TreeCtx
) -> FamilyAddressGrantOut:
    return service.grant_access(ctx, family_address_id, body)


@router.delete("/family-addresses/{family_address_id}/grants/{grant_id}", response_model=Message)
def revoke_family_address_access(family_address_id: uuid.UUID, grant_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.revoke_grant(ctx, family_address_id, grant_id)
    return Message(message="Family address grant revoked")


@router.post(
    "/people/{person_id}/addresses/reuse", response_model=AddressOut, status_code=status.HTTP_201_CREATED
)
def reuse_address(person_id: uuid.UUID, body: AddressReuseIn, ctx: TreeCtx) -> AddressOut:
    return service.project_person_address(ctx, service.reuse(ctx, person_id, body))


@router.post("/people/{person_id}/addresses/{address_id}/adopt-family-version", response_model=AddressOut)
def adopt_family_version(
    person_id: uuid.UUID,
    address_id: uuid.UUID,
    body: AdoptFamilyAddressVersionIn,
    ctx: TreeCtx,
) -> AddressOut:
    return service.project_person_address(ctx, service.adopt(ctx, person_id, address_id, body))


@router.delete("/people/{person_id}/addresses/{address_id}", response_model=Message)
def delete_address(
    person_id: uuid.UUID,
    address_id: uuid.UUID,
    ctx: TreeCtx,
    revision: int = Query(ge=1),
    reason: str | None = Query(default=None, max_length=500),
) -> Message:
    service.withdraw_person_address(ctx, person_id, address_id, revision, reason)
    return Message(message="Address removed")
