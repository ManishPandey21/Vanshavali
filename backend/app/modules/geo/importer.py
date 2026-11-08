"""Stage, review, activate and roll back geography snapshots (ADR-0019 §3).

An import is never live. It writes versioned rows into a *staged* snapshot and a change report
against what was there before; ``activate`` makes a reviewed snapshot the one queries read, and
activating the previous snapshot is the rollback. Only the newest snapshot can be imported into or
discarded, which keeps every step reversible:

* a unit valid in snapshot S has ``first_snapshot <= S`` and (``last_snapshot`` NULL or ``>= S``);
* importing into S inserts new and changed units with ``first_snapshot = S`` and closes retired
  and changed ones with ``last_snapshot = P`` (the snapshot before S);
* discarding S deletes the rows S inserted and reopens the rows it closed.

Each import covers a *scope*: the levels in its files, nationally or for one state (stage 2 with
``--state``). Units outside the scope carry forward unchanged; units inside it that the files no
longer list are retired. A scope can be imported once per snapshot.

Parents are always one level up (state > district > sub-district > village / urban body), so the
hierarchy cannot contain a cycle; a row whose parent is not known is refused.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.core import audit
from app.core.textnorm import search_key
from app.models import GeoSnapshot, GeoUnit, GeoUnitAlias, PincodeOffice, Place
from app.models.enums import GeoAliasKind, GeoLevel, GeoSnapshotStatus
from app.modules.geo.formats import (
    FormatError,
    PinRow,
    UnitRow,
    clean_code,
    clean_required,
    clean_text,
    read_file,
    read_successors,
    script_code,
)
from app.modules.geo.levels import RANK, STAGE_LEVELS

LICENCE = "Government Open Data Licence – India (GODL-India)"
MAX_FILE_BYTES = 512 * 1024 * 1024
LARGE_CHANGE_SHARE = 0.05  # more than 5% of a scope retired at once needs --accept-large-change
_SNAPSHOT_ID = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_CHUNK = 5000
CURATED_ALIASES = Path(__file__).parent / "aliases.json"


class ImportRefused(Exception):
    """The operation was refused; nothing was written. ``problems`` lists (line, message)."""

    def __init__(self, message: str, problems: Sequence[tuple[int, str]] = ()):
        super().__init__(message)
        self.problems = list(problems)


@dataclass
class ImportResult:
    snapshot: str
    summary: dict[str, dict[str, int]]
    report_path: Path | None
    changes: list[dict[str, str]] = field(default_factory=list)


# ------------------------------------------------------------------ snapshots
def latest_snapshot(db: Session) -> GeoSnapshot | None:
    return db.scalars(select(GeoSnapshot).order_by(GeoSnapshot.id.desc()).limit(1)).first()


def active_snapshot(db: Session) -> GeoSnapshot | None:
    return db.scalars(select(GeoSnapshot).where(GeoSnapshot.status == GeoSnapshotStatus.ACTIVE)).first()


def previous_snapshot_id(db: Session, snapshot_id: str) -> str | None:
    return db.scalar(select(func.max(GeoSnapshot.id)).where(GeoSnapshot.id < snapshot_id))


def _open_snapshot(db: Session, snapshot_id: str) -> GeoSnapshot:
    if not _SNAPSHOT_ID.match(snapshot_id):
        raise ImportRefused(f"snapshot must be YYYY-MM, got {snapshot_id!r}")
    latest = latest_snapshot(db)
    if latest is None or latest.id < snapshot_id:
        if latest is not None and latest.status != GeoSnapshotStatus.ACTIVE:
            raise ImportRefused(
                f"the newest snapshot {latest.id} is {latest.status.value}: activate or discard it "
                f"before importing {snapshot_id}"
            )
        snap = GeoSnapshot(id=snapshot_id, status=GeoSnapshotStatus.STAGED, imports=[])
        db.add(snap)
        db.flush()
        return snap
    if latest.id > snapshot_id:
        raise ImportRefused(f"snapshot {snapshot_id} is older than the newest snapshot {latest.id}")
    if latest.status != GeoSnapshotStatus.STAGED:
        raise ImportRefused(
            f"snapshot {snapshot_id} is {latest.status.value}: import into a new snapshot instead"
        )
    return latest


def _scope_keys(levels: Iterable[str], state: str | None) -> list[str]:
    return [f"{lv}:{state or '*'}" for lv in levels]


def _check_scope(snap: GeoSnapshot, keys: list[str]) -> None:
    done = {k for imp in snap.imports for k in imp.get("scopes", [])}
    for k in keys:
        level, _, state = k.partition(":")
        clash = k in done or (
            f"{level}:*" in done if state != "*" else any(d.startswith(f"{level}:") for d in done)
        )
        if clash:
            raise ImportRefused(
                f"snapshot {snap.id} already has an import covering {k}; discard the snapshot to "
                "import it again"
            )


# ------------------------------------------------------------------ files
def _verify(path: Path, sha256: str) -> str:
    if not path.is_file():
        raise ImportRefused(f"{path}: no such file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ImportRefused(f"{path.name}: larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256.strip().lower():
        raise ImportRefused(f"{path.name}: checksum mismatch (file is {digest})")
    return digest


def _read(path: Path) -> Any:
    try:
        return read_file(path)
    except FormatError as exc:
        raise ImportRefused(str(exc), exc.problems) from exc


# ------------------------------------------------------------------ units
def _unit_dict(r: UnitRow, anc: dict[str, str | None], snapshot: str) -> dict[str, Any]:
    return {
        "level": r.level,
        "lgd_code": r.code,
        "parent_level": r.parent_level,
        "parent_lgd_code": r.parent_code,
        "state_code": anc["state"],
        "district_code": anc["district"],
        "sub_district_code": anc["sub_district"],
        "name_en": r.name_en,
        "name_local": r.name_local,
        "local_script": r.local_script,
        "category": r.category,
        "name_key": search_key(r.name_en),
        "local_key": search_key(r.name_local) if r.name_local else "",
        "first_snapshot": snapshot,
        "last_snapshot": None,
        "successor_codes": [],
    }


def _ancestors_of(
    level: GeoLevel, code: str, state: str | None, district: str | None, sub: str | None
) -> dict[str, str | None]:
    """A unit's own state/district/sub-district codes, given its parent's."""
    anc = {"state": state, "district": district, "sub_district": sub}
    if level == GeoLevel.STATE:
        anc["state"] = code
    elif level == GeoLevel.DISTRICT:
        anc["district"] = code
    elif level == GeoLevel.SUB_DISTRICT:
        anc["sub_district"] = code
    return anc


def _current_units(
    db: Session, levels: Iterable[GeoLevel], state: str | None = None
) -> dict[tuple[GeoLevel, str], GeoUnit]:
    q = select(GeoUnit).where(GeoUnit.last_snapshot.is_(None), GeoUnit.level.in_(list(levels)))
    if state:
        q = q.where(GeoUnit.state_code == state)
    return {(u.level, u.lgd_code): u for u in db.scalars(q)}


def _import_units(
    db: Session,
    snap: GeoSnapshot,
    prev: str | None,
    rows_by_level: dict[GeoLevel, list[UnitRow]],
    state: str | None,
    successors: dict[tuple[GeoLevel, str], list[str]],
) -> tuple[dict[str, dict[str, int]], list[dict[str, str]]]:
    levels = sorted(rows_by_level, key=lambda lv: RANK[lv])
    problems: list[tuple[int, str]] = []
    # parents known in the newest view, overlaid level by level by what this import brings
    parent_levels = {lv for lv in GeoLevel if any(RANK[lv] < RANK[x] for x in levels)}
    known: dict[tuple[GeoLevel, str], dict[str, str | None]] = {
        k: {"state": u.state_code, "district": u.district_code, "sub_district": u.sub_district_code}
        for k, u in _current_units(db, parent_levels).items()
    }
    summary: dict[str, dict[str, int]] = {}
    changes: list[dict[str, str]] = []
    for level in levels:
        rows = rows_by_level[level]
        seen: dict[str, int] = {}
        incoming: dict[str, tuple[UnitRow, dict[str, str | None]]] = {}
        for r in rows:
            if r.code in seen:
                problems.append((r.line, f"{level.value} code {r.code} repeats line {seen[r.code]}"))
                continue
            seen[r.code] = r.line
            if r.parent_level is None:
                anc = _ancestors_of(level, r.code, None, None, None)
            else:
                p = known.get((r.parent_level, r.parent_code or ""))
                if p is None:
                    problems.append((r.line, f"unknown parent {r.parent_level.value} {r.parent_code}"))
                    continue
                anc = _ancestors_of(level, r.code, p["state"], p["district"], p["sub_district"])
            if state and anc["state"] != state:
                problems.append((r.line, f"{level.value} {r.code} is not in state {state}"))
                continue
            incoming[r.code] = (r, anc)
        if problems:
            raise ImportRefused(
                f"{len(problems)} row(s) refused; first, line {problems[0][0]}: {problems[0][1]}",
                problems[:50],
            )
        current = _current_units(db, [level], state)
        counts: Counter[str] = Counter(before=len(current), after=len(incoming))
        inserts: list[dict[str, Any]] = []
        close_ids: list[Any] = []
        for code, (r, anc) in incoming.items():
            known[(level, code)] = anc
            old = current.get((level, code))
            if old is None:
                inserts.append(_unit_dict(r, anc, snap.id))
                counts["new"] += 1
                changes.append(
                    {
                        "change": "new",
                        "level": level.value,
                        "lgd_code": code,
                        "name": r.name_en,
                        "parent": r.parent_code or "",
                    }
                )
                continue
            renamed = old.name_en != r.name_en or (old.name_local or None) != r.name_local
            moved = (old.parent_level, old.parent_lgd_code) != (r.parent_level, r.parent_code)
            # also a changed ancestor further up (its sub-district moved to another district)
            other = (old.category or None) != r.category or (
                old.state_code,
                old.district_code,
                old.sub_district_code,
            ) != (anc["state"], anc["district"], anc["sub_district"])
            if not (renamed or moved or other):
                counts["unchanged"] += 1
                continue
            kind = "+".join(
                k
                for k, v in (
                    ("renamed", renamed),
                    ("moved", moved),
                    ("changed", other and not (renamed or moved)),
                )
                if v
            )
            for k in kind.split("+"):
                counts[k] += 1
            close_ids.append(old.id)
            inserts.append(_unit_dict(r, anc, snap.id))
            changes.append(
                {
                    "change": kind,
                    "level": level.value,
                    "lgd_code": code,
                    "name": r.name_en,
                    "previous_name": old.name_en if renamed else "",
                    "parent": r.parent_code or "",
                    "previous_parent": old.parent_lgd_code or "" if moved else "",
                }
            )
            if old.name_en != r.name_en:
                _add_historical_alias(db, level, code, old.name_en, snap.id)
        retired = [u for k, u in current.items() if k[1] not in incoming]
        succ_count: Counter[str] = Counter()
        for u in retired:
            for s in successors.get((level, u.lgd_code), []):
                succ_count[s] += 1
        for u in retired:
            succ = successors.pop((level, u.lgd_code), [])
            for s in succ:
                if (level, s) not in known:
                    problems.append(
                        (0, f"successor {level.value} {s} of {u.lgd_code} is not in the newest data")
                    )
            if len(succ) > 1:
                kind = "split"
            elif succ and succ_count[succ[0]] > 1:
                kind = "merged"
            else:
                kind = "retired"
            counts["retired"] += 1
            if kind != "retired":
                counts[kind] += 1
            close_ids.append(u.id)
            if succ:
                db.execute(update(GeoUnit).where(GeoUnit.id == u.id).values(successor_codes=succ))
            changes.append(
                {
                    "change": kind,
                    "level": level.value,
                    "lgd_code": u.lgd_code,
                    "name": u.name_en,
                    "parent": u.parent_lgd_code or "",
                    "successors": ";".join(succ),
                }
            )
            known.pop((level, u.lgd_code), None)
        if problems:
            raise ImportRefused(f"{len(problems)} problem(s) with successors", problems[:50])
        if close_ids and prev is None:  # cannot happen: rows exist only after an earlier snapshot
            raise ImportRefused("internal error: closing rows without a previous snapshot")
        for i in range(0, len(close_ids), _CHUNK):
            db.execute(
                update(GeoUnit).where(GeoUnit.id.in_(close_ids[i : i + _CHUNK])).values(last_snapshot=prev)
            )
        db.flush()
        for i in range(0, len(inserts), _CHUNK):
            db.execute(insert(GeoUnit), inserts[i : i + _CHUNK])
        summary[level.value] = {
            k: counts[k]
            for k in (
                "before",
                "after",
                "new",
                "renamed",
                "moved",
                "changed",
                "retired",
                "merged",
                "split",
                "unchanged",
            )
        }
    leftover = [f"{lv.value} {c}" for (lv, c) in successors if lv in rows_by_level]
    if leftover:
        raise ImportRefused(
            "successors given for codes this import does not retire: " + ", ".join(leftover[:20])
        )
    return summary, changes


def _historical_source(snapshot: str) -> str:
    return f"LGD name before snapshot {snapshot}"


def _add_historical_alias(db: Session, level: GeoLevel, code: str, name: str, snapshot: str) -> None:
    key = search_key(name)
    exists = db.scalar(
        select(GeoUnitAlias.id).where(
            GeoUnitAlias.level == level, GeoUnitAlias.lgd_code == code, GeoUnitAlias.name_key == key
        )
    )
    if exists is None:
        db.add(
            GeoUnitAlias(
                level=level,
                lgd_code=code,
                name=name,
                script=script_code(name),
                kind=GeoAliasKind.HISTORICAL,
                source=_historical_source(snapshot),
                name_key=key,
            )
        )


# ------------------------------------------------------------------ PIN offices
_PIN_FIELDS = (
    "office_name",
    "office_type",
    "delivery",
    "division",
    "region",
    "circle",
    "district_name",
    "state_name",
    "taluk_name",
    "state_code",
    "district_code",
    "sub_district_code",
)


class _NameIndex:
    """Match India Post's state/district/taluk names to current LGD units, by name or alias."""

    def __init__(self, db: Session):
        units = _current_units(db, [GeoLevel.STATE, GeoLevel.DISTRICT, GeoLevel.SUB_DISTRICT])
        self.by_key: dict[tuple[GeoLevel, str | None, str], set[str]] = {}
        parent_of = {k: u.parent_lgd_code for k, u in units.items()}
        for (lv, code), u in units.items():
            for key in {u.name_key, u.local_key}:
                if key:
                    self.by_key.setdefault((lv, u.parent_lgd_code, key), set()).add(code)
        for a in db.scalars(
            select(GeoUnitAlias).where(
                GeoUnitAlias.level.in_([GeoLevel.STATE, GeoLevel.DISTRICT, GeoLevel.SUB_DISTRICT])
            )
        ):
            if (a.level, a.lgd_code) in units:
                self.by_key.setdefault((a.level, parent_of[(a.level, a.lgd_code)], a.name_key), set()).add(
                    a.lgd_code
                )

    def one(self, level: GeoLevel, parent: str | None, name: str | None) -> str | None:
        if not name:
            return None
        hits = self.by_key.get((level, parent, search_key(name)), set())
        return next(iter(hits)) if len(hits) == 1 else None


def _import_pins(
    db: Session, snap: GeoSnapshot, prev: str | None, rows: list[PinRow]
) -> tuple[dict[str, dict[str, int]], list[dict[str, str]]]:
    idx = _NameIndex(db)
    current = {
        (p.pincode, p.office_key): p
        for p in db.scalars(select(PincodeOffice).where(PincodeOffice.last_snapshot.is_(None)))
    }
    counts: Counter[str] = Counter(before=len(current))
    changes: list[dict[str, str]] = []
    incoming: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r.pincode, search_key(r.office_name)[:200] or r.office_name.lower()[:200])
        if key in incoming:
            counts["duplicates"] += 1
            changes.append(
                {
                    "change": "duplicate_skipped",
                    "level": "pincode",
                    "lgd_code": r.pincode,
                    "name": r.office_name,
                    "note": f"line {r.line}",
                }
            )
            continue
        state = idx.one(GeoLevel.STATE, None, r.state)
        district = idx.one(GeoLevel.DISTRICT, state, r.district) if state else None
        sub = idx.one(GeoLevel.SUB_DISTRICT, district, r.taluk) if district else None
        if district is None:
            counts["unmatched_district"] += 1
            changes.append(
                {
                    "change": "pin_district_unmatched",
                    "level": "pincode",
                    "lgd_code": r.pincode,
                    "name": r.office_name,
                    "note": f"district {r.district!r}, state {r.state!r}",
                }
            )
        incoming[key] = {
            "pincode": r.pincode,
            "office_key": key[1],
            "office_name": r.office_name,
            "office_type": r.office_type,
            "delivery": r.delivery,
            "division": r.division,
            "region": r.region,
            "circle": r.circle,
            "district_name": r.district,
            "state_name": r.state,
            "taluk_name": r.taluk,
            "state_code": state,
            "district_code": district,
            "sub_district_code": sub,
            "first_snapshot": snap.id,
            "last_snapshot": None,
        }
    counts["after"] = len(incoming)
    inserts: list[dict[str, Any]] = []
    close_ids: list[Any] = []
    for key, row in incoming.items():
        old = current.get(key)
        if old is None:
            counts["new"] += 1
            inserts.append(row)
        elif any(getattr(old, f) != row[f] for f in _PIN_FIELDS):
            counts["changed"] += 1
            close_ids.append(old.id)
            inserts.append(row)
        else:
            counts["unchanged"] += 1
    for key, old in current.items():
        if key not in incoming:
            counts["retired"] += 1
            close_ids.append(old.id)
            changes.append(
                {"change": "retired", "level": "pincode", "lgd_code": old.pincode, "name": old.office_name}
            )
    for i in range(0, len(close_ids), _CHUNK):
        db.execute(
            update(PincodeOffice)
            .where(PincodeOffice.id.in_(close_ids[i : i + _CHUNK]))
            .values(last_snapshot=prev)
        )
    db.flush()
    for i in range(0, len(inserts), _CHUNK):
        db.execute(insert(PincodeOffice), inserts[i : i + _CHUNK])
    keys = ("before", "after", "new", "changed", "retired", "unchanged", "unmatched_district", "duplicates")
    return {"pincode": {k: counts[k] for k in keys}}, changes


# ------------------------------------------------------------------ entry points
def import_files(
    db: Session,
    *,
    stage: int,
    snapshot: str,
    files: Sequence[tuple[Path, str]],
    state: str | None = None,
    successors_file: tuple[Path, str] | None = None,
    source_url: str | None = None,
    downloaded_on: str | None = None,
    report_dir: Path | None = None,
    operator: str | None = None,
) -> ImportResult:
    """Stage one import into ``snapshot``. The caller commits; on ImportRefused it must roll back."""
    if stage not in STAGE_LEVELS:
        raise ImportRefused("stage must be 1, 2 or 3")
    if state is not None:
        if stage != 2:
            raise ImportRefused("--state applies to stage 2 (villages and urban bodies) only")
        if not re.fullmatch(r"\d{1,20}", state):
            raise ImportRefused("--state must be an LGD state code")
        state = state.lstrip("0") or "0"
    if not files:
        raise ImportRefused("give at least one --file")
    file_info: list[dict[str, Any]] = []
    parsed = []
    for path, sha in files:
        digest = _verify(path, sha)
        pf = _read(path)
        parsed.append(pf)
        file_info.append(
            {"name": path.name, "sha256": digest, "kind": pf.kind, "rows": len(pf.units) + len(pf.pins)}
        )
    kinds = [p.kind for p in parsed]
    if len(set(kinds)) != len(kinds):
        raise ImportRefused(f"two files of the same kind: {kinds}")
    allowed = {lv.value for lv in STAGE_LEVELS[stage]} or {"pincode"}
    wrong = [k for k in kinds if k not in allowed]
    if wrong:
        raise ImportRefused(f"stage {stage} takes {sorted(allowed)} files, not {wrong}")
    successors: dict[tuple[GeoLevel, str], list[str]] = {}
    if successors_file is not None:
        if stage == 3:
            raise ImportRefused("successors apply to LGD units, not PIN offices")
        spath, ssha = successors_file
        file_info.append({"name": spath.name, "sha256": _verify(spath, ssha), "kind": "successors"})
        try:
            successors = read_successors(spath)
        except FormatError as exc:
            raise ImportRefused(str(exc), exc.problems) from exc

    snap = _open_snapshot(db, snapshot)
    scopes = _scope_keys(kinds, state)
    _check_scope(snap, scopes)
    prev = previous_snapshot_id(db, snap.id)
    if stage == 3:
        summary, changes = _import_pins(db, snap, prev, parsed[0].pins)
    else:
        rows_by_level = {GeoLevel(p.kind): p.units for p in parsed}
        summary, changes = _import_units(db, snap, prev, rows_by_level, state, successors)
    load_curated_aliases(db)

    report_path = None
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = (
            report_dir / f"geo-changes-{snap.id}-stage{stage}{'-state' + state if state else ''}.csv"
        )
        cols = [
            "change",
            "level",
            "lgd_code",
            "name",
            "previous_name",
            "parent",
            "previous_parent",
            "successors",
            "note",
        ]
        with report_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for c in changes:
                w.writerow({k: c.get(k, "") for k in cols})
    record = {
        "stage": stage,
        "state": state,
        "scopes": scopes,
        "files": file_info,
        "source_url": source_url,
        "downloaded_on": downloaded_on,
        "licence": LICENCE,
        "imported_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "imported_by": operator,
        "summary": summary,
        "report": report_path.name if report_path else None,
    }
    snap.imports = [*snap.imports, record]
    audit.record(
        db,
        action="geo.snapshot.imported",
        actor_user_id=None,
        target_type="geo_snapshot",
        summary=f"geo snapshot {snap.id}: stage {stage}{' state ' + state if state else ''} staged",
        details={
            "snapshot": snap.id,
            "stage": stage,
            "state": state,
            "operator": operator,
            "summary": summary,
        },
    )
    db.flush()
    return ImportResult(snapshot=snap.id, summary=summary, report_path=report_path, changes=changes)


def large_changes(snap: GeoSnapshot) -> list[str]:
    """Scopes in which more than LARGE_CHANGE_SHARE of the units (or PIN offices) would retire."""
    out = []
    for imp in snap.imports:
        for scope, c in (imp.get("summary") or {}).items():
            before, retired = c.get("before", 0), c.get("retired", 0)
            if before and retired / before > LARGE_CHANGE_SHARE:
                out.append(
                    f"{scope}{' (state ' + imp['state'] + ')' if imp.get('state') else ''}: {retired} of {before} retired"
                )
    return out


def activate(db: Session, snapshot: str, *, operator: str, accept_large_change: bool = False) -> str:
    """Make ``snapshot`` the active one. Activating an earlier snapshot is the rollback."""
    snap = db.get(GeoSnapshot, snapshot)
    if snap is None:
        raise ImportRefused(f"no snapshot {snapshot}")
    if snap.status == GeoSnapshotStatus.ACTIVE:
        return f"snapshot {snapshot} is already active"
    if snap.status == GeoSnapshotStatus.STAGED:
        if not snap.imports:
            raise ImportRefused(f"snapshot {snapshot} has no imports")
        big = large_changes(snap)
        if big and not accept_large_change:
            raise ImportRefused(
                "large change, review the report and pass --accept-large-change to activate: "
                + "; ".join(big)
            )
    previous = active_snapshot(db)
    if previous is not None:
        previous.status = GeoSnapshotStatus.INACTIVE
        db.flush()
    snap.status = GeoSnapshotStatus.ACTIVE
    snap.activated_at = dt.datetime.now(dt.UTC)
    snap.activated_by = operator[:120]
    audit.record(
        db,
        action="geo.snapshot.activated",
        actor_user_id=None,
        target_type="geo_snapshot",
        summary=f"geo snapshot {snapshot} activated (was {previous.id if previous else 'none'})",
        details={
            "snapshot": snapshot,
            "previous": previous.id if previous else None,
            "operator": operator[:120],
            "accept_large_change": accept_large_change,
            "rollback": bool(previous and previous.id > snapshot),
        },
    )
    db.flush()
    return f"snapshot {snapshot} is active (previously {previous.id if previous else 'none'})"


def discard(db: Session, snapshot: str, *, operator: str) -> str:
    """Delete the newest, non-active snapshot and reopen what it closed."""
    snap = db.get(GeoSnapshot, snapshot)
    if snap is None:
        raise ImportRefused(f"no snapshot {snapshot}")
    latest = latest_snapshot(db)
    if latest is None or latest.id != snapshot:
        raise ImportRefused(f"only the newest snapshot ({latest.id if latest else 'none'}) can be discarded")
    if snap.status == GeoSnapshotStatus.ACTIVE:
        raise ImportRefused(f"snapshot {snapshot} is active: activate the previous snapshot first")
    linked = db.scalar(select(func.count()).select_from(Place).where(Place.lgd_snapshot_id == snapshot))
    if linked:
        raise ImportRefused(
            f"{linked} place(s) were linked while {snapshot} was active; it cannot be discarded"
        )
    prev = previous_snapshot_id(db, snapshot)
    db.execute(delete(GeoUnit).where(GeoUnit.first_snapshot == snapshot))
    db.execute(delete(PincodeOffice).where(PincodeOffice.first_snapshot == snapshot))
    if prev is not None:
        db.execute(
            update(GeoUnit)
            .where(GeoUnit.last_snapshot == prev)
            .values(last_snapshot=None, successor_codes=[])
        )
        db.execute(
            update(PincodeOffice).where(PincodeOffice.last_snapshot == prev).values(last_snapshot=None)
        )
    db.execute(
        delete(GeoUnitAlias).where(
            GeoUnitAlias.kind == GeoAliasKind.HISTORICAL, GeoUnitAlias.source == _historical_source(snapshot)
        )
    )
    db.delete(snap)
    audit.record(
        db,
        action="geo.snapshot.discarded",
        actor_user_id=None,
        target_type="geo_snapshot",
        summary=f"geo snapshot {snapshot} discarded",
        details={"snapshot": snapshot, "operator": operator[:120]},
    )
    db.flush()
    return f"snapshot {snapshot} discarded"


def load_curated_aliases(db: Session, path: Path = CURATED_ALIASES) -> int:
    """Replace the curated aliases with the reviewed file's entries. Returns how many there are."""
    raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"entries": []}
    rows: dict[tuple[GeoLevel, str, str], dict[str, Any]] = {}
    for e in raw.get("entries", []):
        level = GeoLevel(e["level"])
        code = clean_code(str(e["lgd_code"]), what="lgd_code")
        name = clean_required(e["name"], what="alias")
        key = search_key(name)
        rows[(level, code, key)] = {
            "level": level,
            "lgd_code": code,
            "name": name,
            "script": script_code(name),
            "kind": GeoAliasKind.CURATED,
            "source": clean_text(e.get("source"), what="source"),
            "name_key": key,
        }
    db.execute(delete(GeoUnitAlias).where(GeoUnitAlias.kind == GeoAliasKind.CURATED))
    db.flush()
    existing = {(a.level, a.lgd_code, a.name_key) for a in db.scalars(select(GeoUnitAlias))}
    new = [r for k, r in rows.items() if k not in existing]
    if new:
        db.execute(insert(GeoUnitAlias), new)
    return len(rows)
