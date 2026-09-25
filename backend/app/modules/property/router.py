"""Ancestral property API (PRS §17, §37; ADR-0010). Genealogical/documentary records only."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.models import LandParcel, Property, PropertyInterest
from app.models.enums import PropertyClassification, PropertyType
from app.modules.genealogy import lookup
from app.modules.property import service
from app.modules.property.schemas import (
    InterestEndIn,
    InterestIn,
    InterestOut,
    InterestUpdate,
    LineageOut,
    ParcelIn,
    ParcelLineageOut,
    ParcelNode,
    ParcelOut,
    ParcelUpdate,
    PartitionIn,
    PersonPropertyInterestOut,
    PersonPropertyInterestsOut,
    PropertyDetailOut,
    PropertyEventIn,
    PropertyEventOut,
    PropertyEventUpdate,
    PropertyIn,
    PropertyOut,
    PropertyUpdate,
    SubdivideIn,
    SubdivideOut,
    TimelineOut,
)
from app.modules.property.search import register as _register_search
from app.modules.property.serialize import PropertySerializer, parcel_ref, parcel_sort_key

router = APIRouter(prefix="/trees/{tree_id}", tags=["property"])

_register_search()


# ------------------------------------------------------------------ properties
@router.get("/properties", response_model=list[PropertyOut])
def list_properties(
    ctx: TreeCtx,
    property_type: PropertyType | None = Query(default=None, alias="type"),
    classification: PropertyClassification | None = None,
    q: str | None = Query(default=None, max_length=200),
) -> list[PropertyOut]:
    props = service.list_properties(ctx, property_type, classification, q)
    return PropertySerializer(ctx).properties_out(props)


@router.post("/properties", response_model=PropertyDetailOut, status_code=status.HTTP_201_CREATED)
def create_property(body: PropertyIn, ctx: TreeCtx) -> PropertyDetailOut:
    p = service.create_property(ctx, body)
    return PropertySerializer(ctx).detail(p)


@router.get("/properties/{property_id}", response_model=PropertyDetailOut)
def get_property(property_id: uuid.UUID, ctx: TreeCtx) -> PropertyDetailOut:
    return PropertySerializer(ctx).detail(service.get_property(ctx, property_id))


@router.patch("/properties/{property_id}", response_model=PropertyDetailOut)
def update_property(property_id: uuid.UUID, body: PropertyUpdate, ctx: TreeCtx) -> PropertyDetailOut:
    p = service.update_property(ctx, property_id, body)
    return PropertySerializer(ctx).detail(p)


@router.delete("/properties/{property_id}", response_model=Message)
def delete_property(property_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_property(ctx, property_id)
    return Message(message="Property deleted")


# ------------------------------------------------------------------ parcels
@router.get("/properties/{property_id}/parcels", response_model=list[ParcelOut])
def list_parcels(property_id: uuid.UUID, ctx: TreeCtx) -> list[ParcelOut]:
    prop = service.get_property(ctx, property_id)
    ser = PropertySerializer(ctx)
    return ser.parcels_out(ser.parcels_of(prop))


@router.post(
    "/properties/{property_id}/parcels", response_model=ParcelOut, status_code=status.HTTP_201_CREATED
)
def create_parcel(property_id: uuid.UUID, body: ParcelIn, ctx: TreeCtx) -> ParcelOut:
    return PropertySerializer(ctx).parcel_out(service.create_parcel(ctx, property_id, body))


@router.patch("/properties/{property_id}/parcels/{parcel_id}", response_model=ParcelOut)
def update_parcel(
    property_id: uuid.UUID, parcel_id: uuid.UUID, body: ParcelUpdate, ctx: TreeCtx
) -> ParcelOut:
    return PropertySerializer(ctx).parcel_out(service.update_parcel(ctx, property_id, parcel_id, body))


@router.delete("/properties/{property_id}/parcels/{parcel_id}", response_model=Message)
def delete_parcel(property_id: uuid.UUID, parcel_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_parcel(ctx, property_id, parcel_id)
    return Message(message="Parcel deleted")


@router.post(
    "/properties/{property_id}/parcels/{parcel_id}/subdivide",
    response_model=SubdivideOut,
    status_code=status.HTTP_201_CREATED,
)
def subdivide_parcel(
    property_id: uuid.UUID, parcel_id: uuid.UUID, body: SubdivideIn, ctx: TreeCtx
) -> SubdivideOut:
    parent, children, event, warnings = service.subdivide_parcel(ctx, property_id, parcel_id, body)
    ser = PropertySerializer(ctx)
    prop = service.get_property(ctx, property_id)
    return SubdivideOut(
        parent=ser.parcel_out(parent),
        children=[ser.parcel_out(c, 0) for c in children],
        event=ser.event_out(prop, event) if event else None,
        warnings=warnings,
    )


@router.get("/properties/{property_id}/parcels/{parcel_id}/lineage", response_model=ParcelLineageOut)
def parcel_lineage(property_id: uuid.UUID, parcel_id: uuid.UUID, ctx: TreeCtx) -> ParcelLineageOut:
    """Subdivision lineage: ancestors (nearest first), siblings sharing the parent, descendants."""
    prop = service.get_property(ctx, property_id)
    parcel = service.get_parcel(ctx, prop, parcel_id)
    ser = PropertySerializer(ctx)
    all_parcels = {
        p.id: p
        for p in ctx.db.scalars(
            select(LandParcel).where(LandParcel.tree_id == ctx.tree_id, LandParcel.property_id == prop.id)
        )
    }
    children: dict[uuid.UUID, list[LandParcel]] = {}
    for p in sorted(all_parcels.values(), key=parcel_sort_key):
        if p.parent_parcel_id:
            children.setdefault(p.parent_parcel_id, []).append(p)
    ancestors = []
    seen = {parcel.id}
    cur = parcel.parent_parcel_id
    while cur is not None and cur in all_parcels and cur not in seen:
        seen.add(cur)
        ancestors.append(parcel_ref(all_parcels[cur]))
        cur = all_parcels[cur].parent_parcel_id
    siblings = (
        [parcel_ref(p) for p in children.get(parcel.parent_parcel_id, []) if p.id != parcel.id]
        if parcel.parent_parcel_id
        else []
    )
    descendants: list[ParcelNode] = []
    stack = [(c, 1) for c in reversed(children.get(parcel.id, []))]
    visited = {parcel.id}
    while stack:
        node, depth = stack.pop()
        if node.id in visited:
            continue
        visited.add(node.id)
        descendants.append(ParcelNode(parcel=parcel_ref(node), depth=depth))
        stack.extend((c, depth + 1) for c in reversed(children.get(node.id, [])))
    return ParcelLineageOut(
        parcel=ser.parcel_out(parcel, len(children.get(parcel.id, []))),
        ancestors=ancestors,
        siblings=siblings,
        descendants=descendants,
    )


# ------------------------------------------------------------------ interests
@router.get("/properties/{property_id}/interests", response_model=list[InterestOut])
def list_interests(property_id: uuid.UUID, ctx: TreeCtx, current_only: bool = False) -> list[InterestOut]:
    prop = service.get_property(ctx, property_id)
    interests = service.property_interests(ctx, prop.id)
    if current_only:
        interests = [i for i in interests if service.is_current(i)]
    return PropertySerializer(ctx).interests_out(interests)


@router.post(
    "/properties/{property_id}/interests", response_model=InterestOut, status_code=status.HTTP_201_CREATED
)
def create_interest(property_id: uuid.UUID, body: InterestIn, ctx: TreeCtx) -> InterestOut:
    i = service.create_interest(ctx, property_id, body)
    return PropertySerializer(ctx).interests_out([i])[0]


@router.patch("/properties/{property_id}/interests/{interest_id}", response_model=InterestOut)
def update_interest(
    property_id: uuid.UUID, interest_id: uuid.UUID, body: InterestUpdate, ctx: TreeCtx
) -> InterestOut:
    i = service.update_interest(ctx, property_id, interest_id, body)
    return PropertySerializer(ctx).interests_out([i])[0]


@router.post("/properties/{property_id}/interests/{interest_id}/end", response_model=InterestOut)
def end_interest(
    property_id: uuid.UUID, interest_id: uuid.UUID, body: InterestEndIn, ctx: TreeCtx
) -> InterestOut:
    i = service.end_interest(ctx, property_id, interest_id, body)
    return PropertySerializer(ctx).interests_out([i])[0]


@router.delete("/properties/{property_id}/interests/{interest_id}", response_model=Message)
def delete_interest(property_id: uuid.UUID, interest_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_interest(ctx, property_id, interest_id)
    return Message(message="Interest deleted")


# ------------------------------------------------------------------ events
@router.post(
    "/properties/{property_id}/events", response_model=PropertyEventOut, status_code=status.HTTP_201_CREATED
)
def record_event(property_id: uuid.UUID, body: PropertyEventIn, ctx: TreeCtx) -> PropertyEventOut:
    ev = service.record_event(ctx, property_id, body)
    prop = service.get_property(ctx, property_id)
    return PropertySerializer(ctx).event_out(prop, ev)


@router.get("/properties/{property_id}/events/{event_id}", response_model=PropertyEventOut)
def get_event(property_id: uuid.UUID, event_id: uuid.UUID, ctx: TreeCtx) -> PropertyEventOut:
    prop = service.get_property(ctx, property_id)
    return PropertySerializer(ctx).event_out(prop, service.get_event(ctx, prop, event_id))


@router.patch("/properties/{property_id}/events/{event_id}", response_model=PropertyEventOut)
def update_event(
    property_id: uuid.UUID, event_id: uuid.UUID, body: PropertyEventUpdate, ctx: TreeCtx
) -> PropertyEventOut:
    ev = service.update_event(ctx, property_id, event_id, body)
    prop = service.get_property(ctx, property_id)
    return PropertySerializer(ctx).event_out(prop, ev)


@router.post(
    "/properties/{property_id}/partition",
    response_model=PropertyEventOut,
    status_code=status.HTTP_201_CREATED,
)
def record_partition(property_id: uuid.UUID, body: PartitionIn, ctx: TreeCtx) -> PropertyEventOut:
    ev = service.record_partition(ctx, property_id, body)
    prop = service.get_property(ctx, property_id)
    return PropertySerializer(ctx).event_out(prop, ev)


# ------------------------------------------------------------------ views
@router.get("/properties/{property_id}/timeline", response_model=TimelineOut)
def timeline(
    property_id: uuid.UUID,
    ctx: TreeCtx,
    holders_at: dt.date | None = Query(default=None, alias="at", description="YYYY-MM-DD"),
) -> TimelineOut:
    prop = service.get_property(ctx, property_id)
    return PropertySerializer(ctx).timeline(prop, holders_at)


@router.get("/properties/{property_id}/lineage", response_model=LineageOut)
def lineage(property_id: uuid.UUID, ctx: TreeCtx) -> LineageOut:
    prop = service.get_property(ctx, property_id)
    return PropertySerializer(ctx).lineage(prop)


@router.get("/people/{person_id}/property-interests", response_model=PersonPropertyInterestsOut)
def person_property_interests(person_id: uuid.UUID, ctx: TreeCtx) -> PersonPropertyInterestsOut:
    lookup.get_person(ctx, person_id)
    rows = ctx.db.execute(
        select(PropertyInterest, Property)
        .join(
            Property,
            (Property.id == PropertyInterest.property_id) & (Property.tree_id == PropertyInterest.tree_id),
        )
        .where(PropertyInterest.tree_id == ctx.tree_id, PropertyInterest.holder_person_id == person_id)
        .order_by(Property.display_name, PropertyInterest.valid_from_sort.asc().nulls_first())
    ).all()
    visible = [(i, p) for i, p in rows if service.can_view_property(ctx, p)]
    ser = PropertySerializer(ctx)
    props = {
        p.id: o
        for p, o in zip([p for _, p in visible], ser.properties_out([p for _, p in visible]), strict=True)
    }
    interests = ser.interests_out([i for i, _ in visible])
    return PersonPropertyInterestsOut(
        person_id=person_id,
        items=[
            PersonPropertyInterestOut(property=props[p.id], interest=io)
            for (_, p), io in zip(visible, interests, strict=True)
        ],
    )
