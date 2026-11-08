"""Geography reference API schemas (ADR-0019 §6). No tree data appears in any of these."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from app.api.schemas import ApiModel
from app.models.enums import GeoAliasKind, GeoLevel

SubDistrictLabel = Literal["sub_district", "tehsil", "taluka", "mandal", "block", "circle", "subdivision"]


class GeoUnitBrief(ApiModel):
    level: GeoLevel
    lgd_code: str
    name_en: str
    name_local: str | None = None
    local_script: str | None = None


class GeoMatch(ApiModel):
    # why a search result matched: its English name, its local-script name, or an alias
    reason: Literal["name", "local_name", "alias"]
    text: str


class GeoUnitOut(GeoUnitBrief):
    category: str | None = None
    parent_level: GeoLevel | None = None
    parent_lgd_code: str | None = None
    state_code: str | None = None
    district_code: str | None = None
    sub_district_code: str | None = None
    # what this unit's state calls a sub-district (Tehsil, Taluka, Mandal…), an i18n key
    sub_district_label: SubDistrictLabel = "sub_district"
    ancestors: list[GeoUnitBrief] = []
    match: GeoMatch | None = None


class GeoAlias(ApiModel):
    name: str
    kind: GeoAliasKind
    script: str | None = None


class GeoUnitDetail(GeoUnitOut):
    status: Literal["current", "retired"]
    successors: list[GeoUnitOut] = []
    aliases: list[GeoAlias] = []


class GeoSnapshotInfo(ApiModel):
    id: str
    activated_at: dt.datetime | None = None
    attribution: str


class GeoUnitsPage(ApiModel):
    items: list[GeoUnitOut]
    next_cursor: str | None = None
    snapshot: GeoSnapshotInfo


class GeoUnitResponse(ApiModel):
    unit: GeoUnitDetail
    snapshot: GeoSnapshotInfo


class PostOffice(ApiModel):
    office_name: str
    office_type: str | None = None
    delivery: bool | None = None
    district_name: str | None = None
    state_name: str | None = None
    district_lgd_code: str | None = None


class PincodeOut(ApiModel):
    """Post offices for a PIN and the LGD units they suggest. Never a village (§6)."""

    pincode: str
    offices: list[PostOffice]
    states: list[GeoUnitOut]
    districts: list[GeoUnitOut]
    sub_districts: list[GeoUnitOut]
    snapshot: GeoSnapshotInfo


class PlaceLgdNote(ApiModel):
    """The linked unit changed in LGD since it was picked. Informational: the place is unchanged."""

    kind: str  # "renamed", "moved", "ancestor_renamed" (joined by "+"), or "retired"
    since: str | None = None
    unit: GeoUnitOut | GeoUnitBrief
    previous_name: str | None = None
    successors: list[GeoUnitBrief] = []
