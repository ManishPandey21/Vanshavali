"""Family relationship engine: family units, ancestry traversal, relationship calculator (PRS §25)."""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, NamedTuple

from sqlalchemy import select, text

from app.authz.context import TreeContext
from app.core.config import get_settings
from app.models import Person, Relationship
from app.models.enums import PARENT_TYPES, UNION_TYPES, EvidenceStatus, Lineage, RelationshipType, SexAtBirth
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import (
    FamilyOut,
    GraphEdge,
    GraphNode,
    GraphOut,
    RelatedPerson,
    RelationshipPathOut,
    SiblingOut,
    UnionOut,
)
from app.modules.genealogy.serialize import Serializer, relationship_out

_EXCLUDED_EVIDENCE = (EvidenceStatus.DISPROVEN, EvidenceStatus.SUPERSEDED)


def _lineage_filter(lineages: set[Lineage] | None, rel: Any) -> bool:
    if not lineages:
        return True
    return (rel.lineage or Lineage.BIOLOGICAL) in lineages


# --------------------------------------------------------------------------- family unit
def family(ctx: TreeContext, person_id: uuid.UUID, lineages: set[Lineage] | None = None) -> FamilyOut:
    subject = lookup.get_person_subject(ctx, person_id)
    pid = subject.id
    rels = list(
        ctx.db.scalars(
            select(Relationship).where(
                Relationship.tree_id == ctx.tree_id,
                (Relationship.person_a_id == pid) | (Relationship.person_b_id == pid),
            )
        )
    )
    parent_edges = [
        r for r in rels if r.type in PARENT_TYPES and r.person_b_id == pid and _lineage_filter(lineages, r)
    ]
    child_edges = [
        r for r in rels if r.type in PARENT_TYPES and r.person_a_id == pid and _lineage_filter(lineages, r)
    ]
    union_edges = sorted(
        [r for r in rels if r.type in UNION_TYPES], key=lambda r: (r.union_order or 999, r.created_at)
    )
    sibling_edges = [r for r in rels if r.type == RelationshipType.SIBLING]

    # siblings via shared parents
    parent_ids = {r.person_a_id for r in parent_edges}
    shared: list[Relationship] = []
    if parent_ids:
        shared = list(
            ctx.db.scalars(
                select(Relationship).where(
                    Relationship.tree_id == ctx.tree_id,
                    Relationship.person_a_id.in_(parent_ids),
                    Relationship.type.in_(list(PARENT_TYPES)),
                    Relationship.person_b_id != pid,
                )
            )
        )
    union_partner_ids = {r.person_b_id if r.person_a_id == pid else r.person_a_id for r in union_edges}
    all_ids = (
        {pid}
        | parent_ids
        | {r.person_b_id for r in child_edges}
        | union_partner_ids
        | {r.person_b_id for r in shared}
        | {r.person_b_id if r.person_a_id == pid else r.person_a_id for r in sibling_edges}
    )
    subjects = lookup.visible_subjects(ctx, all_ids)
    ser = Serializer(ctx)
    summaries = ser.summaries(subjects)

    def related(other: uuid.UUID, rel: Relationship | None) -> RelatedPerson:
        visible = other in summaries
        return RelatedPerson(
            person=summaries.get(other) if visible else None,
            hidden=not visible,
            relationship_id=rel.id if rel and visible else None,
            relationship_type=rel.type if rel else None,
            lineage=rel.lineage if rel else None,
            subtype=rel.subtype if rel and visible else None,
            evidence_status=rel.evidence_status if rel else None,
        )

    parents = [related(r.person_a_id, r) for r in parent_edges]
    unions: list[UnionOut] = []
    used_children: set[uuid.UUID] = set()
    for u in union_edges:
        partner = u.person_b_id if u.person_a_id == pid else u.person_a_id
        kids = [related(c.person_b_id, c) for c in child_edges if c.union_id == u.id]
        used_children |= {c.id for c in child_edges if c.union_id == u.id}
        if ctx.public and partner not in summaries:
            continue
        if partner not in summaries:
            rel_out = None  # SEC-4: never reveal a hidden partner's id, dates or notes
        elif ctx.public:
            rel_out = relationship_out(u).model_copy(
                update={"notes": None, "legal_status": None, "provenance": None}
            )  # SEC-9: public pages carry no notes or provenance
        else:
            rel_out = relationship_out(u)
        unions.append(UnionOut(relationship=rel_out, partner=related(partner, u), children=kids))
    other_children = [related(c.person_b_id, c) for c in child_edges if c.id not in used_children]

    # sibling classification
    my_bio = {
        r.person_a_id
        for r in parent_edges
        if r.type == RelationshipType.BIOLOGICAL_PARENT and r.evidence_status not in _EXCLUDED_EVIDENCE
    }
    my_adopt = {r.person_a_id for r in parent_edges if r.type == RelationshipType.ADOPTIVE_PARENT}
    my_step = {r.person_a_id for r in parent_edges if r.type in (RelationshipType.STEP_PARENT,)}
    by_sib: dict[uuid.UUID, list[Relationship]] = {}
    for r in shared:
        by_sib.setdefault(r.person_b_id, []).append(r)
    siblings: list[SiblingOut] = []
    for sib, edges in by_sib.items():
        bio = {
            e.person_a_id
            for e in edges
            if e.type == RelationshipType.BIOLOGICAL_PARENT and e.evidence_status not in _EXCLUDED_EVIDENCE
        }
        common_bio = bio & my_bio
        if (common_bio and len(common_bio) >= 2) or (common_bio and len(my_bio) == 1 and len(bio) == 1):
            kind = "full"
        elif common_bio:
            kind = "half"
        elif {e.person_a_id for e in edges} & my_adopt or bio & my_adopt:
            kind = "adoptive"
        elif {e.person_a_id for e in edges} & (my_step | parent_ids):
            kind = "step"
        else:
            continue
        base = related(sib, None)
        if ctx.public and base.hidden:
            continue
        siblings.append(SiblingOut(**base.model_dump(), kind=kind))
    known = {s.person.id for s in siblings if s.person}
    for r in sibling_edges:
        other = r.person_b_id if r.person_a_id == pid else r.person_a_id
        if other in known:
            continue
        base = related(other, r)
        if ctx.public and base.hidden:
            continue
        siblings.append(SiblingOut(**base.model_dump(), kind="explicit"))

    if ctx.public:
        parents = [p for p in parents if not p.hidden]
        other_children = [c for c in other_children if not c.hidden]
        for uo in unions:
            uo.children = [c for c in uo.children if not c.hidden]
    return FamilyOut(
        person=summaries[pid],
        parents=parents,
        unions=unions,
        other_children=other_children,
        siblings=siblings,
    )


# --------------------------------------------------------------------------- traversal
@dataclass
class _Row:
    parent: uuid.UUID
    child: uuid.UUID
    type: RelationshipType
    lineage: Lineage | None
    generation: int


def _walk(
    ctx: TreeContext, root: uuid.UUID, direction: str, depth: int, lineages: set[Lineage] | None
) -> list[_Row]:
    lineage_vals = [lin.value for lin in lineages] if lineages else None
    if direction == "ancestors":
        start_col, next_col, join_col = "person_b_id", "person_a_id", "person_b_id"
    else:
        start_col, next_col, join_col = "person_a_id", "person_b_id", "person_a_id"
    lineage_clause = "AND coalesce(r.lineage, 'biological') = ANY(:lineages)" if lineage_vals else ""
    # column names are internal constants chosen above (never user input)
    sql = text(
        f"""
        WITH RECURSIVE walk(parent, child, type, lineage, generation, path) AS (
            SELECT r.person_a_id, r.person_b_id, r.type, r.lineage, 1, ARRAY[r.{start_col}, r.{next_col}]
              FROM relationship r
             WHERE r.tree_id = :tree AND r.{start_col} = :root AND r.type = ANY(:ptypes)
               AND r.evidence_status <> ALL(:excluded) {lineage_clause}
            UNION ALL
            SELECT r.person_a_id, r.person_b_id, r.type, r.lineage, w.generation + 1, w.path || r.{next_col}
              FROM relationship r
              JOIN walk w ON r.{join_col} = (CASE WHEN :dir = 'ancestors' THEN w.parent ELSE w.child END)
             WHERE r.tree_id = :tree AND r.type = ANY(:ptypes) AND w.generation < :depth
               AND r.evidence_status <> ALL(:excluded) {lineage_clause}
               AND NOT (r.{next_col} = ANY(w.path))
        )
        SELECT DISTINCT parent, child, type, lineage, generation FROM walk ORDER BY generation
        """
    )
    params = {
        "tree": ctx.tree_id,
        "root": root,
        "ptypes": [t.value for t in PARENT_TYPES],
        "depth": depth,
        "dir": direction,
        "excluded": [e.value for e in _EXCLUDED_EVIDENCE],
    }
    if lineage_vals:
        params["lineages"] = lineage_vals
    return [
        _Row(r[0], r[1], RelationshipType(r[2]), Lineage(r[3]) if r[3] else None, r[4])
        for r in ctx.db.execute(sql, params).all()
    ]


def graph(
    ctx: TreeContext,
    root_id: uuid.UUID,
    direction: str,
    depth: int,
    lineages: set[Lineage] | None,
    max_nodes: int = 500,
) -> GraphOut:
    lookup.get_person_subject(ctx, root_id)
    depth = max(1, min(depth, get_settings().max_traversal_depth))
    rows = _walk(ctx, root_id, direction, depth, lineages)
    gen: dict[uuid.UUID, int] = {root_id: 0}
    for r in rows:
        node = r.parent if direction == "ancestors" else r.child
        g = r.generation if direction == "descendants" else -r.generation
        if node not in gen or abs(g) < abs(gen[node]):
            gen[node] = g
    truncated = len(gen) > max_nodes
    if truncated:
        keep = sorted(gen, key=lambda n: abs(gen[n]))[:max_nodes]
        gen = {k: gen[k] for k in keep}
    subjects = lookup.visible_subjects(ctx, gen)
    summaries = Serializer(ctx).summaries(subjects)
    nodes: list[GraphNode] = []
    alias: dict[uuid.UUID, str] = {}
    for i, (pid, g) in enumerate(sorted(gen.items(), key=lambda kv: (abs(kv[1]), str(kv[0])))):
        if pid in summaries:
            alias[pid] = str(pid)
            nodes.append(GraphNode(id=str(pid), person=summaries[pid], generation=g))
        elif not ctx.public:
            alias[pid] = f"hidden-{i}"
            nodes.append(GraphNode(id=alias[pid], person=None, hidden=True, generation=g))
    edges = [
        GraphEdge(source=alias[r.parent], target=alias[r.child], type=r.type, lineage=r.lineage)
        for r in rows
        if r.parent in alias and r.child in alias
    ]
    unique_edges = {(e.source, e.target, e.type): e for e in edges}
    # unions touching visible nodes. Partners outside the lineage (in-laws) are added as partner
    # nodes on their spouse's generation, so descendant views can show couples (only if visible).
    visible = [p for p in gen if p in summaries]
    unions: list[dict[str, str]] = []
    if visible:
        union_rows = list(
            ctx.db.scalars(
                select(Relationship).where(
                    Relationship.tree_id == ctx.tree_id,
                    Relationship.type.in_(list(UNION_TYPES)),
                    Relationship.person_a_id.in_(visible) | Relationship.person_b_id.in_(visible),
                )
            )
        )
        partner_gen: dict[uuid.UUID, int] = {}
        for u in union_rows:
            for inside, other in ((u.person_a_id, u.person_b_id), (u.person_b_id, u.person_a_id)):
                if inside in gen and other not in gen:
                    partner_gen.setdefault(other, gen[inside])
        partner_subjects = lookup.visible_subjects(ctx, partner_gen) if len(nodes) < max_nodes else {}
        partner_summaries = Serializer(ctx).summaries(partner_subjects)
        for pid, g in partner_gen.items():
            if pid in partner_summaries:
                alias[pid] = str(pid)
                nodes.append(
                    GraphNode(id=str(pid), person=partner_summaries[pid], generation=g, partner=True)
                )
        for u in union_rows:
            if (
                u.person_a_id in alias
                and u.person_b_id in alias
                and not alias[u.person_a_id].startswith("hidden")
            ):
                if alias[u.person_b_id].startswith("hidden"):
                    continue
                unions.append(
                    {"id": str(u.id), "a": str(u.person_a_id), "b": str(u.person_b_id), "type": u.type.value}
                )
        if partner_summaries:
            for pr in ctx.db.scalars(
                select(Relationship).where(
                    Relationship.tree_id == ctx.tree_id,
                    Relationship.type.in_(list(PARENT_TYPES)),
                    Relationship.person_a_id.in_(list(partner_summaries)),
                    Relationship.person_b_id.in_([p for p in gen if p in alias]),
                )
            ):
                if lineages and not _lineage_filter(lineages, pr):
                    continue
                key = (alias[pr.person_a_id], alias[pr.person_b_id], pr.type)
                unique_edges.setdefault(
                    key, GraphEdge(source=key[0], target=key[1], type=pr.type, lineage=pr.lineage)
                )
    return GraphOut(
        root_id=root_id,
        direction=direction,
        depth=depth,
        truncated=truncated,
        nodes=nodes,
        edges=list(unique_edges.values()),
        unions=unions,
    )


# --------------------------------------------------------------------------- relationship calculator
_ORDINAL = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
}


def _gendered(sex: SexAtBirth | None, male: str, female: str, neutral: str) -> str:
    if sex == SexAtBirth.MALE:
        return male
    if sex == SexAtBirth.FEMALE:
        return female
    return neutral


def _greats(n: int) -> str:
    return "" if n <= 0 else ("great-" * n if n <= 2 else f"{n}× great-")


def _blood_label(up: int, down: int, sex: SexAtBirth | None, half: bool) -> str:
    """Label of B relative to A, where A goes ``up`` generations to the common ancestor, B is ``down`` below it."""
    if up == 0 and down == 0:
        return "self"
    if down == 0:  # B is A's ancestor
        base = _gendered(sex, "father", "mother", "parent")
        if up == 1:
            return base
        return f"{_greats(up - 2)}grand{base}"
    if up == 0:  # B is A's descendant
        base = _gendered(sex, "son", "daughter", "child")
        if down == 1:
            return base
        return f"{_greats(down - 2)}grand{base}"
    if up == 1 and down == 1:
        return ("half-" if half else "") + _gendered(sex, "brother", "sister", "sibling")
    if up == 1:  # B is a descendant of A's sibling
        base = _gendered(sex, "nephew", "niece", "nibling")
        return base if down == 2 else f"{_greats(down - 3)}grand{base}"
    if down == 1:  # B is a sibling of A's ancestor
        base = _gendered(sex, "uncle", "aunt", "parent's sibling")
        return base if up == 2 else f"{_greats(up - 3)}grand-{base}" if up > 3 else f"great-{base}"
    degree = min(up, down) - 1
    removed = abs(up - down)
    label = f"{_ORDINAL.get(degree, f'{degree}th')} cousin"
    if removed:
        label += " once removed" if removed == 1 else f" {removed} times removed"
    return label


class _Edge(NamedTuple):
    id: uuid.UUID
    person_a_id: uuid.UUID
    person_b_id: uuid.UUID
    type: RelationshipType
    lineage: Lineage | None


def _load_graph(
    ctx: TreeContext, lineages: set[Lineage] | None
) -> tuple[
    dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]],
    dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]],
    dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]],
]:
    deleted = set(
        ctx.db.scalars(select(Person.id).where(Person.tree_id == ctx.tree_id, Person.deleted_at.is_not(None)))
    )
    parents: dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]] = {}
    children: dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]] = {}
    spouses: dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]] = {}
    rows = ctx.db.execute(
        select(
            Relationship.id,
            Relationship.person_a_id,
            Relationship.person_b_id,
            Relationship.type,
            Relationship.lineage,
        ).where(
            Relationship.tree_id == ctx.tree_id, Relationship.evidence_status.notin_(list(_EXCLUDED_EVIDENCE))
        )
    ).all()
    for row in rows:
        r = _Edge(*row)  # lightweight: 30k+ edges are loaded per call at 10k people
        if r.person_a_id in deleted or r.person_b_id in deleted:
            continue
        if r.type in PARENT_TYPES:
            if not _lineage_filter(lineages, r):
                continue
            parents.setdefault(r.person_b_id, []).append((r.person_a_id, r))
            children.setdefault(r.person_a_id, []).append((r.person_b_id, r))
        elif r.type in UNION_TYPES:
            spouses.setdefault(r.person_a_id, []).append((r.person_b_id, r))
            spouses.setdefault(r.person_b_id, []).append((r.person_a_id, r))
    return parents, children, spouses


def _ancestors_with_depth(
    start: uuid.UUID, parents: dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]], limit: int
) -> dict[uuid.UUID, int]:
    out = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        if out[cur] >= limit:
            continue
        for p, _ in parents.get(cur, []):
            if p not in out:
                out[p] = out[cur] + 1
                q.append(p)
    return out


def relationship_path(
    ctx: TreeContext, a_id: uuid.UUID, b_id: uuid.UUID, lineages: set[Lineage] | None = None
) -> RelationshipPathOut:
    """Relationship between two visible people. People the viewer cannot see are never identified:
    their ids are replaced by ``None`` in ``path`` and omitted from ``common_ancestor_ids``, and the
    kinship words for them are gender-neutral.

    Visibility is evaluated only for the people on the result (path + common ancestors), not for the
    whole tree, which keeps this O(edges) at 10k+ people.
    """
    lookup.get_person(ctx, a_id)
    lookup.get_person(ctx, b_id)
    graph = _load_graph(ctx, lineages)
    # pass 1 without sex data finds the path; only the people it touches are then loaded
    out = _relationship_path_raw(ctx, a_id, b_id, graph, {})
    _parents, _children, spouses = graph
    touched = {p for p in out.path if p is not None} | set(out.common_ancestor_ids)
    visible = set(lookup.visible_subjects(ctx, touched))
    hidden = touched - visible
    wanted = (
        touched | {a_id, b_id} | {s for s, _ in spouses.get(a_id, [])} | {s for s, _ in spouses.get(b_id, [])}
    )
    sex = {
        pid: (None if pid in hidden else sx)
        for pid, sx in ctx.db.execute(
            select(Person.id, Person.sex_at_birth).where(Person.tree_id == ctx.tree_id, Person.id.in_(wanted))
        )
        .tuples()
        .all()
    }
    out = _relationship_path_raw(ctx, a_id, b_id, graph, sex)
    return out.model_copy(
        update={
            "path": [p if p in visible else None for p in out.path],
            "common_ancestor_ids": [c for c in out.common_ancestor_ids if c in visible],
        }
    )


def _relationship_path_raw(
    ctx: TreeContext,
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    graph: tuple[dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]], ...],
    sex: dict[uuid.UUID, SexAtBirth | None],
) -> RelationshipPathOut:
    b = lookup.get_person(ctx, b_id)
    limit = get_settings().max_traversal_depth
    parents, children, spouses = graph

    def blood(x: uuid.UUID, y: uuid.UUID) -> tuple[int, int, list[uuid.UUID], set[Lineage]] | None:
        ax = _ancestors_with_depth(x, parents, limit)
        ay = _ancestors_with_depth(y, parents, limit)
        common = set(ax) & set(ay)
        if not common:
            return None
        best = min(ax[c] + ay[c] for c in common)
        cas = [c for c in common if ax[c] + ay[c] == best]
        c0 = min(cas, key=lambda c: ax[c])
        return ax[c0], ay[c0], cas, set()

    base = RelationshipPathOut(from_id=a_id, to_id=b_id, found=False)
    if a_id == b_id:
        return base.model_copy(update={"found": True, "label": "self", "path": [a_id]})

    # direct union
    for other, r in spouses.get(a_id, []):
        if other == b_id:
            label = {
                RelationshipType.DIVORCED_SPOUSE: "former spouse",
                RelationshipType.SEPARATED_SPOUSE: "separated spouse",
                RelationshipType.PARTNER: "partner",
            }.get(r.type, _gendered(sex.get(b_id), "husband", "wife", "spouse"))
            return base.model_copy(
                update={"found": True, "label": label, "chain": ["spouse"], "path": [a_id, b_id]}
            )

    # direct non-biological parent edges carry their own label
    for p, r in parents.get(a_id, []):
        if p == b_id and r.type != RelationshipType.BIOLOGICAL_PARENT:
            kind = r.type.value.replace("_parent", "").replace("_", " ")
            word = (
                "guardian"
                if r.type == RelationshipType.GUARDIAN
                else f"{kind}-{_gendered(sex.get(b_id), 'father', 'mother', 'parent')}"
            )
            return base.model_copy(
                update={
                    "found": True,
                    "label": word,
                    "chain": [r.type.value],
                    "path": [a_id, b_id],
                    "lineages": [r.lineage] if r.lineage else [],
                }
            )
    for c, r in children.get(a_id, []):
        if c == b_id and r.type != RelationshipType.BIOLOGICAL_PARENT:
            kind = r.type.value.replace("_parent", "").replace("_", " ")
            word = (
                "ward"
                if r.type == RelationshipType.GUARDIAN
                else f"{kind}-{_gendered(sex.get(b_id), 'son', 'daughter', 'child')}"
            )
            return base.model_copy(
                update={"found": True, "label": word, "chain": [f"{r.type.value}_of"], "path": [a_id, b_id]}
            )

    res = blood(a_id, b_id)
    if res:
        up, down, cas, _ = res
        a_par = {p for p, r in parents.get(a_id, []) if r.type == RelationshipType.BIOLOGICAL_PARENT}
        b_par = {p for p, r in parents.get(b_id, []) if r.type == RelationshipType.BIOLOGICAL_PARENT}
        half = up == 1 and down == 1 and len(a_par & b_par) == 1 and (len(a_par) > 1 or len(b_par) > 1)
        label = _blood_label(up, down, sex.get(b_id), half)
        path = _bfs_path(a_id, b_id, parents, children, {})
        chain = _chain(path, parents, children, spouses, sex)
        return base.model_copy(
            update={
                "found": True,
                "label": label,
                "chain": chain,
                "path": path,
                "common_ancestor_ids": cas,
                "explanation": f"{up} generation(s) up and {down} down via a common ancestor",
            }
        )

    # in-law: B is blood-related to A's spouse, or B is the spouse of A's blood relative
    for sp, _ in spouses.get(a_id, []):
        r2 = blood(sp, b_id)
        if r2:
            up, down, cas, _ = r2
            inner = _blood_label(up, down, sex.get(b_id), False)
            label = {
                "father": "father-in-law",
                "mother": "mother-in-law",
                "parent": "parent-in-law",
                "brother": "brother-in-law",
                "sister": "sister-in-law",
                "sibling": "sibling-in-law",
            }.get(inner, f"spouse's {inner}")
            path = _bfs_path(a_id, b_id, parents, children, spouses)
            return base.model_copy(
                update={
                    "found": True,
                    "label": label,
                    "path": path,
                    "chain": _chain(path, parents, children, spouses, sex),
                    "common_ancestor_ids": cas,
                }
            )
    for sp, _ in spouses.get(b_id, []):
        r2 = blood(a_id, sp)
        if r2:
            up, down, cas, _ = r2
            inner = _blood_label(up, down, sex.get(sp), False)
            if inner in ("son", "daughter", "child"):
                label = _gendered(sex.get(b_id), "son-in-law", "daughter-in-law", "child-in-law")
            elif inner in ("brother", "sister", "sibling"):
                label = _gendered(sex.get(b_id), "brother-in-law", "sister-in-law", "sibling-in-law")
            elif inner in ("father", "mother", "parent"):
                label = _gendered(sex.get(b_id), "step-father", "step-mother", "step-parent")
            else:
                label = f"{inner}'s spouse"
            path = _bfs_path(a_id, b_id, parents, children, spouses)
            return base.model_copy(
                update={
                    "found": True,
                    "label": label,
                    "path": path,
                    "chain": _chain(path, parents, children, spouses, sex),
                    "common_ancestor_ids": cas,
                }
            )

    path = _bfs_path(a_id, b_id, parents, children, spouses)
    if path:
        chain = _chain(path, parents, children, spouses, sex)
        return base.model_copy(
            update={"found": True, "label": "relative by marriage", "chain": chain, "path": path}
        )
    return base.model_copy(
        update={"explanation": f"No connection found between them and {b.preferred_display_name}"}
    )


def _bfs_path(a: uuid.UUID, b: uuid.UUID, parents: dict, children: dict, spouses: dict) -> list[uuid.UUID]:
    prev: dict[uuid.UUID, uuid.UUID | None] = {a: None}
    q = deque([a])
    while q:
        cur = q.popleft()
        if cur == b:
            break
        for nxt, _ in parents.get(cur, []) + children.get(cur, []) + spouses.get(cur, []):
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    if b not in prev:
        return []
    path = [b]
    while prev[path[-1]] is not None:
        path.append(prev[path[-1]])  # type: ignore[arg-type]
    return list(reversed(path))


def _chain(
    path: list[uuid.UUID],
    parents: dict,
    children: dict,
    spouses: dict,
    sex: dict[uuid.UUID, SexAtBirth | None],
) -> list[str]:
    """Kinship chain words (father, brother, wife…) so the UI can render regional terms (e.g. mama, bua)."""
    words: list[str] = []
    for x, y in pairwise(path):
        s = sex.get(y)
        if any(p == y for p, _ in parents.get(x, [])):
            words.append(_gendered(s, "father", "mother", "parent"))
        elif any(c == y for c, _ in children.get(x, [])):
            words.append(_gendered(s, "son", "daughter", "child"))
        else:
            words.append(_gendered(s, "husband", "wife", "spouse"))
    # collapse parent→child into sibling
    out: list[str] = []
    for w in words:
        if out and out[-1] in ("father", "mother", "parent") and w in ("son", "daughter", "child"):
            out[-1] = {"son": "brother", "daughter": "sister", "child": "sibling"}[w]
        else:
            out.append(w)
    return out
