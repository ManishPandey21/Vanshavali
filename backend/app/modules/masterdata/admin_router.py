"""Super Admin master-data console API (ADR-0025). Every handler depends on ``MasterDataAdmin``:
system admins with two-step sign-in only; everyone else gets 404."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import MasterDataAdmin
from app.models.enums import VocabularyChangeStatus, VocabularyTermManagedBy, VocabularyTermStatus
from app.modules.masterdata import admin
from app.modules.masterdata.admin_schemas import (
    AdminTermDetailOut,
    AdminTermPage,
    AdminVocabularyOut,
    MasterDataChangeIn,
    MasterDataChangeOut,
    MasterDataChangePage,
    MasterDataDecisionIn,
    MasterDataRejectIn,
    VocabularyDuplicateCheckIn,
    VocabularyDuplicateOut,
)

router = APIRouter(prefix="/admin/master-data", tags=["master-data-admin"])


@router.get("/vocabularies", response_model=list[AdminVocabularyOut])
def list_vocabularies(ctx: MasterDataAdmin) -> list[AdminVocabularyOut]:
    """Every global vocabulary with term counts per status and pending changes."""
    return admin.list_vocabularies(ctx)


@router.get("/vocabularies/{key}/terms", response_model=AdminTermPage)
def list_terms(
    key: str,
    ctx: MasterDataAdmin,
    q: str = Query(default="", max_length=100),
    term_status: VocabularyTermStatus | None = Query(default=None, alias="status"),
    managed_by: VocabularyTermManagedBy | None = None,
    sort: str = Query(default="order", pattern="^(order|code|updated)$"),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> AdminTermPage:
    """Global terms, retired included, searchable by code, label (any script) or alias."""
    return admin.list_terms(
        ctx, key, q=q, status=term_status, managed_by=managed_by, sort=sort, cursor=cursor, limit=limit
    )


@router.get("/vocabularies/{key}/terms/{code}", response_model=AdminTermDetailOut)
def term_detail(key: str, code: str, ctx: MasterDataAdmin) -> AdminTermDetailOut:
    """One term with its full change history."""
    return admin.term_detail(ctx, key, code)


@router.post("/vocabularies/{key}/duplicates", response_model=list[VocabularyDuplicateOut])
def check_duplicates(
    key: str, body: VocabularyDuplicateCheckIn, ctx: MasterDataAdmin
) -> list[VocabularyDuplicateOut]:
    """Existing terms (retired included) a new label or alias would duplicate. Writes nothing."""
    return admin.check_duplicates(ctx, key, body.labels, body.aliases, body.exclude_code)


@router.post(
    "/vocabularies/{key}/changes", response_model=MasterDataChangeOut, status_code=status.HTTP_201_CREATED
)
def propose(key: str, body: MasterDataChangeIn, ctx: MasterDataAdmin) -> MasterDataChangeOut:
    """Propose a change to one term (create, update, retire, reactivate); ``publish`` applies it at once."""
    return admin.propose(ctx, key, body)


@router.get("/changes", response_model=MasterDataChangePage)
def list_changes(
    ctx: MasterDataAdmin,
    change_status: VocabularyChangeStatus | None = Query(default=None, alias="status"),
    vocabulary: str | None = Query(default=None, max_length=40),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> MasterDataChangePage:
    """Pending reviews (``status=pending``) and the change history, newest first."""
    return admin.list_changes(ctx, status=change_status, vocabulary=vocabulary, cursor=cursor, limit=limit)


@router.get("/changes/{change_id}", response_model=MasterDataChangeOut)
def get_change(change_id: uuid.UUID, ctx: MasterDataAdmin) -> MasterDataChangeOut:
    return admin.get_change(ctx, change_id)


@router.post("/changes/{change_id}/publish", response_model=MasterDataChangeOut)
def publish(change_id: uuid.UUID, body: MasterDataDecisionIn, ctx: MasterDataAdmin) -> MasterDataChangeOut:
    """Apply a pending change. Refused (409) if the term moved on since the change was prepared."""
    return admin.publish(ctx, change_id, body.note)


@router.post("/changes/{change_id}/reject", response_model=MasterDataChangeOut)
def reject(change_id: uuid.UUID, body: MasterDataRejectIn, ctx: MasterDataAdmin) -> MasterDataChangeOut:
    return admin.reject(ctx, change_id, body.note)


@router.post("/changes/{change_id}/withdraw", response_model=MasterDataChangeOut)
def withdraw(change_id: uuid.UUID, ctx: MasterDataAdmin) -> MasterDataChangeOut:
    """The proposer takes back a pending change."""
    return admin.withdraw(ctx, change_id)
