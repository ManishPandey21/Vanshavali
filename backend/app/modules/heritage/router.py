from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.models.enums import AssertionSubject
from app.modules.heritage import service
from app.modules.heritage.schemas import AssertionIn, AssertionOut, AssertionUpdate, HeritageProfileOut

router = APIRouter(prefix="/trees/{tree_id}", tags=["heritage"])


def _one(ctx, a) -> AssertionOut:  # type: ignore[no-untyped-def]
    prof = service.profile(ctx, a.subject_type, a.person_id or a.branch_id)
    for v in prof.attributes:
        for item in ([v.preferred] if v.preferred else []) + v.alternatives:
            if item.id == a.id:
                return item
    return AssertionOut.model_validate(a)


@router.get("/people/{person_id}/heritage", response_model=HeritageProfileOut)
def person_heritage(person_id: uuid.UUID, ctx: TreeCtx) -> HeritageProfileOut:
    return service.profile(ctx, AssertionSubject.PERSON, person_id)


@router.post("/people/{person_id}/heritage", response_model=AssertionOut, status_code=status.HTTP_201_CREATED)
def add_person_assertion(person_id: uuid.UUID, body: AssertionIn, ctx: TreeCtx) -> AssertionOut:
    return _one(ctx, service.create_assertion(ctx, AssertionSubject.PERSON, person_id, body))


@router.get("/branches/{branch_id}/heritage", response_model=HeritageProfileOut)
def branch_heritage(branch_id: uuid.UUID, ctx: TreeCtx) -> HeritageProfileOut:
    return service.profile(ctx, AssertionSubject.BRANCH, branch_id)


@router.post(
    "/branches/{branch_id}/heritage", response_model=AssertionOut, status_code=status.HTTP_201_CREATED
)
def add_branch_assertion(branch_id: uuid.UUID, body: AssertionIn, ctx: TreeCtx) -> AssertionOut:
    return _one(ctx, service.create_assertion(ctx, AssertionSubject.BRANCH, branch_id, body))


@router.patch("/assertions/{assertion_id}", response_model=AssertionOut)
def update_assertion(assertion_id: uuid.UUID, body: AssertionUpdate, ctx: TreeCtx) -> AssertionOut:
    return _one(ctx, service.update_assertion(ctx, assertion_id, body))


@router.delete("/assertions/{assertion_id}", response_model=Message)
def delete_assertion(assertion_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_assertion(ctx, assertion_id)
    return Message(message="Assertion removed")
