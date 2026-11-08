"""Relationship words (ADR-0026 §6): packs, the reader's preference and a family's own words."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbDep, TreeCtx
from app.api.schemas import Message
from app.modules.kinship import service
from app.modules.kinship.schemas import (
    KinshipOverrideIn,
    KinshipOverrideOut,
    KinshipPackOut,
    KinshipPreferenceIn,
    KinshipPreferenceOut,
)

router = APIRouter(tags=["kinship"])


@router.get("/kinship/packs", response_model=list[KinshipPackOut])
def kinship_packs(user: CurrentUser) -> list[KinshipPackOut]:
    """Packs of relationship words a reader may choose (reviewed ones; drafts for reviewers)."""
    return service.pack_list(user)


@router.put("/me/kinship-preference", response_model=KinshipPreferenceOut)
def set_kinship_preference(body: KinshipPreferenceIn, user: CurrentUser, db: DbDep) -> KinshipPreferenceOut:
    """Which relationship words this reader sees, in every tree; null follows the tree's default."""
    service.set_preference(db, user, body.lang, body.region)
    return KinshipPreferenceOut(lang=user.kinship_lang, region=user.kinship_region)


@router.get("/trees/{tree_id}/kinship-overrides", response_model=list[KinshipOverrideOut])
def list_kinship_overrides(ctx: TreeCtx) -> list[KinshipOverrideOut]:
    """The family's own words for relationships ("Bhayo" for bhabhi)."""
    return service.list_overrides(ctx)


@router.put("/trees/{tree_id}/kinship-overrides", response_model=KinshipOverrideOut)
def put_kinship_override(body: KinshipOverrideIn, ctx: TreeCtx) -> KinshipOverrideOut:
    """Record the family's word for a relationship, tree-wide or for one branch (family.write;
    under family review when the tree reviews all changes)."""
    return KinshipOverrideOut.model_validate(service.put_override(ctx, body))


@router.delete("/trees/{tree_id}/kinship-overrides/{override_id}", response_model=Message)
def delete_kinship_override(override_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_override(ctx, override_id)
    return Message(message="Family word removed")
