"""``/geo``: Indian geography reference data for place cascades (ADR-0019 §6).

Signed-in users only, rate-limited per user, no tree data. Responses carry the active snapshot and
an ``ETag`` derived from it and the request, so clients revalidate cheaply. With
``VSH_GEO_ENABLED=false`` every route answers 404 and the UI keeps the free-text place fields.
Queries travel in the query string; only request paths are logged.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Path, Query, Request, Response

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import decode_cursor, encode_cursor
from app.core.errors import Unprocessable
from app.core.ratelimit import enforce
from app.models.enums import GeoLevel
from app.modules.geo import service
from app.modules.geo.schemas import GeoSnapshotInfo, GeoUnitResponse, GeoUnitsPage, PincodeOut

router = APIRouter(prefix="/geo", tags=["geography"])

# a cascade fires a request per level and per typing pause
RATE_LIMIT_PER_MINUTE = 240
Db = DbDep


def _snapshot(a: service.Active) -> GeoSnapshotInfo:
    return GeoSnapshotInfo(id=a.id, activated_at=a.activated_at, attribution=service.ATTRIBUTION)


def _etag(request: Request, response: Response, a: service.Active) -> Response | None:
    tag = (
        '"' + hashlib.sha256(f"{a.id}|{request.url.path}|{request.url.query}".encode()).hexdigest()[:32] + '"'
    )
    response.headers["ETag"] = tag
    response.headers["Cache-Control"] = "private, no-cache"
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers={"ETag": tag, "Cache-Control": "private, no-cache"})
    return None


@router.get("/units", response_model=GeoUnitsPage, responses={304: {"description": "Not modified"}})
def list_units(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: Db,
    level: GeoLevel | None = None,
    parent: str | None = Query(default=None, pattern=r"^\d{1,20}$"),
    parent_level: GeoLevel | None = None,
    q: str | None = Query(default=None, max_length=100),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> Any:
    enforce(f"geo:{user.id}", RATE_LIMIT_PER_MINUTE)
    a = service.active(db)
    if (cached := _etag(request, response, a)) is not None:
        return cached
    offset = decode_cursor(cursor)
    if q is not None and q.strip():
        levels = [level] if level else [GeoLevel.VILLAGE, GeoLevel.URBAN_BODY]
        items, more = service.search(db, a, q, levels, parent, parent_level, offset, min(limit, 50))
        limit = min(limit, 50)
    else:
        if level is None:
            raise Unprocessable("give level (to list) or q (to search)")
        items, more = service.children(db, a, level, parent, parent_level, offset, limit)
    return GeoUnitsPage(
        items=items,  # type: ignore[arg-type]
        next_cursor=encode_cursor(offset + limit) if more else None,
        snapshot=_snapshot(a),
    )


@router.get(
    "/units/{lgd_code}", response_model=GeoUnitResponse, responses={304: {"description": "Not modified"}}
)
def get_unit(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: Db,
    lgd_code: str = Path(pattern=r"^\d{1,20}$"),
    level: GeoLevel = Query(description="LGD codes are unique per level only"),
) -> Any:
    enforce(f"geo:{user.id}", RATE_LIMIT_PER_MINUTE)
    a = service.active(db)
    if (cached := _etag(request, response, a)) is not None:
        return cached
    return GeoUnitResponse(
        unit=service.unit_detail(db, a, level, lgd_code.lstrip("0") or "0"), snapshot=_snapshot(a)
    )  # type: ignore[arg-type]


@router.get("/pincodes/{pin}", response_model=PincodeOut, responses={304: {"description": "Not modified"}})
def get_pincode(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: Db,
    pin: str = Path(pattern=r"^[1-9]\d{5}$"),
) -> Any:
    enforce(f"geo:{user.id}", RATE_LIMIT_PER_MINUTE)
    a = service.active(db)
    if (cached := _etag(request, response, a)) is not None:
        return cached
    return PincodeOut(**service.pincode(db, a, pin), snapshot=_snapshot(a))
