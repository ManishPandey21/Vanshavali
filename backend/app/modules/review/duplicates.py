"""Duplicates at entry: "is this person already in the tree?" (ADR-0021 §8, plan phase J).

Scores a person about to be added against people the user can already see, with the PRS §24 rules
(names across scripts, birth year, a shared parent or spouse, a different sex at birth counts
against) plus the LGD birth village when both places are linked (ADR-0019). Only visible,
non-concealed people are scored and returned, never counted or hinted at otherwise, so the check
is no oracle for hidden people. Nothing is chosen or merged: the user decides.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

import jellyfish
from sqlalchemy import or_, select

from app.authz.context import TreeContext
from app.core.textnorm import search_key
from app.models import Event, EventParticipant, NameRecord, Place, Relationship
from app.models.enums import PARENT_TYPES, UNION_TYPES, EventType, ParticipantRole
from app.modules.genealogy import lookup, provisional
from app.modules.genealogy.serialize import Serializer

MAX_CANDIDATES = 5
# a same-name match alone (0.5) is worth showing at entry; a distant birth year (-0.3) or a
# different sex at birth (-0.4) takes it below this
MIN_SCORE = 0.45
BADGE_SCORE = 0.85
_POOL = 300


def _keys(names: list[dict[str, Any]]) -> set[str]:
    out = set()
    for n in names:
        key = search_key(n.get("given_name"), n.get("surname"))
        if key:
            out.add(key)
    return out


def _birth_village(ctx: TreeContext, person_ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str]]:
    """(lgd_level, lgd_code) of each person's preferred birth place, when linked to LGD."""
    if not person_ids:
        return {}
    rows = ctx.db.execute(
        select(EventParticipant.person_id, Place.lgd_level, Place.lgd_code)
        .join(Event, Event.id == EventParticipant.event_id)
        .join(Place, Place.id == Event.place_id)
        .where(
            EventParticipant.tree_id == ctx.tree_id,
            EventParticipant.person_id.in_(person_ids),
            EventParticipant.role == ParticipantRole.PRINCIPAL,
            Event.type == EventType.BIRTH,
            Event.is_preferred.is_(True),
            Place.lgd_level.is_not(None),
        )
    ).all()
    return {pid: (str(getattr(lvl, "value", lvl)), code) for pid, lvl, code in rows if code and lvl}


def check(
    ctx: TreeContext,
    *,
    names: list[dict[str, Any]],
    birth_year: int | None,
    sex_at_birth: str | None,
    parent_ids: list[uuid.UUID],
    spouse_ids: list[uuid.UUID],
    birth_place_id: uuid.UUID | None,
    exclude_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    keys = _keys(names)
    if not keys:
        return []
    # candidates: name records similar to any key (trigram index on search_text)
    rows = ctx.db.execute(
        select(NameRecord.person_id, NameRecord.search_text)
        .where(NameRecord.tree_id == ctx.tree_id, or_(*[NameRecord.search_text.op("%")(k) for k in keys]))
        .limit(_POOL)
    ).all()
    their_names: dict[uuid.UUID, set[str]] = defaultdict(set)
    for pid, text in rows:
        their_names[pid].add(text)
    hidden = provisional.concealed_ids(ctx) | set(exclude_ids) | set(parent_ids) | set(spouse_ids)
    subjects = {
        pid: s for pid, s in lookup.visible_subjects(ctx, their_names.keys()).items() if pid not in hidden
    }
    if not subjects:
        return []
    ids = set(subjects)
    parents: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    spouses: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for r in ctx.db.scalars(
        select(Relationship).where(
            Relationship.tree_id == ctx.tree_id,
            or_(Relationship.person_a_id.in_(ids), Relationship.person_b_id.in_(ids)),
        )
    ):
        if r.type in PARENT_TYPES:
            parents[r.person_b_id].add(r.person_a_id)
        elif r.type in UNION_TYPES:
            spouses[r.person_a_id].add(r.person_b_id)
            spouses[r.person_b_id].add(r.person_a_id)
    villages = _birth_village(ctx, ids)
    new_village = None
    if birth_place_id is not None:
        place = ctx.db.get(Place, birth_place_id)
        if place is not None and place.tree_id == ctx.tree_id and place.lgd_level and place.lgd_code:
            new_village = (place.lgd_level.value, place.lgd_code)

    out: list[tuple[float, uuid.UUID, list[str]]] = []
    for pid, subject in subjects.items():
        best, why = 0.0, ""
        for k in keys:
            for theirs in their_names[pid]:
                s = jellyfish.jaro_winkler_similarity(k, theirs)
                if s > best:
                    best, why = s, theirs
        if best < 0.82:
            continue
        reasons = [f'similar name ("{why}")'] if best < 0.999 else ["same name"]
        score = 0.5 * best
        their_year = subject.birth_date.year if subject.birth_date else None
        if birth_year and their_year:
            if abs(birth_year - their_year) <= 1:
                score += 0.25
                reasons.append(f"birth year {their_year}")
            elif abs(birth_year - their_year) > 5:
                score -= 0.3
        if set(parent_ids) & parents[pid]:
            score += 0.15
            reasons.append("same parent")
        if set(spouse_ids) & spouses[pid]:
            score += 0.15
            reasons.append("same spouse")
        if new_village and villages.get(pid) == new_village:
            score += 0.1
            reasons.append("same birth village")
        theirs_sex = subject.person.sex_at_birth.value if subject.person.sex_at_birth else None
        if sex_at_birth and theirs_sex and sex_at_birth != theirs_sex:
            score -= 0.4
        if score >= MIN_SCORE:
            out.append((min(score, 1.0), pid, reasons))
    out.sort(key=lambda x: (-x[0], str(x[1])))
    out = out[:MAX_CANDIDATES]
    summaries = Serializer(ctx).summaries({pid: subjects[pid] for _, pid, _ in out})
    return [
        {"person": summaries[pid], "score": round(s, 3), "likely": s >= BADGE_SCORE, "reasons": reasons}
        for s, pid, reasons in out
    ]
