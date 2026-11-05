from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.modules.genealogy import lookup
from app.modules.genealogy.serialize import Serializer, relationship_out
from app.modules.smartadd import service
from app.modules.smartadd.schemas import (
    SmartAddCommitIn,
    SmartAddCommitOut,
    SmartAddPlanIn,
    SmartAddPlanOut,
    SmartAddTermOut,
)

router = APIRouter(prefix="/trees/{tree_id}", tags=["smart-add"])


@router.get("/smart-add/terms", response_model=list[SmartAddTermOut])
def list_terms(ctx: TreeCtx) -> list[SmartAddTermOut]:
    """Kinship terms Smart Add understands, each as a path of basic edges (ADR-0020)."""
    return service.list_terms()


@router.post("/people/{person_id}/smart-add/plan", response_model=SmartAddPlanOut)
def plan(person_id: uuid.UUID, body: SmartAddPlanIn, ctx: TreeCtx) -> SmartAddPlanOut:
    """Preview: candidates for each step and every record that would be created. Writes nothing."""
    return service.plan(ctx, person_id, body)


@router.post(
    "/people/{person_id}/smart-add", response_model=SmartAddCommitOut, status_code=status.HTTP_201_CREATED
)
def commit(person_id: uuid.UUID, body: SmartAddCommitIn, ctx: TreeCtx) -> SmartAddCommitOut:
    """Create the confirmed plan in one transaction; returns an operation id for undo."""
    event, target, written = service.commit(ctx, person_id, body)
    subjects = lookup.visible_subjects(ctx, written.people)
    summaries = Serializer(ctx).summaries(subjects)
    rels = [lookup.get_relationship(ctx, r) for r in written.relationships]
    return SmartAddCommitOut(
        operation_id=event.id,
        person=summaries[target.id],
        created_people=[summaries[p] for p in written.people if p in summaries],
        relationships=[relationship_out(r) for r in rels],
        relative_age_order_ids=written.age_orders,
        undo_expires_in_seconds=int(service.UNDO_WINDOW.total_seconds()),
    )


@router.post("/smart-add/{operation_id}/undo", response_model=Message)
def undo(operation_id: uuid.UUID, ctx: TreeCtx) -> Message:
    """Undo a Smart Add within 30 minutes, by the same user, if nothing else has changed since."""
    service.undo(ctx, operation_id)
    return Message(message="Undone")
