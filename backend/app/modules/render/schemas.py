from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.models.enums import ChartType, Lineage, RenderArtifactKind, RenderOutput, RenderStatus

ColorBy = Literal["birthplace", "village", "branch", "side", "completeness", "living"]


class RenderSettings(ApiModel):
    """What to render. Only ids and display options: the data itself is read as you, at request time."""

    root_person_id: uuid.UUID | None = None  # fan, pedigree, family tree, lifespan (optional), event timeline
    generations: int = Field(default=4, ge=1, le=8)
    direction: Literal["ancestors", "descendants"] = "descendants"  # family tree
    color_by: ColorBy = "side"
    lineage: list[Lineage] | None = None
    branch_id: uuid.UUID | None = None  # lifespan
    theme: Literal["heritage", "dusk", "minimal"] = "heritage"
    title: str | None = Field(default=None, max_length=120)
    subtitle: str | None = Field(default=None, max_length=200)
    include_photos: bool = True  # event timeline


class RenderJobIn(ApiModel):
    chart_type: ChartType
    output: RenderOutput = RenderOutput.POSTER
    settings: RenderSettings = RenderSettings()


class RenderArtifactOut(ApiModel):
    id: uuid.UUID
    kind: RenderArtifactKind
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_s: float | None


class RenderJobOut(ApiModel):
    id: uuid.UUID
    chart_type: ChartType
    output: RenderOutput
    status: RenderStatus
    progress: int
    settings: dict
    renderer: str | None
    error_code: str | None
    error_message: str | None
    created_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    artifacts: list[RenderArtifactOut] = []
    mine: bool = True


class RenderDownloadOut(ApiModel):
    url: str
    expires_at: dt.datetime
