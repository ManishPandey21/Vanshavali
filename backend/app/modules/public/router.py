"""Unauthenticated read-only views of trees whose owners enabled public mode (deceased-only).

Every response goes through the same privacy evaluation with ``ctx.public=True``: living,
unknown-status and minor people are never returned, and only public-safe fields are included.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import PublicCtx
from app.api.schemas import ApiModel, Page, decode_cursor, encode_cursor
from app.authz.privacy import can_view_person, load_subjects
from app.models import Person
from app.models.enums import ProfileStatus
from app.modules.genealogy import engine, lookup
from app.modules.genealogy.schemas import FamilyOut, GraphOut, PersonOut, PersonSummary
from app.modules.genealogy.serialize import Serializer

router = APIRouter(prefix="/public/trees/{slug}", tags=["public"])


class PublicTreeOut(ApiModel):
    name: str
    description: str | None
    slug: str


@router.get("", response_model=PublicTreeOut)
def public_tree(ctx: PublicCtx) -> PublicTreeOut:
    return PublicTreeOut(name=ctx.tree.name, description=ctx.tree.description, slug=ctx.tree.slug)


@router.get("/people", response_model=Page[PersonSummary])
def public_people(
    ctx: PublicCtx, cursor: str | None = None, limit: int = Query(default=50, ge=1, le=200)
) -> Page[PersonSummary]:
    offset = decode_cursor(cursor)
    rows = ctx.db.scalars(
        select(Person)
        .where(
            Person.tree_id == ctx.tree_id,
            Person.deleted_at.is_(None),
            Person.profile_status == ProfileStatus.DECEASED,
        )
        .order_by(Person.preferred_display_name, Person.id)
    ).all()
    subjects = load_subjects(ctx, rows)
    visible = [subjects[p.id] for p in rows if can_view_person(ctx, subjects[p.id])]
    page = visible[offset : offset + limit]
    summaries = Serializer(ctx).summaries({s.id: s for s in page})
    return Page(
        items=[summaries[s.id] for s in page],
        next_cursor=encode_cursor(offset + limit) if len(visible) > offset + limit else None,
    )


@router.get("/people/{person_id}", response_model=PersonOut)
def public_person(person_id: uuid.UUID, ctx: PublicCtx) -> PersonOut:
    return Serializer(ctx).person_out(lookup.get_person_subject(ctx, person_id))


@router.get("/people/{person_id}/family", response_model=FamilyOut)
def public_family(person_id: uuid.UUID, ctx: PublicCtx) -> FamilyOut:
    return engine.family(ctx, person_id)


@router.get("/people/{person_id}/ancestors", response_model=GraphOut)
def public_ancestors(
    person_id: uuid.UUID, ctx: PublicCtx, depth: int = Query(default=4, ge=1, le=10)
) -> GraphOut:
    return engine.graph(ctx, person_id, "ancestors", depth, None)
