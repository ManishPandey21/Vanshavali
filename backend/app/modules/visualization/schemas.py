"""Compact, purpose-built payloads for charts (ADR-0017). Never full PersonOut objects."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field, field_validator

from app.api.schemas import ApiModel
from app.models.enums import ChartType, LocationPrecision, ProfileStatus, SexAtBirth


class GeoPoint(ApiModel):
    latitude: float
    longitude: float
    precision: LocationPrecision
    coarsened: bool = False


class PlaceRef(ApiModel):
    id: uuid.UUID | None = None
    name: str
    district: str | None = None
    state: str | None = None
    country: str | None = None
    geo: GeoPoint | None = None


class Completeness(ApiModel):
    score: float  # 0..1 over the checks below
    missing: list[str] = []  # birth_date, birth_place, death_date, parents, sources


class VizPerson(ApiModel):
    id: uuid.UUID
    display_name: str
    sex: SexAtBirth | None = None
    profile_status: ProfileStatus
    is_protected: bool = False
    birth_year: int | None = None
    death_year: int | None = None
    birth_display: str | None = None
    death_display: str | None = None
    birth_place: PlaceRef | None = None
    village: str | None = None  # preferred ancestral-village assertion, when visible
    branch_ids: list[uuid.UUID] = []
    event_count: int = 0
    completeness: Completeness | None = None


class AncestryNode(ApiModel):
    slot: int  # Ahnentafel number: root 1, father 2n, mother 2n+1
    generation: int  # 0 = root
    side: str  # self | paternal | maternal
    hidden: bool = False  # a person exists but is hidden from you
    person: VizPerson | None = None


class AncestryOut(ApiModel):
    root_id: uuid.UUID
    generations: int
    nodes: list[AncestryNode]
    missing_slots: list[int] = []  # research gaps: parents not recorded (inside the depth)
    summary: str = ""


class GraphNodeOut(ApiModel):
    id: str  # person id, or "hidden-N" for a placeholder
    hidden: bool = False
    person: VizPerson | None = None
    household_ids: list[uuid.UUID] = []
    distance: int = 0
    expandable: bool = False  # has relatives not included yet


class GraphEdgeOut(ApiModel):
    source: str
    target: str
    kind: str  # parent | union | sibling
    type: str


class NeighbourhoodOut(ApiModel):
    root_id: uuid.UUID
    radius: int
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
    truncated: bool = False


class LifespanEvent(ApiModel):
    event_id: uuid.UUID
    year: int
    label: str
    category: str | None = None


class LifespanRow(ApiModel):
    person: VizPerson
    generation: int | None = None
    start_year: int
    end_year: int | None  # None = living (or end unknown): drawn to today
    end_known: bool = True
    approximate: bool = False
    events: list[LifespanEvent] = []


class HistoricalPeriod(ApiModel):
    label: str
    start_year: int
    end_year: int


class LifespansOut(ApiModel):
    rows: list[LifespanRow]
    periods: list[HistoricalPeriod]
    min_year: int | None = None
    max_year: int | None = None
    truncated: bool = False
    without_dates: int = 0  # visible people left out because no birth year is known
    summary: str = ""


class StoryPhoto(ApiModel):
    media_id: uuid.UUID
    document_id: uuid.UUID
    caption: str | None = None
    is_cover: bool = False
    has_thumbnail: bool = False


class StoryEvent(ApiModel):
    id: uuid.UUID
    type: str
    category: str | None = None
    title: str | None = None
    label: str
    date: dict[str, Any] | None = None
    date_display: str | None = None
    year: int | None = None
    sort_key: str
    place: PlaceRef | None = None
    description: str | None = None
    significance: str
    relatives: list[dict[str, str]] = []
    photos: list[StoryPhoto] = []
    redacted_fields: list[str] = []


class StoryOut(ApiModel):
    person: VizPerson
    events: list[StoryEvent]
    summary: str = ""


class MapPoint(ApiModel):
    id: str
    kind: str  # event | place | heritage | property
    label: str
    geo: GeoPoint
    place_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    person_ids: list[uuid.UUID] = []
    year: int | None = None
    category: str | None = None


class MapPath(ApiModel):
    event_id: uuid.UUID
    person_id: uuid.UUID | None = None
    label: str
    year: int | None = None
    origin: GeoPoint
    origin_label: str
    destination: GeoPoint
    destination_label: str


class MapOut(ApiModel):
    points: list[MapPoint]
    paths: list[MapPath]
    not_geotagged: int = 0  # visible items with a place but no coordinates
    truncated: bool = False


# ---------- presets
_MAX_SETTINGS_BYTES = 8000


class PresetIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    chart_type: ChartType
    settings: dict[str, Any] = {}
    shared: bool = False

    @field_validator("settings")
    @classmethod
    def _small(cls, v: dict[str, Any]) -> dict[str, Any]:
        import json

        if len(json.dumps(v)) > _MAX_SETTINGS_BYTES:
            raise ValueError("chart settings are limited to 8 KB")
        return v


class PresetUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    settings: dict[str, Any] | None = None
    shared: bool | None = None

    @field_validator("settings")
    @classmethod
    def _small(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return v if v is None else PresetIn._small(v)  # type: ignore[call-arg]


class PresetOut(ApiModel):
    id: uuid.UUID
    name: str
    chart_type: ChartType
    settings: dict[str, Any]
    shared: bool
    mine: bool = True
    created_at: dt.datetime
    updated_at: dt.datetime
