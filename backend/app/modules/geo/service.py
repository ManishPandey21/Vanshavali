"""Read-only lookups in the active geography snapshots (ADR-0019 §4).

Public reference data for signed-in users. Nothing here reads or writes tree data.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.schemas import decode_cursor, encode_cursor
from app.core.config import get_settings
from app.core.errors import NotFound, Unprocessable
from app.core.textnorm import search_key
from app.models import GeoPinOffice, GeoPinUnit, GeoSnapshot, GeoUnit
from app.models.enums import GeoLevel, GeoSnapshotStatus, GeoSource
from app.modules.geo.importer import active_snapshot
from app.modules.geo.schemas import (
    GeoOfficeOut,
    GeoPinOut,
    GeoRef,
    GeoSnapshotInfo,
    GeoUnitOut,
    GeoUnitPage,
)

MAX_PAGE = 100
# levels with so many rows that listing them without a parent or a search is refused
LARGE_LEVELS = {
    GeoLevel.VILLAGE,
    GeoLevel.GRAM_PANCHAYAT,
    GeoLevel.TOWN,
    GeoLevel.ULB,
    GeoLevel.BLOCK,
    GeoLevel.SUBDISTRICT,
}


def _enabled() -> None:
    if not get_settings().geo_enabled:
        raise NotFound("Not found")


def _info(s: GeoSnapshot | None) -> GeoSnapshotInfo | None:
    if s is None:
        return None
    return GeoSnapshotInfo(source=s.source, label=s.label, licence=s.licence, attribution=s.attribution)


def _paths(db: Session, units: list[GeoUnit]) -> dict[uuid.UUID, list[GeoRef]]:
    """Ancestors of each unit (state downwards), loaded a level at a time."""
    known: dict[uuid.UUID, GeoUnit] = {u.id: u for u in units}
    wanted = {u.parent_id for u in units if u.parent_id}
    while wanted - known.keys():
        missing = wanted - known.keys()
        rows = list(db.scalars(select(GeoUnit).where(GeoUnit.id.in_(missing))))
        for r in rows:
            known[r.id] = r
        wanted = {r.parent_id for r in rows if r.parent_id}
        if not rows:
            break
    out: dict[uuid.UUID, list[GeoRef]] = {}
    for u in units:
        chain: list[GeoRef] = []
        p = known.get(u.parent_id) if u.parent_id else None
        while p is not None and p.level != GeoLevel.COUNTRY:
            chain.append(GeoRef(level=p.level, code=p.code, name_en=p.name_en, name_local=p.name_local))
            p = known.get(p.parent_id) if p.parent_id else None
        out[u.id] = list(reversed(chain))
    return out


def _status(u: GeoUnit, active: bool) -> str:
    if not active:
        return "retired"
    if u.valid_to is not None and u.valid_to < dt.date.today():
        return "historical"
    return "current"


def _out(u: GeoUnit, path: list[GeoRef], *, active: bool = True) -> GeoUnitOut:
    return GeoUnitOut(
        level=u.level,
        code=u.code,
        name_en=u.name_en,
        name_local=u.name_local,
        local_script=u.local_script,
        local_term=u.local_term,
        category=u.category,
        alt_names=u.alt_names,
        former_names=u.former_names,
        status=_status(u, active),  # type: ignore[arg-type]
        valid_to=u.valid_to,
        successor_codes=u.successor_codes,
        path=path,
    )


def _like(q: str) -> tuple[str, str]:
    k = search_key(q)
    k = k.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{k}%", f"% {k}%"


def units(
    db: Session,
    *,
    level: GeoLevel | None = None,
    parent_level: GeoLevel | None = None,
    parent_code: str | None = None,
    q: str = "",
    include_historical: bool = False,
    cursor: str | None = None,
    limit: int = 50,
) -> GeoUnitPage:
    """Children of a unit, or units of one level, optionally filtered by a search in any script."""
    _enabled()
    snap = active_snapshot(db, GeoSource.LGD)
    if snap is None:
        return GeoUnitPage(items=[], snapshot=None)
    stmt = select(GeoUnit).where(GeoUnit.snapshot_id == snap.id)
    if (parent_level is None) != (parent_code is None):
        raise Unprocessable("Give both parent_level and parent_code", code="invalid_parent")
    if parent_level is not None:
        parent = db.scalar(
            select(GeoUnit.id).where(
                GeoUnit.snapshot_id == snap.id, GeoUnit.level == parent_level, GeoUnit.code == parent_code
            )
        )
        if parent is None:
            raise NotFound("Unit not found")
        stmt = stmt.where(GeoUnit.parent_id == parent)
    elif level is None and not q.strip():
        level = GeoLevel.STATE
    if level is not None:
        stmt = stmt.where(GeoUnit.level == level)
    key = search_key(q) if q.strip() else ""
    if key:
        a, b = _like(q)
        stmt = stmt.where(
            or_(GeoUnit.search_key.like(a, escape="\\"), GeoUnit.search_key.like(b, escape="\\"))
        )
    elif parent_level is None and level in LARGE_LEVELS:
        raise Unprocessable("Choose the parent unit or type part of the name first", code="search_too_broad")
    elif q.strip():
        return GeoUnitPage(items=[], snapshot=_info(snap))
    if not include_historical:
        stmt = stmt.where(or_(GeoUnit.valid_to.is_(None), GeoUnit.valid_to >= dt.date.today()))
    offset = decode_cursor(cursor)
    limit = max(1, min(limit, MAX_PAGE))
    rows = list(db.scalars(stmt.order_by(GeoUnit.name_en, GeoUnit.code).offset(offset).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    paths = _paths(db, rows)
    return GeoUnitPage(
        items=[_out(u, paths[u.id]) for u in rows],
        next_cursor=encode_cursor(offset + limit) if more else None,
        snapshot=_info(snap),
    )


def unit(db: Session, level: GeoLevel, code: str) -> GeoUnitOut:
    """One unit. A code no longer in the active snapshot still resolves from an older one, as retired."""
    _enabled()
    snap = active_snapshot(db, GeoSource.LGD)
    if snap is not None:
        u = db.scalar(
            select(GeoUnit).where(
                GeoUnit.snapshot_id == snap.id, GeoUnit.level == level, GeoUnit.code == code
            )
        )
        if u is not None:
            return _out(u, _paths(db, [u])[u.id])
    old = db.scalar(
        select(GeoUnit)
        .join(GeoSnapshot, GeoSnapshot.id == GeoUnit.snapshot_id)
        .where(
            GeoUnit.level == level,
            GeoUnit.code == code,
            GeoSnapshot.source == GeoSource.LGD,
            GeoSnapshot.status == GeoSnapshotStatus.SUPERSEDED,
        )
        .order_by(GeoSnapshot.activated_at.desc().nullslast(), GeoSnapshot.created_at.desc())
        .limit(1)
    )
    if old is None:
        raise NotFound("Unit not found")
    return _out(old, _paths(db, [old])[old.id], active=False)


def pincode(db: Session, pin: str) -> GeoPinOut:
    """Offices for a PIN and the units each serves. Suggestions only: a PIN is not a village."""
    _enabled()
    post = active_snapshot(db, GeoSource.INDIA_POST)
    if post is None:
        return GeoPinOut(pin=pin, offices=[], snapshot=None)
    offices = list(
        db.scalars(
            select(GeoPinOffice)
            .where(GeoPinOffice.snapshot_id == post.id, GeoPinOffice.pin == pin)
            .order_by(GeoPinOffice.office_name)
        )
    )
    links: dict[uuid.UUID, list[tuple[str, str]]] = {}
    for oid, lv, code in db.execute(
        select(GeoPinUnit.office_id, GeoPinUnit.unit_level, GeoPinUnit.unit_code).where(
            GeoPinUnit.office_id.in_([o.id for o in offices])
        )
    ):
        links.setdefault(oid, []).append((str(lv), code))
    lgd = active_snapshot(db, GeoSource.LGD)
    resolved: dict[tuple[str, str], GeoUnit] = {}
    wanted = {ref for refs in links.values() for ref in refs}
    if lgd is not None and wanted:
        for u in db.scalars(
            select(GeoUnit).where(
                GeoUnit.snapshot_id == lgd.id,
                GeoUnit.code.in_({c for _, c in wanted}),
            )
        ):
            if (str(u.level), u.code) in wanted:
                resolved[(str(u.level), u.code)] = u
    paths = _paths(db, list(resolved.values()))
    return GeoPinOut(
        pin=pin,
        offices=[
            GeoOfficeOut(
                office_name=o.office_name,
                office_type=o.office_type,
                delivery=o.delivery,
                district_name=o.district_name,
                state_name=o.state_name,
                units=[
                    _out(resolved[ref], paths[resolved[ref].id])
                    for ref in links.get(o.id, [])
                    if ref in resolved
                ],
            )
            for o in offices
        ],
        snapshot=_info(post),
    )
