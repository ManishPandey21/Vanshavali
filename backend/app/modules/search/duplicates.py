"""Duplicate person candidates (PRS §24). Cultural fields never count as identity evidence."""

from __future__ import annotations

import uuid
from collections import defaultdict

import jellyfish
from sqlalchemy import select

from app.authz.context import TreeContext
from app.models import NameRecord, Relationship
from app.models.enums import PARENT_TYPES, UNION_TYPES
from app.modules.genealogy import lookup
from app.modules.genealogy.serialize import Serializer
from app.modules.search.schemas import DuplicateCandidate


def _name_sim(a: set[str], b: set[str]) -> tuple[float, str | None]:
    best, why = 0.0, None
    for x in a:
        for y in b:
            if not x or not y:
                continue
            s = jellyfish.jaro_winkler_similarity(x, y)
            if s > best:
                best, why = s, f'names "{x}" / "{y}" similarity {s:.2f}'
    return best, why


def candidate_pairs(
    ctx: TreeContext, *, person_id: uuid.UUID | None, min_score: float, limit: int
) -> list[DuplicateCandidate]:
    names: dict[uuid.UUID, set[str]] = defaultdict(set)
    for pid, text in ctx.db.execute(
        select(NameRecord.person_id, NameRecord.search_text).where(NameRecord.tree_id == ctx.tree_id)
    ):
        names[pid].add(text)
    subjects = lookup.visible_subjects(ctx, names.keys())
    parents: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    spouses: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for r in ctx.db.scalars(select(Relationship).where(Relationship.tree_id == ctx.tree_id)):
        if r.type in PARENT_TYPES:
            parents[r.person_b_id].add(r.person_a_id)
        elif r.type in UNION_TYPES:
            spouses[r.person_a_id].add(r.person_b_id)
            spouses[r.person_b_id].add(r.person_a_id)
    ids = sorted(subjects, key=str)
    # blocking on first letter of any name token keeps this ~O(n·k)
    blocks: dict[str, set[uuid.UUID]] = defaultdict(set)
    for pid in ids:
        for n in names[pid]:
            for tok in n.split():
                blocks[tok[:2]].add(pid)
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for members in blocks.values():
        ms = sorted(members, key=str)
        for i, a in enumerate(ms):
            for b in ms[i + 1 :]:
                if person_id is None or person_id in (a, b):
                    pairs.add((a, b))
    out: list[tuple[float, uuid.UUID, uuid.UUID, list[str]]] = []
    for a, b in pairs:
        if b in parents[a] or a in parents[b] or b in spouses[a]:
            continue  # directly related people are not duplicates of each other
        sim, why = _name_sim(names[a], names[b])
        if sim < 0.82:
            continue
        reasons = [why] if why else []
        score = 0.5 * sim
        bda, bdb = subjects[a].birth_date, subjects[b].birth_date
        ya = bda.year if bda else None
        yb = bdb.year if bdb else None
        if ya and yb:
            if abs(ya - yb) <= 1:
                score += 0.25
                reasons.append(f"birth years {ya} / {yb}")
            elif abs(ya - yb) > 5:
                score -= 0.3
        shared_parents = parents[a] & parents[b]
        if shared_parents:
            score += 0.15
            reasons.append("share a recorded parent")
        if spouses[a] & spouses[b]:
            score += 0.15
            reasons.append("share a recorded spouse")
        if (
            subjects[a].person.sex_at_birth
            and subjects[b].person.sex_at_birth
            and subjects[a].person.sex_at_birth != subjects[b].person.sex_at_birth
        ):
            score -= 0.4
        if score >= min_score:
            out.append((min(score, 1.0), a, b, reasons))
    out.sort(key=lambda x: -x[0])
    out = out[:limit]
    summaries = Serializer(ctx).summaries({pid: subjects[pid] for _, a, b, _ in out for pid in (a, b)})
    return [
        DuplicateCandidate(
            person_a=summaries[a],
            person_b=summaries[b],
            score=round(s, 3),
            outcome="probable" if s >= 0.8 else "possible",
            reasons=reasons,
        )
        for s, a, b, reasons in out
    ]
