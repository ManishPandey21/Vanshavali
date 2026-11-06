from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.api.schemas import ApiModel
from app.models.enums import GeoLevel, GeoSnapshotStatus, GeoSource


class GeoSnapshotInfo(ApiModel):
    """Shown with every answer: where the data comes from and how to attribute it (ADR-0019 §2)."""

    source: GeoSource
    label: str
    licence: str
    attribution: str


class GeoRef(ApiModel):
    level: GeoLevel
    code: str
    name_en: str
    name_local: str | None = None


class GeoUnitOut(ApiModel):
    level: GeoLevel
    code: str
    name_en: str
    name_local: str | None = None
    local_script: str | None = None
    local_term: str | None = None
    category: str | None = None
    alt_names: list[str] = []
    former_names: list[str] = []
    # current: in the active snapshot and valid; historical: in it with a past valid_to;
    # retired: only in an older snapshot
    status: Literal["current", "historical", "retired"] = "current"
    valid_to: dt.date | None = None
    successor_codes: list[str] = []
    # ancestors, from the state down (the country is left out)
    path: list[GeoRef] = []


class GeoUnitPage(ApiModel):
    items: list[GeoUnitOut]
    next_cursor: str | None = None
    snapshot: GeoSnapshotInfo | None = None


class GeoOfficeOut(ApiModel):
    office_name: str
    office_type: str | None = None
    delivery: bool | None = None
    district_name: str | None = None
    state_name: str | None = None
    units: list[GeoUnitOut] = []


class GeoPinOut(ApiModel):
    pin: str
    offices: list[GeoOfficeOut]
    snapshot: GeoSnapshotInfo | None = None


# ---------------------------------------------------------------- admin
class GeoSnapshotOut(ApiModel):
    id: uuid.UUID
    source: GeoSource
    label: str
    status: GeoSnapshotStatus
    source_url: str | None
    downloaded_on: dt.date | None
    licence: str
    attribution: str
    files: list[dict[str, Any]]
    report: dict[str, Any]
    staged_by: str | None
    approved_by_name: str | None = None
    approved_at: dt.datetime | None
    activated_by_name: str | None = None
    activated_at: dt.datetime | None
    created_at: dt.datetime
    approved_by_me: bool = False


class GeoDecisionIn(ApiModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=2000)
