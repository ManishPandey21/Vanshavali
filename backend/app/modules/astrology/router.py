from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.modules.astrology import conflicts, service
from app.modules.astrology.schemas import AstrologyIn, AstrologyOut, AstrologyUpdate, BirthConflictsOut

router = APIRouter(prefix="/trees/{tree_id}", tags=["astrology"])


@router.get("/people/{person_id}/astrology", response_model=list[AstrologyOut])
def list_profiles(person_id: uuid.UUID, ctx: TreeCtx) -> list[AstrologyOut]:
    return service.list_profiles(ctx, person_id)


@router.post(
    "/people/{person_id}/astrology", response_model=AstrologyOut, status_code=status.HTTP_201_CREATED
)
def create_profile(person_id: uuid.UUID, body: AstrologyIn, ctx: TreeCtx) -> AstrologyOut:
    # the writer sees what they just entered, even if the field group is otherwise hidden to them
    return service.profile_out(ctx, service.create_profile(ctx, person_id, body))


@router.get("/astrology/{profile_id}", response_model=AstrologyOut)
def get_profile(profile_id: uuid.UUID, ctx: TreeCtx) -> AstrologyOut:
    prof, _ = service.get_profile(ctx, profile_id)
    return service.profile_out(ctx, prof)


@router.patch("/astrology/{profile_id}", response_model=AstrologyOut)
def update_profile(profile_id: uuid.UUID, body: AstrologyUpdate, ctx: TreeCtx) -> AstrologyOut:
    return service.profile_out(ctx, service.update_profile(ctx, profile_id, body))


@router.delete("/astrology/{profile_id}", response_model=Message)
def delete_profile(profile_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_profile(ctx, profile_id)
    return Message(message="Astrology profile removed")


@router.get("/people/{person_id}/birth-conflicts", response_model=BirthConflictsOut)
def birth_conflicts(person_id: uuid.UUID, ctx: TreeCtx) -> BirthConflictsOut:
    """All birth claims (events + chart details) with provenance, and where they disagree."""
    return conflicts.birth_conflicts(ctx, person_id)
