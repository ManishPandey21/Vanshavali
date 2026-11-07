"""Read the active geography snapshot: cascades, search, PIN suggestions, place notes (ADR-0019).

Everything here reads the rows valid in the *active* snapshot only. When the active snapshot is
also the newest one (the usual case), that is simply ``last_snapshot IS NULL``, which the partial
indexes cover; after a rollback it is the version range.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, and_, case, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound, Unprocessable
from app.core.textnorm import search_key
from app.models import GeoSnapshot, GeoUnit, GeoUnitAlias, PincodeOffice, Place
from app.models.enums import GeoLevel, GeoSnapshotStatus
from app.modules.geo.levels import PARENT_LEVEL, sub_district_label
from app.modules.translit import engine as translit

ATTRIBUTION = "Source: Local Government Directory, Government of India; India Post"
SEARCH_CANDIDATES = 200
TRIGRAM_THRESHOLD = 0.4
_ANCESTOR_COLUMN = {
    GeoLevel.STATE: GeoUnit.state_code,
    GeoLevel.DISTRICT: GeoUnit.district_code,
    GeoLevel.SUB_DISTRICT: GeoUnit.sub_district_code,
}


@dataclass(frozen=True)
class Active:
    id: str
    newest: bool
    activated_at: Any


def enabled() -> None:
    if not get_settings().geo_enabled:
        raise NotFound("Not found")


def active(db: Session) -> Active:
    """The active snapshot, or 404 when the feature is off or no snapshot was activated."""
    enabled()
    snap = db.scalars(select(GeoSnapshot).where(GeoSnapshot.status == GeoSnapshotStatus.ACTIVE)).first()
    if snap is None:
        raise NotFound("No geography reference data is loaded")
    newest = db.scalar(select(func.max(GeoSnapshot.id)))
    return Active(id=snap.id, newest=newest == snap.id, activated_at=snap.activated_at)


def active_or_none(db: Session) -> Active | None:
    try:
        return active(db)
    except NotFound:
        return None


def valid_in(model: Any, snapshot: str, newest: bool = False) -> ColumnElement[bool]:
    if newest:
        return model.last_snapshot.is_(None)  # type: ignore[no-any-return]
    return and_(
        model.first_snapshot <= snapshot,
        or_(model.last_snapshot.is_(None), model.last_snapshot >= snapshot),
    )


def _valid(a: Active) -> ColumnElement[bool]:
    return valid_in(GeoUnit, a.id, a.newest)


# ------------------------------------------------------------------ serialisation
def _path(db: Session, a: Active, units: list[GeoUnit]) -> dict[tuple[GeoLevel, str], GeoUnit]:
    """The ancestors (state, district, sub-district) of ``units``, valid in the active snapshot."""
    wanted: set[tuple[GeoLevel, str]] = set()
    for u in units:
        for lv, code in (
            (GeoLevel.STATE, u.state_code),
            (GeoLevel.DISTRICT, u.district_code),
            (GeoLevel.SUB_DISTRICT, u.sub_district_code),
        ):
            if code and not (lv == u.level and code == u.lgd_code):
                wanted.add((lv, code))
    if not wanted:
        return {}
    conds = [and_(GeoUnit.level == lv, GeoUnit.lgd_code == c) for lv, c in wanted]
    rows = db.scalars(select(GeoUnit).where(_valid(a), or_(*conds)))
    return {(r.level, r.lgd_code): r for r in rows}


def _brief(u: GeoUnit) -> dict[str, Any]:
    return {
        "level": u.level,
        "lgd_code": u.lgd_code,
        "name_en": u.name_en,
        "name_local": u.name_local,
        "local_script": u.local_script,
    }


def unit_out(
    u: GeoUnit, anc: dict[tuple[GeoLevel, str], GeoUnit], match: dict[str, str] | None = None
) -> dict[str, Any]:
    path = []
    for lv, code in (
        (GeoLevel.STATE, u.state_code),
        (GeoLevel.DISTRICT, u.district_code),
        (GeoLevel.SUB_DISTRICT, u.sub_district_code),
    ):
        if code and (lv, code) in anc:
            path.append(_brief(anc[(lv, code)]))
    return {
        **_brief(u),
        "category": u.category,
        "parent_level": u.parent_level,
        "parent_lgd_code": u.parent_lgd_code,
        "state_code": u.state_code,
        "district_code": u.district_code,
        "sub_district_code": u.sub_district_code,
        "sub_district_label": sub_district_label(u.state_code),
        "ancestors": path,
        "match": match,
    }


# ------------------------------------------------------------------ listing and search
def _scope(
    parent: str | None, parent_level: GeoLevel | None, level: GeoLevel | None
) -> ColumnElement[bool] | None:
    if parent is None:
        return None
    pl = parent_level or (PARENT_LEVEL.get(level) if level else None)
    if pl is None or pl not in _ANCESTOR_COLUMN:
        raise Unprocessable("parent_level must be state, district or sub_district")
    if level is not None and pl == level:
        raise Unprocessable("parent_level must be above level")
    col = _ANCESTOR_COLUMN[pl]
    return col == parent  # type: ignore[no-any-return]


def children(
    db: Session,
    a: Active,
    level: GeoLevel,
    parent: str | None,
    parent_level: GeoLevel | None,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    if level != GeoLevel.STATE and parent is None:
        raise Unprocessable("parent is required to list this level; or search with q")
    stmt = select(GeoUnit).where(_valid(a), GeoUnit.level == level)
    scope = _scope(parent, parent_level, level)
    if scope is not None:
        stmt = stmt.where(scope)
    rows = list(db.scalars(stmt.order_by(GeoUnit.name_en, GeoUnit.lgd_code).offset(offset).limit(limit + 1)))
    anc = _path(db, a, rows[:limit])
    return [unit_out(u, anc) for u in rows[:limit]], len(rows) > limit


def _query_keys(q: str) -> tuple[list[str], list[str]]:
    """Search keys for the English-name column and for the local-script-name column.

    The typed text's own key goes against the column of its script, and its transliterations
    (ADR-0025 engine) against the other, so "रामपुर" also meets "Rampur" and "Rampur" meets
    "रामपुर", without comparing every key with both columns.
    """
    own = search_key(q)
    script = translit.script_of(q)
    target: translit.Script | None = "Latn" if script == "Deva" else "Deva" if script == "Latn" else None
    other = [search_key(c.text) for c in translit.suggest(q, target)[:2]] if target else []

    def uniq(xs: list[str]) -> list[str]:
        return [k for i, k in enumerate(xs) if k and k not in xs[:i]]

    if script == "Latn":
        return uniq([own]), uniq(other)
    if script == "Deva":
        return uniq(other), uniq([own])
    return uniq([own]), uniq([own])


def search(
    db: Session,
    a: Active,
    q: str,
    levels: list[GeoLevel],
    parent: str | None,
    parent_level: GeoLevel | None,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    q = q.strip()
    if len(q) < 2:
        raise Unprocessable("type at least two letters")
    name_keys, local_keys = _query_keys(q)
    keys = list(dict.fromkeys(name_keys + local_keys))  # for aliases, which may be in either script
    if not keys:
        return [], False
    scope = _scope(parent, parent_level, levels[0] if len(levels) == 1 else None)
    short = min(len(k) for k in keys) < 3
    if short and scope is None:
        return [], False  # two letters across all of India would match everything

    def sim(col: Any, ks: list[str]) -> Any:
        if not ks:
            return literal(0.0)
        return (
            func.greatest(*[func.similarity(col, k) for k in ks])
            if len(ks) > 1
            else func.similarity(col, ks[0])
        )

    def prefixed(pairs: list[tuple[Any, list[str]]]) -> ColumnElement[bool]:
        return or_(*[c.like(k + "%") for c, ks in pairs for k in ks])

    def exact_first(pairs: list[tuple[Any, list[str]]]) -> Any:
        return case((or_(*[c.in_(ks) for c, ks in pairs if ks]), 0), else_=1)

    def fuzzy(pairs: list[tuple[Any, list[str]]]) -> ColumnElement[bool]:
        return or_(*[c.op("%")(k) for c, ks in pairs for k in ks])

    unit_pairs = [(GeoUnit.name_key, name_keys), (GeoUnit.local_key, local_keys)]
    unit_pairs = [(c, ks) for c, ks in unit_pairs if ks]
    alias_pairs = [(GeoUnitAlias.name_key, keys)]
    unit_cols = (sim(GeoUnit.name_key, name_keys), sim(GeoUnit.local_key, local_keys))
    base = [_valid(a), GeoUnit.level.in_(levels)]
    if scope is not None:
        base.append(scope)
    alias_join = and_(GeoUnitAlias.level == GeoUnit.level, GeoUnitAlias.lgd_code == GeoUnit.lgd_code)

    # 1. exact and prefix matches (btree text_pattern_ops indexes), exact ones first: an exact
    #    match is never crowded out of the candidates by many prefix matches
    unit_rows = list(
        db.execute(
            select(GeoUnit, *unit_cols, literal(None))
            .where(*base, prefixed(unit_pairs))
            .order_by(exact_first(unit_pairs), GeoUnit.name_en, GeoUnit.lgd_code)
            .limit(SEARCH_CANDIDATES)
        ).all()
    )
    alias_rows = list(
        db.execute(
            select(GeoUnit, sim(GeoUnitAlias.name_key, keys), literal(0.0), GeoUnitAlias.name)
            .join(GeoUnitAlias, alias_join)
            .where(*base, prefixed(alias_pairs))
            .order_by(exact_first(alias_pairs), GeoUnit.name_en)
            .limit(SEARCH_CANDIDATES)
        ).all()
    )
    # 2. similar spellings (trigram), best first, only when the page is not already full
    if not short and len(unit_rows) + len(alias_rows) <= offset + limit:
        # 0.4 keeps real variants (Phoolpur/Phulpur 0.42) but not every name sharing "-nagar":
        # at the default 0.3 a common suffix matched ~4% of all villages (benchmark, Nov 2026)
        db.execute(text(f"SET LOCAL pg_trgm.similarity_threshold = {TRIGRAM_THRESHOLD}"))
        unit_rows += db.execute(
            select(GeoUnit, *unit_cols, literal(None))
            .where(*base, fuzzy(unit_pairs))
            .order_by(func.greatest(*unit_cols).desc())
            .limit(SEARCH_CANDIDATES)
        ).all()
        alias_rows += db.execute(
            select(GeoUnit, sim(GeoUnitAlias.name_key, keys), literal(0.0), GeoUnitAlias.name)
            .join(GeoUnitAlias, alias_join)
            .where(*base, fuzzy(alias_pairs))
            .order_by(sim(GeoUnitAlias.name_key, keys).desc())
            .limit(SEARCH_CANDIDATES)
        ).all()

    keyset = set(keys)

    def rank(key: str) -> int:
        if key in keyset:
            return 0
        if any(key.startswith(k) for k in keys):
            return 1
        return 2

    best: dict[Any, tuple[int, float, str, dict[str, str]]] = {}
    units_by_id: dict[Any, GeoUnit] = {}
    for u, s_name, s_local, alias in [*unit_rows, *alias_rows]:
        if alias is not None:
            cands = [(rank(search_key(alias)), float(s_name or 0), {"reason": "alias", "text": alias})]
        else:
            cands = [(rank(u.name_key), float(s_name or 0), {"reason": "name", "text": u.name_en})]
            if u.local_key:
                cands.append(
                    (
                        rank(u.local_key),
                        float(s_local or 0),
                        {"reason": "local_name", "text": u.name_local or ""},
                    )
                )
        r, s, m = min(cands, key=lambda c: (c[0], -c[1]))
        cur = best.get(u.id)
        if cur is None or (r, -s) < (cur[0], -cur[1]):
            best[u.id] = (r, s, u.name_en, m)
            units_by_id[u.id] = u
    ordered = sorted(
        best.items(), key=lambda kv: (kv[1][0], -kv[1][1], kv[1][2], units_by_id[kv[0]].lgd_code)
    )
    page = ordered[offset : offset + limit]
    units = [units_by_id[uid] for uid, _ in page]
    anc = _path(db, a, units)
    return [unit_out(units_by_id[uid], anc, v[3]) for uid, v in page], len(ordered) > offset + limit


# ------------------------------------------------------------------ one unit
def _versions(db: Session, level: GeoLevel, code: str) -> list[GeoUnit]:
    return list(
        db.scalars(
            select(GeoUnit)
            .where(GeoUnit.level == level, GeoUnit.lgd_code == code)
            .order_by(GeoUnit.first_snapshot)
        )
    )


def version_at(db: Session, level: GeoLevel, code: str, snapshot: str) -> GeoUnit | None:
    return db.scalars(
        select(GeoUnit).where(GeoUnit.level == level, GeoUnit.lgd_code == code, valid_in(GeoUnit, snapshot))
    ).first()


def current_unit(db: Session, a: Active, level: GeoLevel, code: str) -> GeoUnit | None:
    return db.scalars(
        select(GeoUnit).where(_valid(a), GeoUnit.level == level, GeoUnit.lgd_code == code)
    ).first()


def unit_detail(db: Session, a: Active, level: GeoLevel, code: str) -> dict[str, Any]:
    u = current_unit(db, a, level, code)
    status = "current"
    if u is None:
        # retired before the active snapshot: show its last version and its successors
        older = [v for v in _versions(db, level, code) if v.first_snapshot <= a.id]
        if not older:
            raise NotFound("No such unit")
        u = older[-1]
        status = "retired"
    anc = _path(db, a, [u])
    successors = []
    if status == "retired" and u.successor_codes:
        succ = list(
            db.scalars(
                select(GeoUnit).where(
                    _valid(a), GeoUnit.level == level, GeoUnit.lgd_code.in_(u.successor_codes)
                )
            )
        )
        sanc = _path(db, a, succ)
        successors = [unit_out(s, sanc) for s in succ]
    aliases = [
        {"name": al.name, "kind": al.kind, "script": al.script}
        for al in db.scalars(
            select(GeoUnitAlias)
            .where(GeoUnitAlias.level == level, GeoUnitAlias.lgd_code == code)
            .order_by(GeoUnitAlias.name)
        )
    ]
    return {**unit_out(u, anc), "status": status, "successors": successors, "aliases": aliases}


# ------------------------------------------------------------------ PIN codes
def pincode(db: Session, a: Active, pin: str) -> dict[str, Any]:
    offices = list(
        db.scalars(
            select(PincodeOffice)
            .where(valid_in(PincodeOffice, a.id, a.newest), PincodeOffice.pincode == pin)
            .order_by(PincodeOffice.office_name)
        )
    )
    if not offices:
        raise NotFound("No post office with this PIN code")
    wanted = {
        GeoLevel.STATE: {o.state_code for o in offices if o.state_code},
        GeoLevel.DISTRICT: {o.district_code for o in offices if o.district_code},
        GeoLevel.SUB_DISTRICT: {o.sub_district_code for o in offices if o.sub_district_code},
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for lv, codes in wanted.items():
        units = (
            list(
                db.scalars(
                    select(GeoUnit)
                    .where(_valid(a), GeoUnit.level == lv, GeoUnit.lgd_code.in_(codes))
                    .order_by(GeoUnit.name_en)
                )
            )
            if codes
            else []
        )
        anc = _path(db, a, units)
        out[lv.value] = [unit_out(u, anc) for u in units]
    return {
        "pincode": pin,
        "offices": [
            {
                "office_name": o.office_name,
                "office_type": o.office_type,
                "delivery": o.delivery,
                "district_name": o.district_name,
                "state_name": o.state_name,
                "district_lgd_code": o.district_code,
            }
            for o in offices
        ],
        "states": out["state"],
        "districts": out["district"],
        "sub_districts": out["sub_district"],
    }


# ------------------------------------------------------------------ tree places
def link_snapshot(db: Session, level: GeoLevel, code: str | None) -> str:
    """Validate a code picked from the cascade; return the active snapshot to record with it."""
    if not code:
        raise Unprocessable("lgd_code is required with lgd_level")
    a = active_or_none(db)
    if a is None:
        raise Unprocessable("Geography reference data is not available; save the place without lgd_level")
    if current_unit(db, a, level, code) is None:
        raise Unprocessable("No such unit in the current Local Government Directory data")
    return a.id


def place_notes(db: Session, places: list[Place]) -> dict[Any, dict[str, Any]]:
    """Non-blocking notes for linked places whose unit changed since it was picked (ADR-0019 §4).

    Read-only: nothing on the place changes. Returns {place_id: note}.
    """
    linked = [p for p in places if p.lgd_level and p.lgd_code and p.lgd_snapshot_id]
    if not linked:
        return {}
    a = active_or_none(db)
    if a is None:
        return {}
    notes: dict[Any, dict[str, Any]] = {}
    for p in linked:
        if p.lgd_snapshot_id == a.id:
            continue
        level = p.lgd_level
        if level is None:
            continue
        then = version_at(db, level, p.lgd_code or "", p.lgd_snapshot_id or "")
        now = current_unit(db, a, level, p.lgd_code or "")
        if then is None:
            continue
        if now is None:
            succ = []
            if then.successor_codes:
                succ = [
                    _brief(s)
                    for s in db.scalars(
                        select(GeoUnit).where(
                            _valid(a), GeoUnit.level == level, GeoUnit.lgd_code.in_(then.successor_codes)
                        )
                    )
                ]
            since = db.scalar(
                select(func.min(GeoSnapshot.id)).where(GeoSnapshot.id > (then.last_snapshot or ""))
            )
            notes[p.id] = {"kind": "retired", "since": since, "unit": _brief(then), "successors": succ}
            continue
        kinds = []
        if (now.name_en, now.name_local) != (then.name_en, then.name_local):
            kinds.append("renamed")
        if (now.state_code, now.district_code, now.sub_district_code) != (
            then.state_code,
            then.district_code,
            then.sub_district_code,
        ):
            kinds.append("moved")
        anc = _path(db, a, [now])
        since = now.first_snapshot
        if "moved" not in kinds:
            # the unit is unchanged but its district (or sub-district, state) was renamed
            for (lv, code), cur in anc.items():
                old = version_at(db, lv, code, p.lgd_snapshot_id or "")
                if old is not None and old.name_en != cur.name_en:
                    kinds.append("ancestor_renamed")
                    since = cur.first_snapshot
                    break
        if not kinds:
            continue
        notes[p.id] = {
            "kind": "+".join(kinds),
            "since": since,
            "unit": unit_out(now, anc),
            "previous_name": then.name_en if "renamed" in kinds else None,
        }
    return notes
