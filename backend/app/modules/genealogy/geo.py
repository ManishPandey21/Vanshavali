"""Coordinate privacy for geo-tagged places and events (ADR-0015 §coordinates).

Exact coordinates of an ancestral house or a living person's home are sensitive. A place can carry a
``coordinate_privacy`` level: viewers below it get coordinates rounded to ``COARSE_DECIMALS`` decimal
places (about 11 km) and the precision reported as ``approximate``. Public pages never get
coordinates at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.authz.context import TreeContext
from app.authz.privacy import level_allows
from app.models import Place
from app.models.enums import LocationPrecision

COARSE_DECIMALS = 1
_FINE = {LocationPrecision.EXACT, LocationPrecision.APPROXIMATE, LocationPrecision.LOCALITY}


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float
    precision: LocationPrecision
    coarsened: bool = False


def coarsen(lat: float, lng: float, precision: LocationPrecision | None) -> Coordinates:
    p = LocationPrecision(precision or LocationPrecision.UNKNOWN)
    return Coordinates(
        round(lat, COARSE_DECIMALS),
        round(lng, COARSE_DECIMALS),
        LocationPrecision.APPROXIMATE if p in _FINE else p,
        coarsened=True,
    )


def may_see_exact(ctx: TreeContext, place: Place) -> bool:
    if ctx.public:
        return False
    if place.coordinate_privacy is None:
        return True
    return level_allows(ctx, place.coordinate_privacy)


def place_coordinates(ctx: TreeContext, place: Place) -> Coordinates | None:
    """The coordinates this viewer may see for ``place`` (None when there are none or public)."""
    if ctx.public or place.latitude is None or place.longitude is None:
        return None
    lat, lng = float(place.latitude), float(place.longitude)
    if may_see_exact(ctx, place):
        return Coordinates(lat, lng, LocationPrecision(place.location_precision or LocationPrecision.UNKNOWN))
    return coarsen(lat, lng, place.location_precision)
