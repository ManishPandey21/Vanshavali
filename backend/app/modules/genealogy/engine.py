"""Family relationship engine: family units, ancestry traversal, relationship calculator (PRS §25)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, NamedTuple

from sqlalchemy import or_, select, text

from app.authz.context import TreeContext
from app.core.config import get_settings
from app.models import Person, Relationship
from app.models.enums import PARENT_TYPES, UNION_TYPES, EvidenceStatus, Lineage, RelationshipType, SexAtBirth
from app.modules.genealogy import ageorder, lookup, provisional
from app.modules.genealogy.schemas import (
    AgeOrderOut,
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


def _removed_person_ids(ctx: TreeContext) -> frozenset[uuid.UUID]:
    """Non-displayable vertices. Privacy-hidden people are intentionally NOT included.

    The irreversible erasure path retains an anonymous structural record for archival
    integrity; it must not surface as a person, placeholder or traversable bridge in
    any interactive family graph.
    """
    return frozenset(
        ctx.db.scalars(
            select(Person.id).where(
                Person.tree_id == ctx.tree_id,
                or_(
                    Person.deleted_at.is_not(None),
                    Person.preferred_display_name == "Erased person",
                ),
            )
        )
    )


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
    # concealed provisional people are left out entirely: no "private relative" placeholder
    excluded = provisional.concealed_ids(ctx) | _removed_person_ids(ctx)
    rels = [r for r in rels if r.person_a_id not in excluded and r.person_b_id not in excluded]
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
        shared = [r for r in shared if r.person_b_id not in excluded]
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


def _reachable_without(
    rows: list[_Row], root_id: uuid.UUID, direction: str, concealed: frozenset[uuid.UUID]
) -> list[_Row]:
    """The walk's edges still reachable from the root once concealed people are taken out.

    Nobody is reached *through* a concealed provisional person, so an ancestor beyond one does not
    appear as an unexplained node that would reveal the gap.
    """
    up = direction == "ancestors"
    by_from: dict[uuid.UUID, list[_Row]] = {}
    for r in rows:
        if r.parent in concealed or r.child in concealed:
            continue
        by_from.setdefault(r.child if up else r.parent, []).append(r)
    keep: list[_Row] = []
    reached = {root_id}
    frontier = [root_id]
    while frontier:
        nxt: list[uuid.UUID] = []
        for node in frontier:
            for r in by_from.get(node, []):
                keep.append(r)
                to = r.parent if up else r.child
                if to not in reached:
                    reached.add(to)
                    nxt.append(to)
        frontier = nxt
    return keep


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
    excluded = provisional.concealed_ids(ctx) | _removed_person_ids(ctx)
    if excluded:
        rows = _reachable_without(rows, root_id, direction, excluded)
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
        union_rows = [u for u in union_rows if u.person_a_id not in excluded and u.person_b_id not in excluded]
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


Adjacency = dict[uuid.UUID, list[tuple[uuid.UUID, _Edge]]]

# Namespace for the virtual parent an explicit sibling pair shares (ADR-0020 §3). Virtual ids never
# leave the engine: they are stripped from paths and common ancestors before anything is returned.
_VIRTUAL_PARENT_NS = uuid.UUID("6f1d3c2e-8a54-4b7e-9c10-5a2b7e9d4f31")


def virtual_parent_id(a: uuid.UUID, b: uuid.UUID) -> uuid.UUID:
    lo, hi = sorted((a, b), key=str)
    return uuid.uuid5(_VIRTUAL_PARENT_NS, f"{lo}:{hi}")


class _LazyGraph:
    """Relationship edges loaded on demand, one batched query per BFS frontier.

    The calculator only ever needs the neighbourhood of the two people: their ancestors and, for
    in-law and marriage paths, a breadth-first search between them. Loading the whole edge list per
    call made this endpoint dominate worker CPU at 10k people (docs/operations/performance.md).
    """

    def __init__(self, ctx: TreeContext, lineages: set[Lineage] | None) -> None:
        self.ctx = ctx
        self.lineages = lineages
        self.loaded: set[uuid.UUID] = set()
        self.seen_edges: set[uuid.UUID] = set()
        self.virtual: set[uuid.UUID] = set()
        # deleted people and concealed provisional people are not walked through at all
        self.deleted = set(
            ctx.db.scalars(
                select(Person.id).where(Person.tree_id == ctx.tree_id, Person.deleted_at.is_not(None))
            )
        ) | provisional.concealed_ids(ctx)
        self._parents: Adjacency = {}
        self._children: Adjacency = {}
        self._spouses: Adjacency = {}
        self.parents = _LazyAdjacency(self, self._parents)
        self.children = _LazyAdjacency(self, self._children)
        self.spouses = _LazyAdjacency(self, self._spouses)

    def prefetch(self, ids: Iterable[uuid.UUID]) -> None:
        missing = [i for i in set(ids) if i not in self.loaded]
        if not missing:
            return
        self.loaded.update(missing)
        rows = self.ctx.db.execute(
            select(
                Relationship.id,
                Relationship.person_a_id,
                Relationship.person_b_id,
                Relationship.type,
                Relationship.lineage,
            ).where(
                Relationship.tree_id == self.ctx.tree_id,
                Relationship.evidence_status.notin_(list(_EXCLUDED_EVIDENCE)),
                or_(Relationship.person_a_id.in_(missing), Relationship.person_b_id.in_(missing)),
            )
        ).all()
        for row in rows:
            r = _Edge(*row)
            if r.id in self.seen_edges:
                continue
            self.seen_edges.add(r.id)
            if r.person_a_id in self.deleted or r.person_b_id in self.deleted:
                continue
            if r.type in PARENT_TYPES:
                if not _lineage_filter(self.lineages, r):
                    continue
                self._parents.setdefault(r.person_b_id, []).append((r.person_a_id, r))
                self._children.setdefault(r.person_a_id, []).append((r.person_b_id, r))
            elif r.type in UNION_TYPES:
                self._spouses.setdefault(r.person_a_id, []).append((r.person_b_id, r))
                self._spouses.setdefault(r.person_b_id, []).append((r.person_a_id, r))
            elif r.type == RelationshipType.SIBLING:
                # An explicit sibling edge (parents not recorded): the pair shares a virtual parent, so
                # the calculator resolves brother, uncle, cousin… through it like a real one.
                v = virtual_parent_id(r.person_a_id, r.person_b_id)
                self.virtual.add(v)
                self.loaded.add(v)  # nothing to load from the database for it
                for child in (r.person_a_id, r.person_b_id):
                    self._parents.setdefault(child, []).append((v, r))
                    self._children.setdefault(v, []).append((child, r))


class _LazyAdjacency:
    """Read-only ``dict.get`` view that loads a node's edges the first time it is asked for."""

    def __init__(self, graph: _LazyGraph, data: Adjacency) -> None:
        self.graph = graph
        self.data = data

    def get(
        self, node: uuid.UUID, default: list[tuple[uuid.UUID, _Edge]] | None = None
    ) -> list[tuple[uuid.UUID, _Edge]]:
        if node not in self.graph.loaded:
            self.graph.prefetch([node])
        return self.data.get(node, default if default is not None else [])


def _ancestors_with_depth(
    start: uuid.UUID, parents: _LazyAdjacency, limit: int, via: dict[uuid.UUID, uuid.UUID] | None = None
) -> dict[uuid.UUID, int]:
    """Generation distance to every ancestor; ``via`` records the child each ancestor was reached from."""
    out = {start: 0}
    frontier = [start]
    depth = 0
    while frontier and depth < limit:
        parents.graph.prefetch(frontier)
        nxt: list[uuid.UUID] = []
        for cur in frontier:
            for p, _ in parents.get(cur, []):
                if p not in out:
                    out[p] = depth + 1
                    nxt.append(p)
                    if via is not None:
                        via[p] = cur
        frontier = nxt
        depth += 1
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
    lazy = _LazyGraph(ctx, lineages)
    graph = (lazy.parents, lazy.children, lazy.spouses)

    def real(o: RelationshipPathOut) -> RelationshipPathOut:
        """Drop virtual sibling parents: they are a calculation device, not people."""
        if not lazy.virtual:
            return o
        return o.model_copy(
            update={
                "path": [p for p in o.path if p not in lazy.virtual],
                "common_ancestor_ids": [c for c in o.common_ancestor_ids if c not in lazy.virtual],
            }
        )

    # pass 1 without sex data finds the path; only the people it touches are then loaded
    out = real(_relationship_path_raw(ctx, a_id, b_id, graph, {}))
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
    raw = _relationship_path_raw(ctx, a_id, b_id, graph, sex)
    out = real(raw)
    age_orders: list[AgeOrderOut] = []
    if raw.found and len(raw.path) > 1:
        hops = _chain_hops([p for p in raw.path if p is not None], *graph, sex)
        if [w for w, _, _ in hops] == raw.chain:  # direct non-biological edges carry their own words
            age_orders = ageorder.for_sibling_hops(ctx, hops, visible)
    return out.model_copy(
        update={
            "path": [p if p in visible else None for p in out.path],
            "common_ancestor_ids": [c for c in out.common_ancestor_ids if c in visible],
            "age_orders": age_orders,
        }
    )


def _relationship_path_raw(
    ctx: TreeContext,
    a_id: uuid.UUID,
    b_id: uuid.UUID,
    graph: tuple[_LazyAdjacency, _LazyAdjacency, _LazyAdjacency],
    sex: dict[uuid.UUID, SexAtBirth | None],
) -> RelationshipPathOut:
    b = lookup.get_person(ctx, b_id)
    limit = get_settings().max_traversal_depth
    parents, children, spouses = graph

    def blood(x: uuid.UUID, y: uuid.UUID) -> tuple[int, int, list[uuid.UUID], list[uuid.UUID]] | None:
        """(up, down, common ancestors, path x → common ancestor → y), or None if not blood kin."""
        via_x: dict[uuid.UUID, uuid.UUID] = {}
        via_y: dict[uuid.UUID, uuid.UUID] = {}
        ax = _ancestors_with_depth(x, parents, limit, via_x)
        ay = _ancestors_with_depth(y, parents, limit, via_y)
        common = set(ax) & set(ay)
        if not common:
            return None
        best = min(ax[c] + ay[c] for c in common)
        cas = [c for c in common if ax[c] + ay[c] == best]
        c0 = min(cas, key=lambda c: (ax[c], str(c)))

        def up_to(start: uuid.UUID, via: dict[uuid.UUID, uuid.UUID]) -> list[uuid.UUID]:
            chain = [c0]
            while chain[-1] != start:
                chain.append(via[chain[-1]])
            return chain  # c0 … start

        # built from the two upward searches: no downward search through the whole tree
        path = [*reversed(up_to(x, via_x)), *up_to(y, via_y)[1:]]
        return ax[c0], ay[c0], cas, path

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
        up, down, cas, path = res
        a_par = {p for p, r in parents.get(a_id, []) if r.type == RelationshipType.BIOLOGICAL_PARENT}
        b_par = {p for p, r in parents.get(b_id, []) if r.type == RelationshipType.BIOLOGICAL_PARENT}
        half = up == 1 and down == 1 and len(a_par & b_par) == 1 and (len(a_par) > 1 or len(b_par) > 1)
        label = _blood_label(up, down, sex.get(b_id), half)
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
            up, down, cas, blood_path = r2
            inner = _blood_label(up, down, sex.get(b_id), False)
            label = {
                "father": "father-in-law",
                "mother": "mother-in-law",
                "parent": "parent-in-law",
                "brother": "brother-in-law",
                "sister": "sister-in-law",
                "sibling": "sibling-in-law",
            }.get(inner, f"spouse's {inner}")
            path = [a_id, *blood_path]
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
            up, down, cas, blood_path = r2
            inner = _blood_label(up, down, sex.get(sp), False)
            if inner in ("son", "daughter", "child"):
                label = _gendered(sex.get(b_id), "son-in-law", "daughter-in-law", "child-in-law")
            elif inner in ("brother", "sister", "sibling"):
                label = _gendered(sex.get(b_id), "brother-in-law", "sister-in-law", "sibling-in-law")
            elif inner in ("father", "mother", "parent"):
                label = _gendered(sex.get(b_id), "step-father", "step-mother", "step-parent")
            else:
                label = f"{inner}'s spouse"
            path = [*blood_path, b_id]
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


def _hops(prev: dict[uuid.UUID, uuid.UUID | None], n: uuid.UUID) -> int:
    k = 0
    while prev[n] is not None:
        n = prev[n]  # type: ignore[assignment]
        k += 1
    return k


def _bfs_path(
    a: uuid.UUID,
    b: uuid.UUID,
    parents: _LazyAdjacency,
    children: _LazyAdjacency,
    spouses: _LazyAdjacency | None,
) -> list[uuid.UUID]:
    """Shortest path a → b (``spouses=None``: parent/child edges only).

    Bidirectional: the smaller frontier is expanded each round, so an unrelated pair explores far
    less of a large tree than a one-sided search would.
    """
    if a == b:
        return [a]

    def neighbours(n: uuid.UUID) -> list[tuple[uuid.UUID, _Edge]]:
        return parents.get(n, []) + children.get(n, []) + (spouses.get(n, []) if spouses else [])

    prev_a: dict[uuid.UUID, uuid.UUID | None] = {a: None}
    prev_b: dict[uuid.UUID, uuid.UUID | None] = {b: None}
    front_a, front_b = [a], [b]
    meet: uuid.UUID | None = None
    while front_a and front_b and meet is None:
        grow_a = len(front_a) <= len(front_b)
        front, prev, other = (front_a, prev_a, prev_b) if grow_a else (front_b, prev_b, prev_a)
        parents.graph.prefetch(front)
        nxt: list[uuid.UUID] = []
        meets: list[uuid.UUID] = []
        for cur in front:
            for n, _ in neighbours(cur):
                if n not in prev:
                    prev[n] = cur
                    nxt.append(n)
                    if n in other:
                        meets.append(n)
        if meets:  # all are equally far on this side; take the one nearest the other end
            meet = min(meets, key=lambda n: (_hops(other, n), str(n)))
        if grow_a:
            front_a = nxt
        else:
            front_b = nxt
    if meet is None:
        return []
    left = [meet]
    while prev_a[left[-1]] is not None:
        left.append(prev_a[left[-1]])  # type: ignore[arg-type]
    right = [meet]
    while prev_b[right[-1]] is not None:
        right.append(prev_b[right[-1]])  # type: ignore[arg-type]
    return [*reversed(left), *right[1:]]


def _chain_hops(
    path: list[uuid.UUID],
    parents: _LazyAdjacency,
    children: _LazyAdjacency,
    spouses: _LazyAdjacency,
    sex: dict[uuid.UUID, SexAtBirth | None],
) -> list[tuple[str, uuid.UUID, uuid.UUID]]:
    """Kinship chain words with the two people each word joins: ``("brother", father, uncle)``.

    A parent→child step collapses into a sibling word joining the two children, so age order is
    compared between the right pair (the uncle and the *father* for Tau/Chacha), never the viewer.
    """
    hops: list[tuple[str, uuid.UUID, uuid.UUID]] = []
    parents.graph.prefetch(path)
    for x, y in pairwise(path):
        s = sex.get(y)
        if any(p == y for p, _ in parents.get(x, [])):
            word = _gendered(s, "father", "mother", "parent")
        elif any(c == y for c, _ in children.get(x, [])):
            word = _gendered(s, "son", "daughter", "child")
        else:
            word = _gendered(s, "husband", "wife", "spouse")
        if hops and hops[-1][0] in ("father", "mother", "parent") and word in ("son", "daughter", "child"):
            sibling = {"son": "brother", "daughter": "sister", "child": "sibling"}[word]
            hops[-1] = (sibling, hops[-1][1], y)
        else:
            hops.append((word, x, y))
    return hops


def _chain(
    path: list[uuid.UUID],
    parents: _LazyAdjacency,
    children: _LazyAdjacency,
    spouses: _LazyAdjacency,
    sex: dict[uuid.UUID, SexAtBirth | None],
) -> list[str]:
    """Kinship chain words (father, brother, wife…) so the UI can render regional terms (e.g. mama, bua)."""
    return [w for w, _, _ in _chain_hops(path, parents, children, spouses, sex)]
