"""The complete family graph: every authorised person connected to someone, or the whole tree (ADR-0034).

Unlike ``engine.graph`` (one root, parent edges, one direction, a depth), this treats the family as a
graph: parent/child, union, explicit-sibling and "other" edges are all followed, in both directions,
with no generation limit. A visited set makes cycles (pedigree collapse, cousin marriage) harmless
and guarantees one node per person.

Three rules decide what is in it:

1. **Absent people are not there.** Removed, permanently deleted and concealed provisional people
   (``engine.absent_ids``) are dropped from the edge list before traversal: no node, no placeholder,
   and nothing is reached through them. A family may therefore fall into separate groups; nothing is
   invented to join them.
2. **Hidden people keep today's placeholder, and no more.** An active person the viewer may not see
   is an anonymous node. The walk continues past them along parent/child links only (what the
   ancestor and descendant views already do) and never through their marriages or sibling links into
   another family. Reached only by a marriage or sibling link, a hidden person is a leaf.
3. **Nothing leaves the tree.** Every query is filtered by ``tree_id`` (and by row-level security).

The result can be large, so it is served in pages (``nodes`` in a stable order, each edge on the page
that completes it). ``complete`` is true only on the last page; the client must not present a partial
result as the whole family. The cursor carries a *revision* of the tree; if the tree changes between
pages the next page is refused with 409 ``graph_changed`` and the client starts again, so pages from
two different states of the tree are never stitched together.
"""

from __future__ import annotations

import base64
import bisect
import hashlib
import json
import threading
import time
import uuid
from collections import OrderedDict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from sqlalchemy import func, select

from app.authz import lifecycle
from app.authz.context import TreeContext
from app.authz.privacy import Subject
from app.core.errors import Conflict, Unprocessable
from app.models import AccessGrant, BranchMembership, Person, Relationship
from app.models.enums import PARENT_TYPES, UNION_TYPES, EvidenceStatus, Lineage, RelationshipType
from app.modules.genealogy import lookup
from app.modules.genealogy.engine import absent_ids
from app.modules.genealogy.schemas import (
    FamilyGraphComponent,
    FamilyGraphEdge,
    FamilyGraphLink,
    FamilyGraphNode,
    FamilyGraphOut,
)
from app.modules.genealogy.serialize import Serializer

Scope = Literal["connected", "all"]

PAGE_DEFAULT = 500
PAGE_MAX = 1000
_CHUNK = 2000  # ids per IN (...) list
_EXCLUDED_EVIDENCE = (EvidenceStatus.DISPROVEN, EvidenceStatus.SUPERSEDED)
_TYPES = [*PARENT_TYPES, *UNION_TYPES, RelationshipType.SIBLING, RelationshipType.OTHER]

# how a node may be expanded
_FULL = "full"  # visible: every edge is followed
_LINEAL = "lineal"  # hidden, reached by a parent/child link: only parent/child links are followed
_LEAF = "leaf"  # hidden, reached only by a marriage/sibling/other link: not expanded


class _Rel(NamedTuple):
    id: uuid.UUID
    a: uuid.UUID
    b: uuid.UUID
    type: RelationshipType
    lineage: Lineage | None

    @property
    def lineal(self) -> bool:
        return self.type in PARENT_TYPES


def _chunks(ids: Iterable[uuid.UUID]) -> Iterable[list[uuid.UUID]]:
    batch: list[uuid.UUID] = []
    for i in ids:
        batch.append(i)
        if len(batch) >= _CHUNK:
            yield batch
            batch = []
    if batch:
        yield batch


class _Edges:
    """Adjacency of active people, loaded a frontier at a time (or all at once for the whole tree)."""

    def __init__(self, ctx: TreeContext) -> None:
        self.ctx = ctx
        self.absent = absent_ids(ctx)
        self.loaded: set[uuid.UUID] = set()
        self.seen: set[uuid.UUID] = set()
        self.by_person: dict[uuid.UUID, list[_Rel]] = {}
        self.everything = False

    def _stmt(self):  # type: ignore[no-untyped-def]
        return select(
            Relationship.id,
            Relationship.person_a_id,
            Relationship.person_b_id,
            Relationship.type,
            Relationship.lineage,
        ).where(
            Relationship.tree_id == self.ctx.tree_id,
            Relationship.type.in_(_TYPES),
            Relationship.evidence_status.notin_(list(_EXCLUDED_EVIDENCE)),
        )

    def _add(self, rows: Iterable[tuple]) -> None:  # type: ignore[type-arg]
        for row in rows:
            r = _Rel(row[0], row[1], row[2], RelationshipType(row[3]), Lineage(row[4]) if row[4] else None)
            if r.id in self.seen:
                continue
            self.seen.add(r.id)
            if r.a in self.absent or r.b in self.absent:
                continue  # rule 1: an absent person has no edges
            self.by_person.setdefault(r.a, []).append(r)
            self.by_person.setdefault(r.b, []).append(r)

    def load_all(self) -> None:
        self._add(self.ctx.db.execute(self._stmt()).all())
        self.everything = True

    def load(self, ids: Iterable[uuid.UUID]) -> None:
        if self.everything:
            return
        missing = [i for i in ids if i not in self.loaded]
        self.loaded.update(missing)
        for batch in _chunks(missing):
            self._add(
                self.ctx.db.execute(
                    self._stmt().where(
                        Relationship.person_a_id.in_(batch) | Relationship.person_b_id.in_(batch)
                    )
                ).all()
            )

    def of(self, person: uuid.UUID) -> list[_Rel]:
        return self.by_person.get(person, [])


class _Visibility:
    """Who the viewer may see, decided only by ``lookup.visible_subjects`` (the shared rule)."""

    def __init__(self, ctx: TreeContext) -> None:
        self.ctx = ctx
        self.subjects: dict[uuid.UUID, Subject] = {}
        self.checked: set[uuid.UUID] = set()

    def ensure(self, ids: Iterable[uuid.UUID]) -> None:
        missing = [i for i in ids if i not in self.checked]
        self.checked.update(missing)
        for batch in _chunks(missing):
            self.subjects.update(lookup.visible_subjects(self.ctx, batch))

    def visible(self, person: uuid.UUID) -> bool:
        return person in self.subjects


@dataclass
class _Component:
    order: list[uuid.UUID]  # breadth-first from the seed: near relatives first
    mode: dict[uuid.UUID, str]
    rels: list[_Rel]
    generation: dict[uuid.UUID, int] = field(default_factory=dict)


def _walk_component(ctx: TreeContext, seed: uuid.UUID, edges: _Edges, vis: _Visibility) -> _Component:
    mode: dict[uuid.UUID, str] = {seed: _FULL}
    order = [seed]
    frontier = [seed]
    while frontier:
        edges.load(frontier)
        found: dict[uuid.UUID, bool] = {}  # newly reached person -> reached by a parent/child link?
        upgraded: list[uuid.UUID] = []
        for cur in frontier:
            cur_mode = mode[cur]
            if cur_mode == _LEAF:
                continue
            for r in edges.of(cur):
                if cur_mode == _LINEAL and not r.lineal:
                    continue  # rule 2: never through a hidden person's marriage or sibling link
                other = r.b if r.a == cur else r.a
                known = mode.get(other)
                if known is None:
                    found[other] = found.get(other, False) or r.lineal
                elif known == _LEAF and r.lineal:
                    mode[other] = _LINEAL  # now also reached by descent: may be walked along it
                    upgraded.append(other)
        vis.ensure(found)
        nxt: list[uuid.UUID] = []
        for other in sorted(found):  # stable order: the same tree always pages the same way
            if vis.visible(other):
                mode[other] = _FULL
            elif ctx.public:
                continue  # public pages never carry placeholders
            else:
                mode[other] = _LINEAL if found[other] else _LEAF
            order.append(other)
            nxt.append(other)
        frontier = nxt + sorted(set(upgraded))
    rels: dict[uuid.UUID, _Rel] = {}
    for pid in order:
        for r in edges.of(pid):
            if r.a not in mode or r.b not in mode:
                continue
            a_hidden, b_hidden = mode[r.a] != _FULL, mode[r.b] != _FULL
            if not r.lineal and a_hidden and b_hidden:
                continue  # a link between two hidden people says nothing the viewer may know
            rels[r.id] = r
    comp = _Component(order=order, mode=mode, rels=sorted(rels.values(), key=lambda r: r.id))
    comp.generation = _generations(comp)
    return comp


def _generations(comp: _Component) -> dict[uuid.UUID, int]:
    """One row number per person so that partners and recorded siblings share a row and every child
    is below their parents, however the family was reached.

    Partners and explicit siblings are merged into a group; groups are layered by longest path over
    the parent links and then pulled down towards their children, so an in-law's parents sit one row
    above the in-law rather than at the top of the chart. A contradictory record (a marriage across
    generations) cannot loop: the link that would close a cycle is ignored for layering only.
    """
    parent: dict[uuid.UUID, uuid.UUID] = {p: p for p in comp.order}

    def find(x: uuid.UUID) -> uuid.UUID:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in comp.rels:
        if r.type in UNION_TYPES or r.type == RelationshipType.SIBLING:
            ra, rb = find(r.a), find(r.b)
            if ra != rb:
                lo, hi = sorted((ra, rb), key=str)
                parent[hi] = lo
    groups = sorted({find(p) for p in comp.order}, key=str)
    down: dict[uuid.UUID, set[uuid.UUID]] = {g: set() for g in groups}
    up: dict[uuid.UUID, set[uuid.UUID]] = {g: set() for g in groups}
    for r in comp.rels:
        if r.lineal:
            ga, gb = find(r.a), find(r.b)
            if ga != gb:
                down[ga].add(gb)
                up[gb].add(ga)
    indeg = {g: len(up[g]) for g in groups}
    ready = deque(g for g in groups if indeg[g] == 0)
    topo: list[uuid.UUID] = []
    done: set[uuid.UUID] = set()
    ignored: set[tuple[uuid.UUID, uuid.UUID]] = set()
    remaining = set(groups)
    while remaining:
        if not ready:  # a cycle between groups: release its least constrained member
            g = min(remaining, key=lambda x: (indeg[x], str(x)))
            for p in up[g]:
                if p not in done:
                    ignored.add((p, g))
            indeg[g] = 0
            ready.append(g)
        g = ready.popleft()
        if g in done:
            continue
        done.add(g)
        remaining.discard(g)
        topo.append(g)
        for c in sorted(down[g], key=str):
            if c in done or (g, c) in ignored:
                continue
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
    layer: dict[uuid.UUID, int] = {}
    for g in topo:
        layer[g] = max((layer[p] + 1 for p in up[g] if (p, g) not in ignored and p in layer), default=0)
    for g in reversed(topo):
        kids = [layer[c] for c in down[g] if (g, c) not in ignored]
        if kids:
            layer[g] = max(layer[g], min(kids) - 1)
    base = layer[find(comp.order[0])]
    return {p: layer[find(p)] - base for p in comp.order}


@dataclass
class _Graph:
    components: list[_Component]
    subjects: dict[uuid.UUID, Subject]


def _traverse(ctx: TreeContext, scope: Scope, root_id: uuid.UUID | None) -> _Graph:
    edges = _Edges(ctx)
    vis = _Visibility(ctx)
    if root_id is not None:
        vis.ensure([root_id])
        return _Graph([_walk_component(ctx, root_id, edges, vis)], vis.subjects)
    # the whole tree: every active person the viewer may see starts or joins a group
    edges.load_all()
    inactive = lifecycle.inactive_person_ids(ctx)
    everyone = [
        pid
        for pid in ctx.db.scalars(
            select(Person.id).where(
                Person.tree_id == ctx.tree_id, Person.deleted_at.is_(None), Person.erased_at.is_(None)
            )
        )
        if pid not in inactive and pid not in edges.absent
    ]
    vis.ensure(everyone)
    placed: set[uuid.UUID] = set()
    components: list[_Component] = []
    for pid in sorted(everyone):
        if pid in placed or not vis.visible(pid):
            continue  # a group nobody visible belongs to is not shown at all
        comp = _walk_component(ctx, pid, edges, vis)
        placed.update(p for p in comp.order if comp.mode[p] == _FULL)
        components.append(comp)
    components.sort(key=lambda c: (-len(c.order), c.order[0]))
    return _Graph(components, vis.subjects)


@dataclass(frozen=True)
class _Plan:
    """The whole authorised result in its final order, as ids and positions only (no personal data).

    Serving a page from it needs nothing but the page's own people. It is valid for exactly one
    revision of the tree and one viewer.
    """

    seq: tuple[tuple[int, uuid.UUID], ...]  # (group, person) in page order
    full: tuple[bool, ...]  # visible to the viewer (else an anonymous placeholder)
    generation: tuple[int, ...]
    # (position of the later endpoint, position a, position b, type, lineage), sorted by the first
    rels: tuple[tuple[int, int, int, RelationshipType, Lineage | None], ...]
    components: tuple[tuple[int, int], ...]  # (nodes, visible people) per group
    total_people: int


def _plan(ctx: TreeContext, scope: Scope, root_id: uuid.UUID | None) -> _Plan:
    graph = _traverse(ctx, scope, root_id)
    index: dict[tuple[int, uuid.UUID], int] = {}
    seq: list[tuple[int, uuid.UUID]] = []
    full: list[bool] = []
    generation: list[int] = []
    for ci, comp in enumerate(graph.components):
        for pid in comp.order:
            index[(ci, pid)] = len(seq)
            seq.append((ci, pid))
            full.append(comp.mode[pid] == _FULL)
            generation.append(comp.generation[pid])
    rels = sorted(
        (
            (max(index[(ci, r.a)], index[(ci, r.b)]), index[(ci, r.a)], index[(ci, r.b)], r.type, r.lineage)
            for ci, comp in enumerate(graph.components)
            for r in comp.rels
        ),
        key=lambda t: t[:3],
    )
    return _Plan(
        seq=tuple(seq),
        full=tuple(full),
        generation=tuple(generation),
        rels=tuple(rels),
        components=tuple(
            (len(c.order), sum(1 for p in c.order if c.mode[p] == _FULL)) for c in graph.components
        ),
        total_people=sum(full),
    )


# A family is read in several pages, and the traversal is the expensive part. The plan for one
# (tree, viewer, scope, root, revision) is kept briefly in this process so later pages only load
# their own people. It can never serve a stale tree: the revision in the key is read from the
# database on every request and changes with any person or relationship change (removal, restore
# and deletion included). It holds ids only, and each page still re-checks that the viewer may see
# every person on it (see family_graph). Other processes simply compute their own.
_PLAN_TTL_SECONDS = 120.0
_PLAN_CACHE_SIZE = 16
_plans: OrderedDict[tuple[object, ...], tuple[float, _Plan]] = OrderedDict()
_plans_lock = threading.Lock()


def _cached_plan(
    ctx: TreeContext, scope: Scope, root_id: uuid.UUID | None, rev: str, *, fresh: bool = False
) -> _Plan:
    key = (ctx.tree_id, ctx.membership_id, scope, root_id, rev)
    now = time.monotonic()
    if not fresh:
        with _plans_lock:
            hit = _plans.get(key)
            if hit is not None and hit[0] > now:
                _plans.move_to_end(key)
                return hit[1]
    plan = _plan(ctx, scope, root_id)
    with _plans_lock:
        _plans[key] = (now + _PLAN_TTL_SECONDS, plan)
        _plans.move_to_end(key)
        while len(_plans) > _PLAN_CACHE_SIZE:
            _plans.popitem(last=False)
    return plan


def forget_plans() -> None:
    """Tests only: start from an empty cache."""
    with _plans_lock:
        _plans.clear()


def revision(ctx: TreeContext) -> str:
    """Changes whenever a person or relationship of the tree is added, changed, removed or deleted,
    a grant or branch membership changes, or the viewer's own role changes. Opaque; carries no data."""
    rel = ctx.db.execute(
        select(func.count(), func.max(Relationship.updated_at)).where(Relationship.tree_id == ctx.tree_id)
    ).one()
    per = ctx.db.execute(
        select(func.count(), func.max(Person.updated_at), func.count(Person.deleted_at)).where(
            Person.tree_id == ctx.tree_id
        )
    ).one()
    # what else decides who this viewer may see: explicit grants and branch membership
    grants = ctx.db.execute(
        select(func.count(), func.max(AccessGrant.updated_at)).where(AccessGrant.tree_id == ctx.tree_id)
    ).one()
    branches = ctx.db.execute(
        select(func.count(), func.max(BranchMembership.updated_at)).where(
            BranchMembership.tree_id == ctx.tree_id
        )
    ).one()
    viewer = [str(ctx.membership_id), sorted(r.value for r in ctx.roles), str(ctx.branch_scope)]
    raw = json.dumps([[str(x) for x in row] for row in (rel, per, grants, branches)] + [viewer])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _encode_cursor(offset: int, rev: str, scope: str, root_id: uuid.UUID | None) -> str:
    raw = json.dumps({"o": offset, "r": rev, "s": scope, "p": str(root_id) if root_id else None})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str, scope: str, root_id: uuid.UUID | None) -> tuple[int, str]:
    """The cursor only names a position and the tree revision it belongs to. Every page is authorised
    again from scratch, so a forged cursor can at most ask for a different page of what the caller
    may already see."""
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        offset, rev = int(data["o"]), str(data["r"])
        same = data["s"] == scope and data["p"] == (str(root_id) if root_id else None)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise Unprocessable("Invalid cursor", code="invalid_cursor") from None
    if not same or offset < 0:
        raise Unprocessable("Invalid cursor", code="invalid_cursor")
    return offset, rev


def family_graph(
    ctx: TreeContext,
    scope: Scope,
    root_id: uuid.UUID | None,
    cursor: str | None = None,
    limit: int = PAGE_DEFAULT,
) -> FamilyGraphOut:
    if scope == "connected":
        if root_id is None:
            raise Unprocessable("person_id is required for the connected family", code="person_required")
        lookup.get_person_subject(ctx, root_id)  # 404 if absent or hidden: never a root
    else:
        root_id = None
    limit = max(1, min(limit, PAGE_MAX))
    rev = revision(ctx)
    offset = 0
    if cursor:
        offset, cursor_rev = _decode_cursor(cursor, scope, root_id)
        if cursor_rev != rev:
            raise Conflict(
                "The family tree changed while it was loading. Load it again.", code="graph_changed"
            )
    plan = _cached_plan(ctx, scope, root_id, rev)
    total = len(plan.seq)
    if offset > total:
        raise Unprocessable("Invalid cursor", code="invalid_cursor")
    end = min(total, offset + limit)

    # Authorise this page now, whatever the plan says: only people the shared visibility rule
    # returns are named. If the plan is out of step with it (a grant or branch changed without
    # touching the tree), rebuild once from the database and serve that.
    def page_subjects(p: _Plan) -> tuple[dict[uuid.UUID, Subject], bool]:
        wanted = [p.seq[i][1] for i in range(offset, min(len(p.seq), offset + limit)) if p.full[i]]
        subjects = lookup.visible_subjects(ctx, wanted)
        return subjects, len(subjects) == len(set(wanted))

    subjects, in_step = page_subjects(plan)
    if not in_step:
        plan = _cached_plan(ctx, scope, root_id, rev, fresh=True)
        total = len(plan.seq)
        end = min(total, offset + limit)
        subjects, in_step = page_subjects(plan)
        if not in_step:  # changed again under us: let the client start over rather than guess
            raise Conflict(
                "The family tree changed while it was loading. Load it again.", code="graph_changed"
            )
    summaries = Serializer(ctx).summaries(subjects)

    def node_id(i: int) -> str:
        ci, pid = plan.seq[i]
        # a placeholder's alias is its position only, never derived from the hidden person's id
        return str(pid) if plan.full[i] else f"hidden-{ci}-{i}"

    nodes = [
        FamilyGraphNode(
            id=node_id(i),
            person=summaries[plan.seq[i][1]] if plan.full[i] else None,
            hidden=not plan.full[i],
            generation=plan.generation[i],
            component=plan.seq[i][0],
        )
        for i in range(offset, end)
    ]
    edges: list[FamilyGraphEdge] = []
    links: list[FamilyGraphLink] = []
    start = bisect.bisect_left(plan.rels, offset, key=lambda t: t[0])
    for last, ia, ib, rtype, lineage in plan.rels[start:]:
        if last >= end:
            break  # each edge travels with the later of its two people: exactly once
        a, b = node_id(ia), node_id(ib)
        if rtype in PARENT_TYPES:
            edges.append(FamilyGraphEdge(source=a, target=b, type=rtype, lineage=lineage))
        else:
            kind: Literal["union", "sibling", "other"] = (
                "union"
                if rtype in UNION_TYPES
                else "sibling"
                if rtype == RelationshipType.SIBLING
                else "other"
            )
            links.append(FamilyGraphLink(a=a, b=b, kind=kind, type=rtype))
    complete = end >= total
    return FamilyGraphOut(
        scope=scope,
        root_id=root_id,
        revision=rev,
        total_nodes=total,
        total_people=plan.total_people,
        offset=offset,
        nodes=nodes,
        edges=edges,
        links=links,
        components=[
            FamilyGraphComponent(index=ci, size=size, people=people)
            for ci, (size, people) in enumerate(plan.components)
        ]
        if offset == 0
        else [],
        complete=complete,
        next_cursor=None if complete else _encode_cursor(end, rev, scope, root_id),
    )
