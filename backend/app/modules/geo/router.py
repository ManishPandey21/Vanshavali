"""Geography reference API (ADR-0019 §4): signed-in users, rate-limited, no tree data."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbDep
from app.core.config import get_settings
from app.core.ratelimit import enforce
from app.models import User
from app.models.enums import GeoLevel
from app.modules.geo import service
from app.modules.geo.schemas import GeoPinOut, GeoUnitOut, GeoUnitPage

router = APIRouter(prefix="/geo", tags=["geography"])

Code = Annotated[str, Path(pattern=r"^[A-Za-z0-9]{1,40}$")]


def _limited(user: CurrentUser) -> User:
    enforce(f"geo:{user.id}", get_settings().geo_rate_limit_per_minute)
    return user


GeoUser = Annotated[User, Depends(_limited)]


@router.get("/units", response_model=GeoUnitPage)
def list_units(
    user: GeoUser,
    db: DbDep,
    level: GeoLevel | None = None,
    parent_level: GeoLevel | None = None,
    parent_code: str | None = Query(default=None, pattern=r"^[A-Za-z0-9]{1,40}$"),
    q: str = Query(default="", max_length=100),
    include_historical: bool = False,
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
) -> GeoUnitPage:
    """Children of a unit (``parent_level`` + ``parent_code``), or units of a level; ``q`` searches
    English, local-script, alternate and former names. Without arguments: the states and UTs."""
    return service.units(
        db,
        level=level,
        parent_level=parent_level,
        parent_code=parent_code,
        q=q,
        include_historical=include_historical,
        cursor=cursor,
        limit=limit,
    )


@router.get("/units/{level}/{code}", response_model=GeoUnitOut)
def get_unit(level: GeoLevel, code: Code, user: GeoUser, db: DbDep) -> GeoUnitOut:
    """One unit with its ancestors; a retired code still resolves (status ``retired``)."""
    return service.unit(db, level, code)


@router.get("/pincodes/{pin}", response_model=GeoPinOut)
def get_pincode(user: GeoUser, db: DbDep, pin: str = Path(pattern=r"^[1-9][0-9]{5}$")) -> GeoPinOut:
    """Post offices for a PIN and the units they serve (suggestions; a PIN can cover many places)."""
    return service.pincode(db, pin)
