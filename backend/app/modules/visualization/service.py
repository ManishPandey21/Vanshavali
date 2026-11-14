"""Visualization data shaping (ADR-0017).

Every function here builds its payload from the same privacy primitives as the rest of the API:
``lookup.visible_subjects`` (who you may see), the event serialiser (which redacts dates, places and
coordinates per field group) and ``geo.place_coordinates`` (coordinate privacy). Hidden people are
placeholders without names, dates or places. Payloads are compact and capped.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import Subject, level_allows
from app.core.config import get_settings
from app.core.errors import NotFound
from app.models import (
    Assertion,
    BranchMembership,
    ChartPreset,
    Citation,
    Document,
    DocumentDerivative,
    Event,
    EventMedia,
    EventParticipant,
    HouseholdMembership,
    Person,
    Place,
    Property,
    Relationship,
)
from app.models.enums import (
    PARENT_TYPES,
    UNION_TYPES,
    CitationTarget,
    DerivativeKind,
    EventSignificance,
    EventType,
    HeritageAttribute,
    Lineage,
    LocationPrecision,
    ParticipantRole,
    ProfileStatus,
    RelationshipType,
    SexAtBirth,
)
from app.modules.documents.access import can_view_document
from app.modules.genealogy import geo, lookup, provisional
from app.modules.genealogy.engine import _EXCLUDED_EVIDENCE, _reachable_without, _walk, absent_ids
from app.modules.genealogy.schemas import EventOut
from app.modules.genealogy.serialize import Serializer, _pick_vitals, _sort_key
from app.modules.visualization.schemas import (
    AncestryNode,
    AncestryOut,
    Completeness,
    GeoPoint,
    GraphEdgeOut,
    GraphNodeOut,
    HistoricalPeriod,
    LifespanEvent,
    LifespanRow,
    LifespansOut,
    MapOut,
    MapPath,
    MapPoint,
    NeighbourhoodOut,
    PlaceRef,
    PresetIn,
    PresetOut,
    PresetUpdate,
    StoryEvent,
    StoryOut,
    StoryPhoto,
    VizPerson,
)

MAX_ANCESTRY_GENERATIONS = 10
MAX_GRAPH_NODES = 300
MAX_LIFESPANS = 500
MAX_MAP_POINTS = 2000

# Neutral context bands for the lifespan timeline (editable list; dates are conventional).
HISTORICAL_PERIODS = [
    HistoricalPeriod(label="Company rule", start_year=1757, end_year=1858),
    HistoricalPeriod(label="British Raj", start_year=1858, end_year=1947),
    HistoricalPeriod(label="Independence and Partition", start_year=1947, end_year=1948),
    HistoricalPeriod(label="Republic of India", start_year=1950, end_year=dt.date.today().year),
]


def _geo(c: geo.Coordinates | None) -> GeoPoint | None:
    if c is None:
        return None
    return GeoPoint(latitude=c.latitude, longitude=c.longitude, precision=c.precision, coarsened=c.coarsened)


def place_ref(ctx: TreeContext, place: Place | None, *, name: str | None = None) -> PlaceRef | None:
    if place is None:
        return PlaceRef(name=name) if name else None
    return PlaceRef(
        id=place.id,
        name=place.map_label or place.canonical_name,
        district=place.district,
        state=place.state,
        country=place.country,
        geo=None if ctx.public else _geo(geo.place_coordinates(ctx, place)),
    )


def _places(ctx: TreeContext, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, Place]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {
        p.id: p
        for p in ctx.db.scalars(select(Place).where(Place.tree_id == ctx.tree_id, Place.id.in_(wanted)))
    }


# ---------------------------------------------------------------- people
def build_people(
    ctx: TreeContext, subjects: dict[uuid.UUID, Subject], *, completeness: bool = False
) -> dict[uuid.UUID, VizPerson]:
    """Compact, privacy-filtered person cards for already-visible subjects (batched queries)."""
    if not subjects:
        return {}
    ids = list(subjects)
    ser = Serializer(ctx)
    vitals_events = ser.events_for(ids, subjects, {EventType.BIRTH, EventType.DEATH})
    vitals = {pid: _pick_vitals(vitals_events.get(pid, []), pid) for pid in ids}
    places = _places(ctx, {v["birth"].place_id for v in vitals.values() if v["birth"]})
    villages: dict[uuid.UUID, str] = {}
    if not ctx.public:
        from app.modules.heritage.service import _visible

        for a in ctx.db.scalars(
            select(Assertion)
            .where(
                Assertion.tree_id == ctx.tree_id,
                Assertion.person_id.in_(ids),
                Assertion.attribute == HeritageAttribute.ANCESTRAL_VILLAGE.value,
            )
            .order_by(Assertion.is_preferred.desc())
        ):
            pid = a.person_id
            if pid is None or pid in villages or not _visible(ctx, a, subjects[pid]):
                continue
            label = a.value_text
            if a.place_id:
                pl = _places(ctx, [a.place_id]).get(a.place_id)
                label = (pl.map_label or pl.canonical_name) if pl else label
            if label:
                villages[pid] = label
    # visible principal events per person (private events are not counted)
    counts: dict[uuid.UUID, int] = defaultdict(int)
    for pid, level in ctx.db.execute(
        select(EventParticipant.person_id, Event.privacy_level)
        .join(Event, (Event.id == EventParticipant.event_id) & (Event.tree_id == EventParticipant.tree_id))
        .where(
            EventParticipant.tree_id == ctx.tree_id,
            EventParticipant.person_id.in_(ids),
            EventParticipant.role == ParticipantRole.PRINCIPAL,
        )
    ):
        if level is None or level_allows(ctx, level, subject=subjects[pid]):
            counts[pid] += 1
    parents: dict[uuid.UUID, int] = {}
    sourced: set[uuid.UUID] = set()
    if completeness:
        concealed = absent_ids(ctx)
        for child, parent in ctx.db.execute(
            select(Relationship.person_b_id, Relationship.person_a_id).where(
                Relationship.tree_id == ctx.tree_id,
                Relationship.person_b_id.in_(ids),
                Relationship.type.in_(list(PARENT_TYPES)),
            )
        ).all():
            if parent not in concealed:  # a concealed parent is not counted as recorded
                parents[child] = parents.get(child, 0) + 1
        sourced = set(
            ctx.db.scalars(
                select(Citation.target_id).where(
                    Citation.tree_id == ctx.tree_id,
                    Citation.target_type == CitationTarget.PERSON,
                    Citation.target_id.in_(ids),
                )
            )
        )
        ev_owner = dict(
            ctx.db.execute(
                select(EventParticipant.event_id, EventParticipant.person_id).where(
                    EventParticipant.tree_id == ctx.tree_id,
                    EventParticipant.person_id.in_(ids),
                    EventParticipant.role == ParticipantRole.PRINCIPAL,
                )
            ).all()
        )
        if ev_owner:
            for eid in ctx.db.scalars(
                select(Citation.target_id).where(
                    Citation.tree_id == ctx.tree_id,
                    Citation.target_type == CitationTarget.EVENT,
                    Citation.target_id.in_(list(ev_owner)),
                )
            ):
                sourced.add(ev_owner[eid])
    out: dict[uuid.UUID, VizPerson] = {}
    for pid, s in subjects.items():
        v = vitals[pid]
        summary = ser.summary(s, v)
        birth: EventOut | None = v["birth"]
        bp = None
        if birth is not None and (birth.place_id or birth.place_as_recorded):
            bp = place_ref(
                ctx, places.get(birth.place_id) if birth.place_id else None, name=birth.place_as_recorded
            )
        comp = None
        if completeness:
            checks = {
                "birth_date": summary.birth_year is not None,
                "birth_place": bp is not None,
                "parents": parents.get(pid, 0) > 0,
                "sources": pid in sourced,
            }
            if s.person.profile_status == ProfileStatus.DECEASED:
                checks["death_date"] = summary.death_year is not None
            comp = Completeness(
                score=round(sum(checks.values()) / len(checks), 2),
                missing=[k for k, ok in checks.items() if not ok],
            )
        out[pid] = VizPerson(
            id=pid,
            display_name=summary.display_name,
            sex=summary.sex_at_birth,
            profile_status=summary.profile_status,
            is_protected=summary.is_protected,
            birth_year=summary.birth_year,
            death_year=summary.death_year,
            birth_display=summary.birth_display,
            death_display=summary.death_display,
            birth_place=bp,
            village=villages.get(pid),
            branch_ids=[] if ctx.public else sorted(s.branch_ids, key=str),
            event_count=counts.get(pid, 0),
            completeness=comp,
        )
    return out


# ---------------------------------------------------------------- ancestry (fan + pedigree)
def _parent_rows(
    ctx: TreeContext, child_ids: list[uuid.UUID], lineages: set[Lineage] | None
) -> dict[uuid.UUID, list[Relationship]]:
    out: dict[uuid.UUID, list[Relationship]] = defaultdict(list)
    if not child_ids:
        return out
    concealed = absent_ids(ctx)  # never placeheld, never walked through
    for r in ctx.db.scalars(
        select(Relationship).where(
            Relationship.tree_id == ctx.tree_id,
            Relationship.person_b_id.in_(child_ids),
            Relationship.type.in_(list(PARENT_TYPES)),
            Relationship.evidence_status.not_in(list(_EXCLUDED_EVIDENCE)),
        )
    ):
        if lineages and (r.lineage or Lineage.BIOLOGICAL) not in lineages:
            continue
        if r.person_a_id in concealed:
            continue
        out[r.person_b_id].append(r)
    return out


_TYPE_ORDER = {
    RelationshipType.BIOLOGICAL_PARENT: 0,
    RelationshipType.ADOPTIVE_PARENT: 1,
    RelationshipType.STEP_PARENT: 2,
    RelationshipType.FOSTER_PARENT: 3,
    RelationshipType.GUARDIAN: 4,
}


def ancestry(
    ctx: TreeContext, root_id: uuid.UUID, generations: int, lineages: set[Lineage] | None
) -> AncestryOut:
    lookup.get_person_subject(ctx, root_id)
    generations = max(1, min(generations, MAX_ANCESTRY_GENERATIONS))
    slots: dict[int, uuid.UUID] = {1: root_id}
    frontier = {1: root_id}
    for _gen in range(1, generations + 1):
        rows = _parent_rows(ctx, list(set(frontier.values())), lineages)
        parent_ids = {r.person_a_id for rs in rows.values() for r in rs}
        sexes = (
            dict(
                ctx.db.execute(
                    select(Person.id, Person.sex_at_birth).where(
                        Person.tree_id == ctx.tree_id, Person.id.in_(parent_ids), Person.deleted_at.is_(None)
                    )
                ).all()
            )
            if parent_ids
            else {}
        )
        nxt: dict[int, uuid.UUID] = {}
        for slot, child in frontier.items():
            cands = sorted(
                (r for r in rows.get(child, []) if r.person_a_id in sexes),
                key=lambda r: (_TYPE_ORDER.get(r.type, 9), str(r.person_a_id)),
            )
            father = next((r.person_a_id for r in cands if sexes[r.person_a_id] == SexAtBirth.MALE), None)
            mother = next((r.person_a_id for r in cands if sexes[r.person_a_id] == SexAtBirth.FEMALE), None)
            for r in cands:  # unknown sex fills whichever slot is free
                if r.person_a_id in (father, mother):
                    continue
                if father is None:
                    father = r.person_a_id
                elif mother is None:
                    mother = r.person_a_id
            for s, pid in ((2 * slot, father), (2 * slot + 1, mother)):
                if pid is not None and pid not in slots.values():  # pedigree collapse: first slot wins
                    nxt[s] = pid
        slots.update(nxt)
        frontier = nxt
        if not frontier:
            break
    subjects = lookup.visible_subjects(ctx, set(slots.values()))
    people = build_people(ctx, subjects, completeness=True)
    nodes: list[AncestryNode] = []
    missing: list[int] = []
    for slot in sorted(slots):
        pid = slots[slot]
        gen = slot.bit_length() - 1
        side = "self" if slot == 1 else ("paternal" if (slot >> (gen - 1)) == 2 else "maternal")
        visible = pid in people
        if not visible and ctx.public:
            continue
        nodes.append(
            AncestryNode(slot=slot, generation=gen, side=side, hidden=not visible, person=people.get(pid))
        )
        if visible and gen < generations:
            missing += [s for s in (2 * slot, 2 * slot + 1) if s not in slots]
    # a pending provisional ancestor (unnamed or unverified, ADR-0020 §8) is "to complete", not
    # "known"; only viewers who can see them get this count (others never see them at all)
    pending = provisional.pending_ids(ctx)
    to_complete = sum(1 for n in nodes if n.slot > 1 and not n.hidden and slots[n.slot] in pending)
    known = sum(1 for n in nodes if n.slot > 1 and not n.hidden) - to_complete
    root_name = people[root_id].display_name if root_id in people else ""
    summary = (
        f"Ancestors of {root_name} over {generations} generations: {known} known, "
        + (f"{to_complete} to complete, " if to_complete else "")
        + f"{sum(1 for n in nodes if n.hidden)} private, {len(missing)} not yet recorded."
    )
    return AncestryOut(
        root_id=root_id, generations=generations, nodes=nodes, missing_slots=missing, summary=summary
    )


# ---------------------------------------------------------------- neighbourhood graph
def _edge_kind(t: RelationshipType) -> str:
    if t in PARENT_TYPES:
        return "parent"
    if t in UNION_TYPES:
        return "union"
    if t == RelationshipType.SIBLING:
        return "sibling"
    return "other"


def neighbourhood(
    ctx: TreeContext, root_id: uuid.UUID, radius: int, lineages: set[Lineage] | None, max_nodes: int
) -> NeighbourhoodOut:
    lookup.get_person_subject(ctx, root_id)
    radius = max(1, min(radius, 3))
    max_nodes = max(10, min(max_nodes, MAX_GRAPH_NODES))
    dist: dict[uuid.UUID, int] = {root_id: 0}
    rels: dict[uuid.UUID, Relationship] = {}
    frontier = {root_id}
    visible_ids: set[uuid.UUID] = {root_id}
    truncated = False
    concealed = absent_ids(ctx)
    for d in range(1, radius + 1):
        if not frontier:
            break
        rows = list(
            ctx.db.scalars(
                select(Relationship).where(
                    Relationship.tree_id == ctx.tree_id,
                    Relationship.person_a_id.in_(frontier) | Relationship.person_b_id.in_(frontier),
                    Relationship.evidence_status.not_in(list(_EXCLUDED_EVIDENCE)),
                )
            )
        )
        new: set[uuid.UUID] = set()
        for r in rows:
            if lineages and r.type in PARENT_TYPES and (r.lineage or Lineage.BIOLOGICAL) not in lineages:
                continue
            if r.person_a_id in concealed or r.person_b_id in concealed:
                continue  # concealed provisional people: no node, no edge, no placeholder
            rels[r.id] = r
            for other in (r.person_a_id, r.person_b_id):
                if other not in dist:
                    if len(dist) >= max_nodes:
                        truncated = True
                        continue
                    dist[other] = d
                    new.add(other)
        vis = set(lookup.visible_subjects(ctx, new))
        visible_ids |= vis
        frontier = vis  # never expand through someone hidden from you
    subjects = lookup.visible_subjects(ctx, visible_ids)
    people = build_people(ctx, subjects)
    households: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if not ctx.public and subjects:
        for pid, hid in ctx.db.execute(
            select(HouseholdMembership.person_id, HouseholdMembership.household_id).where(
                HouseholdMembership.tree_id == ctx.tree_id, HouseholdMembership.person_id.in_(list(subjects))
            )
        ):
            households[pid].append(hid)
    # does a visible boundary node have relatives outside the payload?
    boundary = [p for p in subjects if dist.get(p, 0) >= radius or truncated]
    expandable: set[uuid.UUID] = set()
    if boundary:
        for r in ctx.db.scalars(
            select(Relationship).where(
                Relationship.tree_id == ctx.tree_id,
                Relationship.person_a_id.in_(boundary) | Relationship.person_b_id.in_(boundary),
            )
        ):
            for a, b in ((r.person_a_id, r.person_b_id), (r.person_b_id, r.person_a_id)):
                if a in subjects and b not in dist and b not in concealed:
                    expandable.add(a)
    alias: dict[uuid.UUID, str] = {}
    nodes: list[GraphNodeOut] = []
    for i, (pid, d) in enumerate(sorted(dist.items(), key=lambda kv: (kv[1], str(kv[0])))):
        if pid in people:
            alias[pid] = str(pid)
            nodes.append(
                GraphNodeOut(
                    id=str(pid),
                    person=people[pid],
                    household_ids=households.get(pid, []),
                    distance=d,
                    expandable=pid in expandable,
                )
            )
        elif not ctx.public:
            alias[pid] = f"hidden-{i}"
            nodes.append(GraphNodeOut(id=alias[pid], hidden=True, distance=d))
    edges = []
    for r in rels.values():
        src, dst = alias.get(r.person_a_id), alias.get(r.person_b_id)
        if src is None or dst is None or (src.startswith("hidden") and dst.startswith("hidden")):
            continue
        edges.append(GraphEdgeOut(source=src, target=dst, kind=_edge_kind(r.type), type=r.type.value))
    return NeighbourhoodOut(root_id=root_id, radius=radius, nodes=nodes, edges=edges, truncated=truncated)


# ---------------------------------------------------------------- lifespans
def lifespans(
    ctx: TreeContext,
    root_id: uuid.UUID | None,
    generations: int,
    branch_id: uuid.UUID | None,
    include_events: bool,
    limit: int,
) -> LifespansOut:
    limit = max(1, min(limit, MAX_LIFESPANS))
    gen_of: dict[uuid.UUID, int] = {}
    if root_id is not None:
        lookup.get_person_subject(ctx, root_id)
        depth = max(1, min(generations, get_settings().max_traversal_depth))
        gen_of[root_id] = 0
        for direction, sign in (("ancestors", -1), ("descendants", 1)):
            walked = _walk(ctx, root_id, direction, depth, None)
            concealed = absent_ids(ctx)
            if concealed:
                walked = _reachable_without(walked, root_id, direction, concealed)
            for r in walked:
                node = r.parent if direction == "ancestors" else r.child
                gen_of.setdefault(node, sign * r.generation)
        candidates = set(gen_of)
    else:
        candidates = set(
            ctx.db.scalars(
                select(Person.id)
                .where(Person.tree_id == ctx.tree_id, Person.deleted_at.is_(None))
                .limit(5000)
            )
        )
    if branch_id is not None:
        members = set(
            ctx.db.scalars(
                select(BranchMembership.person_id).where(
                    BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == branch_id
                )
            )
        )
        candidates &= members
    subjects = lookup.visible_subjects(ctx, candidates)
    people = build_people(ctx, subjects)
    dated = sorted(
        (p for p in people.values() if p.birth_year is not None),
        key=lambda p: (p.birth_year or 0, p.display_name),
    )
    truncated = len(dated) > limit
    dated = dated[:limit]
    events_by: dict[uuid.UUID, list[LifespanEvent]] = defaultdict(list)
    if include_events and dated:
        ids = [p.id for p in dated]
        evs = Serializer(ctx).events_for(ids, {i: subjects[i] for i in ids})
        for pid, lst in evs.items():
            for e in lst:
                year = (e.date or {}).get("year")
                if not year or e.type in (EventType.BIRTH, EventType.DEATH):
                    continue
                if e.category is None and e.significance == EventSignificance.STANDARD:
                    continue
                events_by[pid].append(
                    LifespanEvent(event_id=e.id, year=int(year), label=_event_label(e), category=e.category)
                )
    this_year = dt.date.today().year
    rows = []
    for p in dated:
        deceased = p.profile_status == ProfileStatus.DECEASED
        rows.append(
            LifespanRow(
                person=p,
                generation=gen_of.get(p.id),
                start_year=p.birth_year or 0,
                end_year=p.death_year if deceased else None,
                end_known=(p.death_year is not None)
                if deceased
                else p.profile_status == ProfileStatus.LIVING,
                approximate=bool(p.birth_display and p.birth_display[:1].lower() in ("c", "b", "a")),
                events=events_by.get(p.id, []),
            )
        )
    min_year = min((r.start_year for r in rows), default=None)
    max_year = max((r.end_year or this_year for r in rows), default=None)
    overlap = ""
    if rows:
        alive_together = _max_overlap(rows, this_year)
        overlap = (
            f" At most {alive_together[0]} of them were alive at the same time (around {alive_together[1]})."
        )
    summary = (
        f"{len(rows)} lifespans from {min_year} to {max_year}." + overlap
        if rows
        else "No lifespans with known birth years."
    )
    return LifespansOut(
        rows=rows,
        periods=HISTORICAL_PERIODS,
        min_year=min_year,
        max_year=max_year,
        truncated=truncated,
        without_dates=len(people) - len([p for p in people.values() if p.birth_year is not None]),
        summary=summary,
    )


def _max_overlap(rows: list[LifespanRow], this_year: int) -> tuple[int, int]:
    deltas: dict[int, int] = defaultdict(int)
    for r in rows:
        deltas[r.start_year] += 1
        deltas[(r.end_year or this_year) + 1] -= 1
    best, best_year, cur = 0, rows[0].start_year, 0
    for y in sorted(deltas):
        cur += deltas[y]
        if cur > best:
            best, best_year = cur, y
    return best, best_year


def _event_label(e: EventOut) -> str:
    if e.title:
        return e.title
    return (e.category.value if e.category else e.type.value).replace("_", " ").capitalize()


# ---------------------------------------------------------------- story (lifetime event timeline)
def story(ctx: TreeContext, person_id: uuid.UUID) -> StoryOut:
    subject = lookup.get_person_subject(ctx, person_id)
    person = build_people(ctx, {person_id: subject}, completeness=True)[person_id]
    events = Serializer(ctx).events_for([person_id], {person_id: subject}).get(person_id, [])
    ids = {e.id for e in events}
    places = _places(ctx, {e.place_id for e in events})
    photos: dict[uuid.UUID, list[StoryPhoto]] = defaultdict(list)
    if ids and not ctx.public:
        rows = ctx.db.execute(
            select(EventMedia, Document)
            .join(
                Document, (Document.id == EventMedia.document_id) & (Document.tree_id == EventMedia.tree_id)
            )
            .where(
                EventMedia.tree_id == ctx.tree_id, EventMedia.event_id.in_(ids), Document.deleted_at.is_(None)
            )
            .order_by(EventMedia.is_cover.desc(), EventMedia.sort_order)
        ).all()
        visible = [(m, d) for m, d in rows if can_view_document(ctx, d)]
        thumbs = (
            set(
                ctx.db.scalars(
                    select(DocumentDerivative.document_id).where(
                        DocumentDerivative.tree_id == ctx.tree_id,
                        DocumentDerivative.document_id.in_([d.id for _, d in visible]),
                        DocumentDerivative.kind == DerivativeKind.THUMBNAIL,
                    )
                )
            )
            if visible
            else set()
        )
        for m, d in visible:
            photos[m.event_id].append(
                StoryPhoto(
                    media_id=m.id,
                    document_id=d.id,
                    caption=m.caption,
                    is_cover=m.is_cover,
                    has_thumbnail=d.id in thumbs,
                )
            )
    out = []
    for e in events:
        pl = places.get(e.place_id) if e.place_id else None
        ref = place_ref(ctx, pl, name=e.place_as_recorded)
        if ref is not None and e.latitude is not None and e.longitude is not None:
            ref.geo = GeoPoint(
                latitude=e.latitude,
                longitude=e.longitude,
                precision=e.location_precision
                or (ref.geo.precision if ref.geo else LocationPrecision.UNKNOWN),
            )
        out.append(
            StoryEvent(
                id=e.id,
                type=e.type.value,
                category=e.category.value if e.category else None,
                title=e.title,
                label=_event_label(e),
                date=e.date,
                date_display=e.date_display,
                year=(e.date or {}).get("year"),
                sort_key=_sort_key(e.date),
                place=ref,
                description=e.description,
                significance=e.significance.value,
                relatives=[
                    {
                        "person_id": str(p.person_id),
                        "display_name": p.display_name or "",
                        "role": p.role.value,
                    }
                    for p in e.participants
                    if p.person_id != person_id
                ],
                photos=photos.get(e.id, []),
                redacted_fields=e.redacted_fields,
            )
        )
    out.sort(key=lambda s: (s.sort_key, s.type))
    dated = [s for s in out if s.year]
    summary = f"{person.display_name}: {len(out)} life events"
    if dated:
        summary += f", from {dated[0].year} to {dated[-1].year}"
    return StoryOut(person=person, events=out, summary=summary + ".")


# ---------------------------------------------------------------- map
def geo_map(
    ctx: TreeContext, person_id: uuid.UUID | None, branch_id: uuid.UUID | None, include: set[str]
) -> MapOut:
    from app.modules.lifeevents.service import serialize_events

    points: list[MapPoint] = []
    paths: list[MapPath] = []
    not_geotagged = 0
    scope: set[uuid.UUID] | None = None
    if person_id is not None:
        lookup.get_person(ctx, person_id)
        scope = {person_id}
    if branch_id is not None:
        members = set(
            ctx.db.scalars(
                select(BranchMembership.person_id).where(
                    BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == branch_id
                )
            )
        )
        scope = members if scope is None else scope & members
    if "events" in include or "migrations" in include:
        stmt = select(Event).where(
            Event.tree_id == ctx.tree_id,
            Event.latitude.is_not(None) | Event.place_id.is_not(None) | Event.origin_place_id.is_not(None),
        )
        if scope is not None:
            stmt = stmt.where(
                Event.id.in_(
                    select(EventParticipant.event_id).where(
                        EventParticipant.tree_id == ctx.tree_id, EventParticipant.person_id.in_(scope)
                    )
                )
            )
        evs = serialize_events(ctx, list(ctx.db.scalars(stmt.limit(MAX_MAP_POINTS * 2))))
        places = _places(ctx, {e.place_id for e in evs} | {e.origin_place_id for e in evs})
        for e in evs:
            dest = _event_geo(
                ctx,
                e.latitude,
                e.longitude,
                e.location_precision,
                places.get(e.place_id) if e.place_id else None,
            )
            people = [p.person_id for p in e.participants if p.role == ParticipantRole.PRINCIPAL]
            year = (e.date or {}).get("year")
            if e.type == EventType.MIGRATION and "migrations" in include and e.origin_place_id:
                origin_pl = places.get(e.origin_place_id)
                origin = _geo(geo.place_coordinates(ctx, origin_pl)) if origin_pl else None
                if origin and dest:
                    paths.append(
                        MapPath(
                            event_id=e.id,
                            person_id=people[0] if people else None,
                            label=_event_label(e),
                            year=year,
                            origin=origin,
                            origin_label=origin_pl.map_label or origin_pl.canonical_name if origin_pl else "",
                            destination=dest,
                            destination_label=e.place_name or e.place_as_recorded or "",
                        )
                    )
            if "events" not in include:
                continue
            if dest is None:
                if e.place_id or e.place_as_recorded:
                    not_geotagged += 1
                continue
            who = ", ".join(
                p.display_name or "" for p in e.participants if p.role == ParticipantRole.PRINCIPAL
            )
            points.append(
                MapPoint(
                    id=f"event-{e.id}",
                    kind="event",
                    label=f"{_event_label(e)} — {who}" if who else _event_label(e),
                    geo=dest,
                    place_id=e.place_id,
                    event_id=e.id,
                    person_ids=people,
                    year=year,
                    category=(e.category.value if e.category else e.type.value),
                )
            )
    if "heritage" in include and not ctx.public:
        from app.modules.heritage.service import _visible

        stmt2 = select(Assertion).where(Assertion.tree_id == ctx.tree_id, Assertion.place_id.is_not(None))
        if scope is not None:
            stmt2 = stmt2.where(Assertion.person_id.in_(scope))
        rows = list(ctx.db.scalars(stmt2.limit(MAX_MAP_POINTS)))
        subj = lookup.visible_subjects(ctx, {a.person_id for a in rows if a.person_id})
        hplaces = _places(ctx, {a.place_id for a in rows})
        for a in rows:
            if a.person_id is not None and a.person_id not in subj:
                continue
            if not _visible(ctx, a, subj.get(a.person_id) if a.person_id else None):
                continue
            pl = hplaces.get(a.place_id) if a.place_id else None
            g = _geo(geo.place_coordinates(ctx, pl)) if pl else None
            if pl is None or g is None:
                not_geotagged += 1 if pl is not None else 0
                continue
            who = subj[a.person_id].person.preferred_display_name if a.person_id in subj else ""
            attr = a.attribute.replace("_", " ")
            points.append(
                MapPoint(
                    id=f"heritage-{a.id}",
                    kind="heritage",
                    label=f"{attr.capitalize()}: {pl.map_label or pl.canonical_name}"
                    + (f" — {who}" if who else ""),
                    geo=g,
                    place_id=pl.id,
                    person_ids=[a.person_id] if a.person_id else [],
                    category=a.attribute,
                )
            )
    if (
        "properties" in include
        and not ctx.public
        and (ctx.has(Permission.PROPERTY_READ) or ctx.has(Permission.PROPERTY_WRITE))
    ):
        from app.modules.property.service import can_view_property

        props = [
            p
            for p in ctx.db.scalars(
                select(Property)
                .where(Property.tree_id == ctx.tree_id, Property.place_id.is_not(None))
                .limit(500)
            )
            if can_view_property(ctx, p)
        ]
        pplaces = _places(ctx, {p.place_id for p in props})
        for p in props:
            pl = pplaces.get(p.place_id) if p.place_id else None
            g = _geo(geo.place_coordinates(ctx, pl)) if pl else None
            if g is None:
                continue
            points.append(
                MapPoint(
                    id=f"property-{p.id}",
                    kind="property",
                    label=p.display_name,
                    geo=g,
                    place_id=pl.id if pl else None,
                    category="property",
                )
            )
    if "places" in include and scope is None and not ctx.public:
        from app.models.enums import PlaceType

        special = [
            PlaceType.ANCESTRAL_HOUSE,
            PlaceType.TEMPLE,
            PlaceType.SHRINE,
            PlaceType.VILLAGE,
            PlaceType.LAND_PARCEL,
        ]
        used = {pt.place_id for pt in points if pt.place_id}
        for pl in ctx.db.scalars(
            select(Place)
            .where(Place.tree_id == ctx.tree_id, Place.place_type.in_(special), Place.latitude.is_not(None))
            .limit(MAX_MAP_POINTS)
        ):
            if pl.id in used:
                continue
            g = _geo(geo.place_coordinates(ctx, pl))
            if g is not None:
                points.append(
                    MapPoint(
                        id=f"place-{pl.id}",
                        kind="place",
                        label=pl.map_label or pl.canonical_name,
                        geo=g,
                        place_id=pl.id,
                        category=pl.place_type.value,
                    )
                )
    truncated = len(points) > MAX_MAP_POINTS
    return MapOut(
        points=points[:MAX_MAP_POINTS],
        paths=paths[:MAX_MAP_POINTS],
        not_geotagged=not_geotagged,
        truncated=truncated,
    )


def _event_geo(
    ctx: TreeContext, lat: float | None, lng: float | None, precision: Any, place: Place | None
) -> GeoPoint | None:
    if lat is not None and lng is not None:
        return GeoPoint(latitude=lat, longitude=lng, precision=precision or LocationPrecision.UNKNOWN)
    if place is not None:
        return _geo(geo.place_coordinates(ctx, place))
    return None


# ---------------------------------------------------------------- presets
def _preset_out(ctx: TreeContext, p: ChartPreset) -> PresetOut:
    return PresetOut.model_validate(p).model_copy(update={"mine": p.user_id == ctx.user_id})


def list_presets(ctx: TreeContext, chart_type: Any | None) -> list[PresetOut]:
    stmt = select(ChartPreset).where(
        ChartPreset.tree_id == ctx.tree_id,
        (ChartPreset.user_id == ctx.user_id) | ChartPreset.shared.is_(True),
    )
    if chart_type is not None:
        stmt = stmt.where(ChartPreset.chart_type == chart_type)
    return [_preset_out(ctx, p) for p in ctx.db.scalars(stmt.order_by(ChartPreset.name))]


def create_preset(ctx: TreeContext, body: PresetIn) -> PresetOut:
    if ctx.user_id is None:
        raise NotFound("Tree not found")
    count = ctx.db.scalar(
        select(func.count())
        .select_from(ChartPreset)
        .where(ChartPreset.tree_id == ctx.tree_id, ChartPreset.user_id == ctx.user_id)
    )
    if (count or 0) >= 100:
        from app.core.errors import Unprocessable

        raise Unprocessable("You can keep at most 100 chart presets in a tree", code="too_many_presets")
    p = ChartPreset(
        tree_id=ctx.tree_id,
        user_id=ctx.user_id,
        name=body.name.strip(),
        chart_type=body.chart_type,
        settings=body.settings,
        shared=body.shared,
        created_by=ctx.user_id,
    )
    ctx.db.add(p)
    ctx.db.flush()
    return _preset_out(ctx, p)


def _own_preset(ctx: TreeContext, preset_id: uuid.UUID, *, allow_admin: bool = False) -> ChartPreset:
    p = ctx.db.scalar(
        select(ChartPreset).where(ChartPreset.tree_id == ctx.tree_id, ChartPreset.id == preset_id)
    )
    if p is None or (p.user_id != ctx.user_id and not p.shared):
        raise NotFound("Preset not found")
    if p.user_id != ctx.user_id and not (allow_admin and ctx.is_admin):
        from app.core.errors import Forbidden

        raise Forbidden("Only the person who saved this preset can change it")
    return p


def update_preset(ctx: TreeContext, preset_id: uuid.UUID, body: PresetUpdate) -> PresetOut:
    p = _own_preset(ctx, preset_id)
    if body.name is not None:
        p.name = body.name.strip()
    if body.settings is not None:
        p.settings = body.settings
    if body.shared is not None:
        p.shared = body.shared
    p.updated_by = ctx.user_id
    ctx.db.flush()
    return _preset_out(ctx, p)


def delete_preset(ctx: TreeContext, preset_id: uuid.UUID) -> None:
    ctx.db.delete(_own_preset(ctx, preset_id, allow_admin=True))
