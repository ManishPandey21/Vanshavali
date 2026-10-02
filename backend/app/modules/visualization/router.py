from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import TreeCtx
from app.api.schemas import Message
from app.models.enums import ChartType, Lineage
from app.modules.visualization import service
from app.modules.visualization.schemas import (
    AncestryOut,
    LifespansOut,
    MapOut,
    NeighbourhoodOut,
    PresetIn,
    PresetOut,
    PresetUpdate,
    StoryOut,
)

router = APIRouter(prefix="/trees/{tree_id}", tags=["visualization"])

LineageQuery = Annotated[list[Lineage] | None, Query(description="Restrict parent links to these lineages")]
MAP_LAYERS = {"events", "migrations", "heritage", "properties", "places"}


@router.get("/viz/ancestry", response_model=AncestryOut)
def ancestry(
    ctx: TreeCtx,
    root: uuid.UUID,
    generations: int = Query(default=5, ge=1, le=service.MAX_ANCESTRY_GENERATIONS),
    lineage: LineageQuery = None,
) -> AncestryOut:
    """Ahnentafel-numbered ancestors for fan and pedigree charts, with birthplace, village, branch,
    completeness and living/deceased attributes for colouring, and research gaps."""
    return service.ancestry(ctx, root, generations, set(lineage) if lineage else None)


@router.get("/viz/neighbourhood", response_model=NeighbourhoodOut)
def neighbourhood(
    ctx: TreeCtx,
    root: uuid.UUID,
    radius: int = Query(default=1, ge=1, le=3),
    max_nodes: int = Query(default=120, ge=10, le=service.MAX_GRAPH_NODES),
    lineage: LineageQuery = None,
) -> NeighbourhoodOut:
    """Relatives within ``radius`` steps for the dynamic graph; expand nodes by calling again with
    ``root`` set to an ``expandable`` node (progressive loading)."""
    return service.neighbourhood(ctx, root, radius, set(lineage) if lineage else None, max_nodes)


@router.get("/viz/lifespans", response_model=LifespansOut)
def lifespans(
    ctx: TreeCtx,
    root: uuid.UUID | None = None,
    generations: int = Query(default=4, ge=1, le=25),
    branch_id: uuid.UUID | None = None,
    include_events: bool = False,
    limit: int = Query(default=200, ge=1, le=service.MAX_LIFESPANS),
) -> LifespansOut:
    return service.lifespans(ctx, root, generations, branch_id, include_events, limit)


@router.get("/viz/people/{person_id}/story", response_model=StoryOut)
def story(person_id: uuid.UUID, ctx: TreeCtx) -> StoryOut:
    """A person's life events in order, with places, relatives and album photos (event timeline)."""
    return service.story(ctx, person_id)


@router.get("/viz/map", response_model=MapOut)
def geo_map(
    ctx: TreeCtx,
    person_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    layer: Annotated[
        list[str] | None, Query(description="events, migrations, heritage, properties, places")
    ] = None,
) -> MapOut:
    include = set(layer or MAP_LAYERS) & MAP_LAYERS
    return service.geo_map(ctx, person_id, branch_id, include)


@router.get("/chart-presets", response_model=list[PresetOut])
def list_presets(ctx: TreeCtx, chart_type: ChartType | None = None) -> list[PresetOut]:
    """Your presets plus presets other members shared with the tree."""
    return service.list_presets(ctx, chart_type)


@router.post("/chart-presets", response_model=PresetOut, status_code=status.HTTP_201_CREATED)
def create_preset(body: PresetIn, ctx: TreeCtx) -> PresetOut:
    return service.create_preset(ctx, body)


@router.patch("/chart-presets/{preset_id}", response_model=PresetOut)
def update_preset(preset_id: uuid.UUID, body: PresetUpdate, ctx: TreeCtx) -> PresetOut:
    return service.update_preset(ctx, preset_id, body)


@router.delete("/chart-presets/{preset_id}", response_model=Message)
def delete_preset(preset_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_preset(ctx, preset_id)
    return Message(message="Preset deleted")
