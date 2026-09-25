from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import TreeCtx
from app.core.textnorm import search_key
from app.models import FamilyBranch, Household, Place
from app.modules.genealogy import lookup
from app.modules.genealogy.serialize import Serializer
from app.modules.search import providers
from app.modules.search.schemas import DuplicateCandidate, SearchHit, SearchOut
from app.modules.search.service import match_names

router = APIRouter(prefix="/trees/{tree_id}", tags=["search"])

ALL_KINDS = ("person", "place", "branch", "household", "document", "property")


@router.get("/search", response_model=SearchOut)
def search(
    ctx: TreeCtx,
    q: str = Query(min_length=1, max_length=200),
    kinds: list[str] | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> SearchOut:
    wanted = set(kinds or ALL_KINDS)
    hits: list[SearchHit] = []
    if "person" in wanted:
        matches = match_names(ctx, q, limit=limit * 3)
        subjects = lookup.visible_subjects(ctx, [m.person_id for m in matches])
        summaries = Serializer(ctx).summaries(subjects)
        for m in matches:
            if m.person_id in summaries:
                s = summaries[m.person_id]
                years = f"{s.birth_year or '?'}–{s.death_year or ('' if s.profile_status.value == 'living' else '?')}"
                hits.append(
                    SearchHit(
                        kind="person",
                        id=m.person_id,
                        title=s.display_name,
                        subtitle=years,
                        score=m.score,
                        match_tier=m.tier,
                        match_reason=m.reason,
                        person=s,
                    )
                )
    key = search_key(q)
    if "place" in wanted and key:
        for p in ctx.db.scalars(
            select(Place).where(Place.tree_id == ctx.tree_id, Place.search_text.contains(key)).limit(limit)
        ):
            other_names = [n.get("name") for n in (p.historical_names or []) + (p.local_names or [])]
            via = next((n for n in other_names if n and key in search_key(n)), None)
            reason = (
                f'historical/local name "{via}"'
                if via and key not in search_key(p.canonical_name)
                else f'place name contains "{q}"'
            )
            hits.append(
                SearchHit(
                    kind="place",
                    id=p.id,
                    title=p.canonical_name,
                    subtitle=p.place_type.value,
                    score=0.7,
                    match_tier="contains",
                    match_reason=reason,
                )
            )
    if "branch" in wanted:
        for b in ctx.db.scalars(
            select(FamilyBranch)
            .where(FamilyBranch.tree_id == ctx.tree_id, FamilyBranch.name.ilike(f"%{q}%"))
            .limit(limit)
        ):
            hits.append(
                SearchHit(
                    kind="branch",
                    id=b.id,
                    title=b.name,
                    subtitle=b.descent_rule.value,
                    score=0.7,
                    match_tier="contains",
                    match_reason=f'branch name contains "{q}"',
                )
            )
    if "household" in wanted:
        for h in ctx.db.scalars(
            select(Household)
            .where(
                Household.tree_id == ctx.tree_id,
                (Household.name.ilike(f"%{q}%") | Household.house_name.ilike(f"%{q}%")),
            )
            .limit(limit)
        ):
            hits.append(
                SearchHit(
                    kind="household",
                    id=h.id,
                    title=h.name,
                    subtitle=h.house_name,
                    score=0.7,
                    match_tier="contains",
                    match_reason=f'household name contains "{q}"',
                )
            )
    for kind, provider in providers.registered().items():
        if kind in wanted:
            hits.extend(provider(ctx, q, limit))
    hits.sort(key=lambda h: -h.score)
    return SearchOut(query=q, hits=hits[: limit * 2])


@router.get("/duplicates", response_model=list[DuplicateCandidate])
def duplicates(
    ctx: TreeCtx,
    person_id: uuid.UUID | None = None,
    min_score: float = Query(default=0.55, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[DuplicateCandidate]:
    """Possible duplicate people (PRS §24). Suggestions only — merging always needs a user."""
    from app.modules.search.duplicates import candidate_pairs

    return candidate_pairs(ctx, person_id=person_id, min_score=min_score, limit=limit)
