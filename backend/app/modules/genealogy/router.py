from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select

from app.api.deps import TreeCtx
from app.api.schemas import ApiModel, Message, Page, decode_cursor, encode_cursor
from app.authz.privacy import can_view_person, load_subjects
from app.core.textnorm import search_key
from app.models import Person, Place
from app.models.enums import EventType, Lineage, ProfileStatus
from app.modules.genealogy import ageorder, engine, geo, lookup, provisional, service
from app.modules.genealogy.provisional import ProvisionalState
from app.modules.genealogy.schemas import (
    EventIn,
    EventOut,
    EventUpdate,
    FamilyOut,
    GraphOut,
    NameIn,
    NameOut,
    NameUpdate,
    PersonCreate,
    PersonOut,
    PersonSummary,
    PersonUpdate,
    PlaceIn,
    PlaceOut,
    PlaceUpdate,
    PrivacyUpdate,
    RelationshipIn,
    RelationshipOut,
    RelationshipPathOut,
    RelationshipUpdate,
    RelativeAgeOrderIn,
    RelativeAgeOrderOut,
    RelativeIn,
    RelativeOut,
)
from app.modules.genealogy.serialize import Serializer, name_out, relationship_out
from app.modules.geo import service as geo_service
from app.modules.geo.schemas import PlaceLgdNote

router = APIRouter(prefix="/trees/{tree_id}", tags=["genealogy"])

LineageQuery = Annotated[
    list[Lineage] | None, Query(description="Restrict to these lineages (biological, legal, ritual, social)")
]


def _person_out(ctx, person_id: uuid.UUID) -> PersonOut:  # type: ignore[no-untyped-def]
    subject = lookup.get_person_subject(ctx, person_id)
    return Serializer(ctx).person_out(subject)


# ------------------------------------------------------------------ people
@router.get("/people", response_model=Page[PersonSummary])
def list_people(
    ctx: TreeCtx,
    q: str | None = Query(default=None, max_length=200),
    status_: ProfileStatus | None = Query(default=None, alias="status"),
    provisional_state: list[ProvisionalState] | None = Query(
        default=None,
        description='Only provisional people in these states: the "To complete" view (ADR-0020 §8). '
        "Visibility rules are unchanged, so it lists only people the caller may see.",
    ),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[PersonSummary]:
    offset = decode_cursor(cursor)
    only: set[uuid.UUID] | None = None
    if provisional_state:
        wanted = {str(s) for s in provisional_state}
        only = {pid for pid, st in provisional.states(ctx).items() if st.value in wanted}
    if q:
        from app.modules.search.service import match_names

        order = [m.person_id for m in match_names(ctx, q)]
        persons = {
            p.id: p
            for p in ctx.db.scalars(
                select(Person).where(
                    Person.tree_id == ctx.tree_id, Person.id.in_(order), Person.deleted_at.is_(None), Person.preferred_display_name != "Erased person"
                )
            )
        }
        if status_:
            persons = {k: v for k, v in persons.items() if v.profile_status == status_}
        if only is not None:
            persons = {k: v for k, v in persons.items() if k in only}
        subjects = load_subjects(ctx, persons.values())
        ranked = [subjects[i] for i in order if i in subjects and can_view_person(ctx, subjects[i])]
        page = ranked[offset : offset + limit]
        more = len(ranked) > offset + limit
    else:
        stmt = select(Person).where(Person.tree_id == ctx.tree_id, Person.deleted_at.is_(None), Person.preferred_display_name != "Erased person")
        if status_:
            stmt = stmt.where(Person.profile_status == status_)
        if only is not None:
            stmt = stmt.where(Person.id.in_(list(only) or [uuid.UUID(int=0)]))
        stmt = stmt.order_by(Person.preferred_display_name, Person.id)
        visible: list = []
        seen_visible, scan, chunk, exhausted = 0, 0, max(limit * 3, 100), False
        # count *visible* rows so hidden people never leak through page sizes or cursors
        while len(visible) < limit + 1 and not exhausted:
            rows = ctx.db.scalars(stmt.offset(scan).limit(chunk)).all()
            scan += len(rows)
            exhausted = len(rows) < chunk
            subjects = load_subjects(ctx, rows)
            for p in rows:
                if can_view_person(ctx, subjects[p.id]):
                    if seen_visible >= offset:
                        visible.append(subjects[p.id])
                    seen_visible += 1
                    if len(visible) >= limit + 1:
                        break
        page = visible[:limit]
        more = len(visible) > limit
    summaries = Serializer(ctx).summaries({s.id: s for s in page})
    return Page(
        items=[summaries[s.id] for s in page], next_cursor=encode_cursor(offset + limit) if more else None
    )


@router.get("/people/deleted", response_model=list[PersonSummary])
def deleted_people(ctx: TreeCtx) -> list[PersonSummary]:
    """Soft-deleted (restorable) people, for tree admins. Merged-away people are listed under merges."""
    from app.authz.permissions import Permission

    ctx.require(Permission.TREE_MANAGE)
    rows = ctx.db.scalars(
        select(Person)
        .where(Person.tree_id == ctx.tree_id, Person.deleted_at.is_not(None), Person.merged_into_id.is_(None))
        .order_by(Person.deleted_at.desc())
    ).all()
    subjects = load_subjects(ctx, rows)
    ser = Serializer(ctx)
    return [ser.summary(subjects[p.id]) for p in rows]


@router.post("/people", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(body: PersonCreate, ctx: TreeCtx) -> PersonOut:
    person = service.create_person(ctx, body)
    return _person_out(ctx, person.id)


@router.get("/people/{person_id}", response_model=PersonOut)
def get_person(person_id: uuid.UUID, ctx: TreeCtx) -> PersonOut:
    return _person_out(ctx, person_id)


@router.patch("/people/{person_id}", response_model=PersonOut)
def update_person(person_id: uuid.UUID, body: PersonUpdate, ctx: TreeCtx) -> PersonOut:
    service.update_person(ctx, person_id, body)
    return _person_out(ctx, person_id)


@router.put("/people/{person_id}/privacy", response_model=PersonOut)
def set_privacy(person_id: uuid.UUID, body: PrivacyUpdate, ctx: TreeCtx) -> PersonOut:
    subject = lookup.get_person_subject(ctx, person_id)
    service.set_privacy(ctx, subject, body)
    return _person_out(ctx, person_id)


@router.delete("/people/{person_id}", response_model=Message)
def delete_person(person_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_person(ctx, person_id)
    return Message(message="Person removed from the tree (restorable by a tree admin)")


class EraseIn(ApiModel):
    reason: str = Field(min_length=3, max_length=500)
    confirm: bool


@router.post("/people/{person_id}/erase", response_model=Message)
def erase_person(person_id: uuid.UUID, body: EraseIn, ctx: TreeCtx) -> Message:
    """Irreversible privacy erasure; the person remains as an anonymous placeholder."""
    if not body.confirm:
        from app.core.errors import Unprocessable

        raise Unprocessable("Set confirm=true to erase this person's data permanently")
    service.erase_person(ctx, person_id, body.reason)
    return Message(message="Personal data erased; an anonymous placeholder keeps the tree structure intact")


@router.post("/people/{person_id}/restore", response_model=PersonOut)
def restore_person(person_id: uuid.UUID, ctx: TreeCtx) -> PersonOut:
    service.restore_person(ctx, person_id)
    return _person_out(ctx, person_id)


# ------------------------------------------------------------------ names
@router.post("/people/{person_id}/names", response_model=NameOut, status_code=status.HTTP_201_CREATED)
def add_name(person_id: uuid.UUID, body: NameIn, ctx: TreeCtx) -> NameOut:
    return name_out(service.add_name(ctx, person_id, body))


@router.patch("/people/{person_id}/names/{name_id}", response_model=NameOut)
def update_name(person_id: uuid.UUID, name_id: uuid.UUID, body: NameUpdate, ctx: TreeCtx) -> NameOut:
    return name_out(service.update_name(ctx, person_id, name_id, body))


@router.delete("/people/{person_id}/names/{name_id}", response_model=Message)
def delete_name(person_id: uuid.UUID, name_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_name(ctx, person_id, name_id)
    return Message(message="Name removed")


# ------------------------------------------------------------------ events
@router.get("/people/{person_id}/events", response_model=list[EventOut])
def person_events(
    person_id: uuid.UUID, ctx: TreeCtx, type: list[EventType] | None = Query(default=None)
) -> list[EventOut]:
    subject = lookup.get_person_subject(ctx, person_id)
    return (
        Serializer(ctx)
        .events_for([subject.id], {subject.id: subject}, set(type) if type else None)
        .get(subject.id, [])
    )


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(body: EventIn, ctx: TreeCtx) -> EventOut:
    e = service.create_event(ctx, body)
    return _event_out(ctx, e.id)


def _event_out(ctx, event_id: uuid.UUID) -> EventOut:  # type: ignore[no-untyped-def]
    e, _principal = service.get_event_checked(ctx, event_id)
    from app.core.errors import NotFound
    from app.models import EventParticipant

    parts = list(
        ctx.db.scalars(
            select(EventParticipant).where(
                EventParticipant.tree_id == ctx.tree_id, EventParticipant.event_id == e.id
            )
        )
    )
    subjects = lookup.visible_subjects(ctx, [p.person_id for p in parts])
    from app.models.enums import CitationTarget
    from app.modules.genealogy.serialize import citation_counts, media_summary

    out = Serializer(ctx).event_out(
        e, parts, subjects, citation_counts(ctx, CitationTarget.EVENT, {e.id}), media_summary(ctx, {e.id})
    )
    if out is None:
        raise NotFound("Event not found")
    return out


@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: uuid.UUID, ctx: TreeCtx) -> EventOut:
    return _event_out(ctx, event_id)


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(event_id: uuid.UUID, body: EventUpdate, ctx: TreeCtx) -> EventOut:
    service.update_event(ctx, event_id, body)
    return _event_out(ctx, event_id)


@router.delete("/events/{event_id}", response_model=Message)
def delete_event(event_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_event(ctx, event_id)
    return Message(message="Event deleted")


# ------------------------------------------------------------------ places
def _place_out(ctx, p: Place) -> PlaceOut:  # type: ignore[no-untyped-def]
    coords = geo.place_coordinates(ctx, p)
    update: dict = {
        "hierarchy": service.place_hierarchy(ctx, p),
        "latitude": coords.latitude if coords else None,
        "longitude": coords.longitude if coords else None,
        "coordinates_coarsened": bool(coords and coords.coarsened),
    }
    note = geo_service.place_notes(ctx.db, [p]).get(p.id)
    if note is not None:
        update["lgd_note"] = PlaceLgdNote.model_validate(note)
    if coords is not None:
        update["location_precision"] = coords.precision
        if coords.coarsened:
            update["geo_note"] = None
    return PlaceOut.model_validate(p).model_copy(update=update)


@router.get("/places", response_model=Page[PlaceOut])
def list_places(
    ctx: TreeCtx,
    q: str | None = Query(default=None, max_length=200),
    geotagged: bool | None = Query(default=None, description="only places with (or without) coordinates"),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[PlaceOut]:
    offset = decode_cursor(cursor)
    stmt = select(Place).where(Place.tree_id == ctx.tree_id)
    if geotagged is not None:
        stmt = stmt.where(Place.latitude.is_not(None) if geotagged else Place.latitude.is_(None))
    if q:
        stmt = stmt.where(Place.search_text.contains(search_key(q)))
    rows = ctx.db.scalars(stmt.order_by(Place.canonical_name).offset(offset).limit(limit + 1)).all()
    return Page(
        items=[_place_out(ctx, p) for p in rows[:limit]],
        next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None,
    )


@router.post("/places", response_model=PlaceOut, status_code=status.HTTP_201_CREATED)
def create_place(body: PlaceIn, ctx: TreeCtx) -> PlaceOut:
    return _place_out(ctx, service.create_place(ctx, body))


@router.get("/places/{place_id}", response_model=PlaceOut)
def get_place(place_id: uuid.UUID, ctx: TreeCtx) -> PlaceOut:
    return _place_out(ctx, lookup.get_place(ctx, place_id))


@router.patch("/places/{place_id}", response_model=PlaceOut)
def update_place(place_id: uuid.UUID, body: PlaceUpdate, ctx: TreeCtx) -> PlaceOut:
    return _place_out(ctx, service.update_place(ctx, place_id, body))


# ------------------------------------------------------------------ relationships
@router.post("/relationships", response_model=RelationshipOut, status_code=status.HTTP_201_CREATED)
def create_relationship(body: RelationshipIn, ctx: TreeCtx) -> RelationshipOut:
    return relationship_out(service.create_relationship(ctx, body))


@router.get("/relationships/{rel_id}", response_model=RelationshipOut)
def get_relationship(rel_id: uuid.UUID, ctx: TreeCtx) -> RelationshipOut:
    rel = lookup.get_relationship(ctx, rel_id)
    lookup.get_person(ctx, rel.person_a_id)
    lookup.get_person(ctx, rel.person_b_id)
    return relationship_out(rel)


@router.patch("/relationships/{rel_id}", response_model=RelationshipOut)
def update_relationship(rel_id: uuid.UUID, body: RelationshipUpdate, ctx: TreeCtx) -> RelationshipOut:
    return relationship_out(service.update_relationship(ctx, rel_id, body))


@router.delete("/relationships/{rel_id}", response_model=Message)
def delete_relationship(rel_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_relationship(ctx, rel_id)
    return Message(message="Relationship removed")


@router.post("/people/{person_id}/relatives", response_model=RelativeOut, status_code=status.HTTP_201_CREATED)
def add_relative(person_id: uuid.UUID, body: RelativeIn, ctx: TreeCtx) -> RelativeOut:
    other, rels = service.add_relative(ctx, person_id, body)
    subject = lookup.get_person_subject(ctx, other.id)
    summary = Serializer(ctx).summaries({subject.id: subject})[subject.id]
    return RelativeOut(person=summary, relationships=[relationship_out(r) for r in rels])


@router.get("/people/{person_id}/family", response_model=FamilyOut)
def get_family(person_id: uuid.UUID, ctx: TreeCtx, lineage: LineageQuery = None) -> FamilyOut:
    return engine.family(ctx, person_id, set(lineage) if lineage else None)


@router.get("/people/{person_id}/ancestors", response_model=GraphOut)
def ancestors(
    person_id: uuid.UUID,
    ctx: TreeCtx,
    depth: int = Query(default=4, ge=1, le=25),
    lineage: LineageQuery = None,
) -> GraphOut:
    return engine.graph(ctx, person_id, "ancestors", depth, set(lineage) if lineage else None)


@router.get("/people/{person_id}/descendants", response_model=GraphOut)
def descendants(
    person_id: uuid.UUID,
    ctx: TreeCtx,
    depth: int = Query(default=4, ge=1, le=25),
    lineage: LineageQuery = None,
) -> GraphOut:
    return engine.graph(ctx, person_id, "descendants", depth, set(lineage) if lineage else None)


@router.get("/people/{person_id}/connected", response_model=GraphOut)
def connected(
    person_id: uuid.UUID,
    ctx: TreeCtx,
    depth: int = Query(default=25, ge=1, le=25),
) -> GraphOut:
    """Complete reachable family component within the documented safety budgets."""
    return engine.connected_graph(ctx, person_id, max_depth=depth)


@router.post(
    "/relative-age-orders",
    response_model=RelativeAgeOrderOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": RelativeAgeOrderOut, "description": "Already recorded"}},
)
def record_relative_age(body: RelativeAgeOrderIn, ctx: TreeCtx) -> RelativeAgeOrderOut | JSONResponse:
    """Family-confirmed "older / younger than" between two siblings (ADR-0020 §5). It takes
    precedence over birth dates when kinship terms depend on age (Tau vs Chacha)."""
    row, created = ageorder.record_for_siblings(ctx, body.person_id, body.relative_to_id, body.order)
    out = RelativeAgeOrderOut(
        id=row.id, elder_person_id=row.elder_person_id, younger_person_id=row.younger_person_id
    )
    if created:
        return out
    return JSONResponse(out.model_dump(mode="json"), status_code=status.HTTP_200_OK)


@router.delete("/relative-age-orders/{record_id}", response_model=Message)
def delete_relative_age(record_id: uuid.UUID, ctx: TreeCtx) -> Message:
    """Remove a recorded age order (to correct a mistake)."""
    ageorder.delete(ctx, record_id)
    return Message(message="Age order removed")


@router.get("/relationship-path", response_model=RelationshipPathOut)
def relationship_path(
    ctx: TreeCtx,
    from_id: uuid.UUID = Query(alias="from"),
    to_id: uuid.UUID = Query(alias="to"),
    lineage: LineageQuery = None,
    lang: str | None = Query(
        default=None, pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$", description="the reader's UI language"
    ),
) -> RelationshipPathOut:
    from app.modules.kinship.service import deciding_age, terms_for

    out = engine.relationship_path(ctx, from_id, to_id, set(lineage) if lineage else None)
    if out.found:
        out = out.model_copy(
            update={
                "terms": terms_for(ctx, from_id, out.chain, out.age_orders, lang),
                "age_decision": deciding_age(out.chain, out.age_orders),
            }
        )
    return out
