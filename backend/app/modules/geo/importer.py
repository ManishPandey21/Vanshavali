"""Stage an official geography snapshot from a canonical CSV (ADR-0019 §3, increment 1).

``stage`` reads the file under strict limits, validates every row and the hierarchy, and either
records a **failed** snapshot (with the errors, inserting no rows) or inserts the rows into a new
**validated** snapshot together with a diff against the currently active snapshot of the same
source. Staged rows are invisible to users until an administrator approves and another activates
the snapshot. The canonical formats are documented in ``docs/operations/geo-import.md``.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.orm import Session, aliased

from app.core.ids import uuid7
from app.core.textnorm import search_key
from app.models import GeoPinOffice, GeoPinUnit, GeoSnapshot, GeoUnit
from app.models.enums import GeoLevel, GeoSnapshotStatus, GeoSource, GeoUnitOrigin
from app.models.geo import PARENT_LEVELS

LGD_HEADER = [
    "level",
    "code",
    "parent_level",
    "parent_code",
    "name_en",
    "name_local",
    "local_script",
    "local_term",
    "category",
    "alternate_names",
    "former_names",
    "valid_from",
    "valid_to",
    "successor_codes",
]
POST_HEADER = ["pin", "office_name", "office_type", "delivery", "district", "state", "unit_codes"]

MAX_BYTES = 300 * 1024 * 1024
MAX_ROWS = 1_500_000
MAX_FIELD = 200
MAX_LIST = 20
MAX_MESSAGES = 200
SAMPLES = 20
BATCH = 5000

# insert parents before children
DEPTH = {
    "country": 0,
    "state": 1,
    "district": 2,
    "subdistrict": 3,
    "block": 3,
    "ulb": 3,
    "town": 4,
    "gram_panchayat": 4,
    "village": 4,
}
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_LGD_CODE = re.compile(r"^[0-9]{1,12}$")
_PIN = re.compile(r"^[1-9][0-9]{5}$")
_SCRIPT = re.compile(r"^[A-Z][a-z]{3}$")
_OFFICE_TYPES = {"H.O.", "S.O.", "B.O.", "HO", "SO", "BO"}


class GeoImportError(ValueError):
    """The file itself is unusable (too large, not UTF-8, wrong header…). No snapshot is created."""


@dataclass
class Messages:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0

    def error(self, line: int, msg: str) -> None:
        self.error_count += 1
        if len(self.errors) < MAX_MESSAGES:
            self.errors.append(f"line {line}: {msg}")

    def warn(self, line: int, msg: str) -> None:
        self.warning_count += 1
        if len(self.warnings) < MAX_MESSAGES:
            self.warnings.append(f"line {line}: {msg}")


@dataclass
class UnitRow:
    line: int
    level: str
    code: str
    parent_level: str | None
    parent_code: str | None
    name_en: str
    name_local: str | None
    local_script: str | None
    local_term: str | None
    category: str | None
    alt_names: list[str]
    former_names: list[str]
    valid_from: dt.date | None
    valid_to: dt.date | None
    successor_codes: list[str]


@dataclass
class OfficeRow:
    line: int
    pin: str
    office_name: str
    office_type: str | None
    delivery: bool | None
    district: str | None
    state: str | None
    units: list[tuple[str, str]]


# ---------------------------------------------------------------- reading
def read_file(path: Path) -> tuple[bytes, str]:
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise GeoImportError(f"{path.name}: {size} bytes is over the {MAX_BYTES} byte limit")
    if size == 0:
        raise GeoImportError(f"{path.name}: the file is empty")
    data = path.read_bytes()
    if b"\x00" in data:
        raise GeoImportError(f"{path.name}: binary content (NUL byte); expected a UTF-8 CSV file")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GeoImportError(f"{path.name}: not valid UTF-8 ({exc.reason} at byte {exc.start})") from exc
    return data, text


def _rows(text: str, header: list[str], name: str) -> list[tuple[int, dict[str, str]]]:
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        got = next(reader)
    except StopIteration as exc:
        raise GeoImportError(f"{name}: no header row") from exc
    if [h.strip() for h in got] != header:
        raise GeoImportError(f"{name}: the header must be exactly: {','.join(header)}")
    out: list[tuple[int, dict[str, str]]] = []
    for i, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        if len(out) >= MAX_ROWS:
            raise GeoImportError(f"{name}: more than {MAX_ROWS} rows")
        if len(row) != len(header):
            out.append((i, {"__bad__": f"expected {len(header)} columns, found {len(row)}"}))
            continue
        out.append((i, {k: v.strip() for k, v in zip(header, row, strict=True)}))
    return out


def _text(m: Messages, line: int, value: str, name: str, *, required: bool = False) -> str | None:
    if not value:
        if required:
            m.error(line, f"{name} is required")
        return None
    if len(value) > MAX_FIELD:
        m.error(line, f"{name} is longer than {MAX_FIELD} characters")
        return None
    if any(ord(ch) < 32 for ch in value):
        m.error(line, f"{name} contains control characters")
        return None
    return value


def _list(m: Messages, line: int, value: str, name: str) -> list[str]:
    items = [x.strip() for x in value.split("|") if x.strip()] if value else []
    if len(items) > MAX_LIST:
        m.error(line, f"{name}: at most {MAX_LIST} entries")
        return []
    return [x for x in items if _text(m, line, x, name) is not None]


def _date(m: Messages, line: int, value: str, name: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        m.error(line, f"{name} must be a date like 2026-10-01")
        return None


def _code_ok(level: str, code: str) -> bool:
    return bool(_COUNTRY_CODE.match(code) if level == "country" else _LGD_CODE.match(code))


def parse_units(text: str, name: str, m: Messages) -> list[UnitRow]:
    levels = {lv.value for lv in GeoLevel}
    out: list[UnitRow] = []
    for line, r in _rows(text, LGD_HEADER, name):
        if "__bad__" in r:
            m.error(line, r["__bad__"])
            continue
        level = r["level"]
        if level not in levels:
            m.error(line, f"unknown level {level!r}")
            continue
        code = r["code"]
        if not _code_ok(level, code):
            m.error(line, f"bad {level} code {code!r}")
            continue
        parent_level = r["parent_level"] or None
        parent_code = r["parent_code"] or None
        if level == "country":
            if parent_level or parent_code:
                m.error(line, "a country has no parent")
                continue
        elif parent_level not in PARENT_LEVELS[level] or not parent_code:
            m.error(line, f"a {level} needs a parent of level {' or '.join(PARENT_LEVELS[level])}")
            continue
        script = _text(m, line, r["local_script"], "local_script")
        if script and not _SCRIPT.match(script):
            m.error(line, f"local_script must be an ISO 15924 code such as Deva, not {script!r}")
            script = None
        name_en = _text(m, line, r["name_en"], "name_en", required=True)
        successors = _list(m, line, r["successor_codes"], "successor_codes")
        if any(not _code_ok(level, s) for s in successors):
            m.error(line, "successor_codes must be codes of the same level")
            successors = []
        valid_from = _date(m, line, r["valid_from"], "valid_from")
        valid_to = _date(m, line, r["valid_to"], "valid_to")
        if valid_from and valid_to and valid_to < valid_from:
            m.error(line, "valid_to is before valid_from")
        if name_en is None:
            continue
        out.append(
            UnitRow(
                line=line,
                level=level,
                code=code,
                parent_level=parent_level,
                parent_code=parent_code,
                name_en=name_en,
                name_local=_text(m, line, r["name_local"], "name_local"),
                local_script=script,
                local_term=_text(m, line, r["local_term"], "local_term"),
                category=_text(m, line, r["category"], "category"),
                alt_names=_list(m, line, r["alternate_names"], "alternate_names"),
                former_names=_list(m, line, r["former_names"], "former_names"),
                valid_from=valid_from,
                valid_to=valid_to,
                successor_codes=successors,
            )
        )
    return out


def validate_units(rows: list[UnitRow], m: Messages) -> None:
    seen: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r.level, r.code)
        if key in seen:
            m.error(r.line, f"duplicate {r.level} code {r.code} (first on line {seen[key]})")
        else:
            seen[key] = r.line
    for r in rows:
        if r.parent_level and (r.parent_level, r.parent_code) not in seen:
            m.error(r.line, f"{r.level} {r.code}: parent {r.parent_level} {r.parent_code} is not in the file")
        for s in r.successor_codes:
            if (r.level, s) not in seen:
                m.warn(r.line, f"{r.level} {r.code}: successor {s} is not in the file")
    if rows and not any(r.level == "country" for r in rows):
        m.error(1, "the file has no country row (e.g. level=country, code=IN)")


def parse_offices(text: str, name: str, m: Messages) -> list[OfficeRow]:
    levels = {lv.value for lv in GeoLevel}
    out: list[OfficeRow] = []
    seen: dict[tuple[str, str], int] = {}
    for line, r in _rows(text, POST_HEADER, name):
        if "__bad__" in r:
            m.error(line, r["__bad__"])
            continue
        if not _PIN.match(r["pin"]):
            m.error(line, f"bad PIN {r['pin']!r}: six digits, not starting with 0")
            continue
        office = _text(m, line, r["office_name"], "office_name", required=True)
        if office is None:
            continue
        if (r["pin"], office.casefold()) in seen:
            m.error(
                line,
                f"duplicate office {office} for PIN {r['pin']} (first on line {seen[(r['pin'], office.casefold())]})",
            )
            continue
        seen[(r["pin"], office.casefold())] = line
        otype = r["office_type"] or None
        if otype and otype not in _OFFICE_TYPES:
            m.error(line, f"office_type must be H.O., S.O. or B.O., not {otype!r}")
            otype = None
        delivery = {"": None, "delivery": True, "yes": True, "non-delivery": False, "no": False}.get(
            r["delivery"].lower(), "bad"
        )
        if delivery == "bad":
            m.error(line, "delivery must be Delivery, Non-Delivery or empty")
            delivery = None
        units: list[tuple[str, str]] = []
        for ref in _list(m, line, r["unit_codes"], "unit_codes"):
            level, _, code = ref.partition(":")
            if level not in levels or not _code_ok(level, code):
                m.error(line, f"unit_codes entry {ref!r} must look like village:123456")
                continue
            units.append((level, code))
        out.append(
            OfficeRow(
                line=line,
                pin=r["pin"],
                office_name=office,
                office_type=otype,
                delivery=delivery if isinstance(delivery, bool) else None,
                district=_text(m, line, r["district"], "district"),
                state=_text(m, line, r["state"], "state"),
                units=units,
            )
        )
    return out


# ---------------------------------------------------------------- staging
def active_snapshot(db: Session, source: GeoSource) -> GeoSnapshot | None:
    return db.scalar(
        select(GeoSnapshot).where(
            GeoSnapshot.source == source, GeoSnapshot.status == GeoSnapshotStatus.ACTIVE
        )
    )


def _unit_key(r: UnitRow) -> str:
    return search_key(r.name_en, r.name_local, *r.alt_names, *r.former_names)


def _insert_units(db: Session, snapshot_id: uuid.UUID, rows: list[UnitRow]) -> None:
    ids: dict[tuple[str, str], uuid.UUID] = {(r.level, r.code): uuid7() for r in rows}
    ordered = sorted(rows, key=lambda r: DEPTH[r.level])
    for i in range(0, len(ordered), BATCH):
        db.execute(
            insert(GeoUnit),
            [
                {
                    "id": ids[(r.level, r.code)],
                    "snapshot_id": snapshot_id,
                    "level": r.level,
                    "code": r.code,
                    "parent_id": ids[(r.parent_level, r.parent_code)]
                    if r.parent_level and r.parent_code
                    else None,
                    "name_en": r.name_en,
                    "name_local": r.name_local,
                    "local_script": r.local_script,
                    "local_term": r.local_term,
                    "category": r.category,
                    "alt_names": r.alt_names,
                    "former_names": r.former_names,
                    "valid_from": r.valid_from,
                    "valid_to": r.valid_to,
                    "successor_codes": r.successor_codes,
                    "origin": GeoUnitOrigin.OFFICIAL.value,
                    "search_key": _unit_key(r),
                }
                for r in ordered[i : i + BATCH]
            ],
        )


def _unit_diff(db: Session, previous: GeoSnapshot | None, rows: list[UnitRow]) -> dict[str, Any]:
    if previous is None:
        return {"previous": None, "added": dict(Counter(r.level for r in rows))}
    parent = aliased(GeoUnit)
    old: dict[tuple[str, str], tuple[str, str | None, str | None]] = {}
    for o_level, o_code, o_name, o_plevel, o_pcode in db.execute(
        select(GeoUnit.level, GeoUnit.code, GeoUnit.name_en, parent.level, parent.code)
        .outerjoin(parent, parent.id == GeoUnit.parent_id)
        .where(GeoUnit.snapshot_id == previous.id)
    ):
        old[(str(o_level), o_code)] = (o_name, str(o_plevel) if o_plevel else None, o_pcode)
    added: Counter[str] = Counter()
    renamed: Counter[str] = Counter()
    moved: Counter[str] = Counter()
    samples: dict[str, list[str]] = {"added": [], "retired": [], "renamed": [], "moved": []}

    def sample(kind: str, text: str) -> None:
        if len(samples[kind]) < SAMPLES:
            samples[kind].append(text)

    for r in rows:
        before = old.pop((r.level, r.code), None)
        if before is None:
            added[r.level] += 1
            sample("added", f"{r.level} {r.code} {r.name_en}")
            continue
        name, plevel, pcode = before
        if name != r.name_en:
            renamed[r.level] += 1
            sample("renamed", f"{r.level} {r.code}: {name} → {r.name_en}")
        if (plevel, pcode) != (r.parent_level, r.parent_code):
            moved[r.level] += 1
            sample("moved", f"{r.level} {r.code}: {plevel} {pcode} → {r.parent_level} {r.parent_code}")
    retired: Counter[str] = Counter()
    for (r_level, r_code), (r_name, _, _) in old.items():
        retired[r_level] += 1
        sample("retired", f"{r_level} {r_code} {r_name}")
    return {
        "previous": previous.label,
        "added": dict(added),
        "retired": dict(retired),
        "renamed": dict(renamed),
        "moved": dict(moved),
        "samples": samples,
    }


def _insert_offices(db: Session, snapshot_id: uuid.UUID, rows: list[OfficeRow], m: Messages) -> None:
    lgd = active_snapshot(db, GeoSource.LGD)
    known: set[tuple[str, str]] = set()
    if lgd is not None:
        known = {
            (str(lv), c)
            for lv, c in db.execute(select(GeoUnit.level, GeoUnit.code).where(GeoUnit.snapshot_id == lgd.id))
        }
    offices = []
    links = []
    for r in rows:
        oid = uuid7()
        offices.append(
            {
                "id": oid,
                "snapshot_id": snapshot_id,
                "pin": r.pin,
                "office_name": r.office_name,
                "office_type": r.office_type,
                "delivery": r.delivery,
                "district_name": r.district,
                "state_name": r.state,
            }
        )
        for level, code in dict.fromkeys(r.units):
            if (level, code) not in known:
                m.warn(r.line, f"{level} {code} is not in the active LGD snapshot")
            links.append({"id": uuid7(), "office_id": oid, "unit_level": level, "unit_code": code})
    for i in range(0, len(offices), BATCH):
        db.execute(insert(GeoPinOffice), offices[i : i + BATCH])
    for i in range(0, len(links), BATCH):
        db.execute(insert(GeoPinUnit), links[i : i + BATCH])


def _office_diff(db: Session, previous: GeoSnapshot | None, rows: list[OfficeRow]) -> dict[str, Any]:
    if previous is None:
        return {"previous": None, "added": {"office": len(rows)}}
    old = {
        (pin, name.casefold())
        for pin, name in db.execute(
            select(GeoPinOffice.pin, GeoPinOffice.office_name).where(GeoPinOffice.snapshot_id == previous.id)
        )
    }
    new = {(r.pin, r.office_name.casefold()) for r in rows}
    return {
        "previous": previous.label,
        "added": {"office": len(new - old)},
        "retired": {"office": len(old - new)},
        "samples": {
            "added": [f"{p} {n}" for p, n in sorted(new - old)[:SAMPLES]],
            "retired": [f"{p} {n}" for p, n in sorted(old - new)[:SAMPLES]],
        },
    }


def stage(
    db: Session,
    *,
    source: GeoSource,
    label: str,
    path: Path,
    licence: str,
    attribution: str,
    source_url: str | None = None,
    downloaded_on: dt.date | None = None,
    staged_by: str | None = None,
) -> GeoSnapshot:
    """Parse, validate and stage one snapshot; commits and returns it (status validated or failed)."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$", label):
        raise GeoImportError("label: letters, digits, dot, dash or underscore (e.g. 2026-10)")
    if db.scalar(select(GeoSnapshot.id).where(GeoSnapshot.source == source, GeoSnapshot.label == label)):
        raise GeoImportError(f"a {source.value} snapshot labelled {label} already exists")
    if source_url and not re.match(r"^https?://[^\s<>\"']+$", source_url):
        raise GeoImportError("source_url must start with https:// or http://")
    data, text = read_file(path)
    m = Messages()
    snap = GeoSnapshot(
        source=source,
        label=label,
        status=GeoSnapshotStatus.STAGED,
        source_url=source_url,
        downloaded_on=downloaded_on,
        licence=licence[:200],
        attribution=attribution,
        files=[{"name": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}],
        staged_by=staged_by,
    )
    db.add(snap)
    db.flush()
    previous = active_snapshot(db, source)
    counts: dict[str, int]
    diff: dict[str, Any] | None = None
    if source == GeoSource.LGD:
        units = parse_units(text, path.name, m)
        validate_units(units, m)
        counts = dict(Counter(r.level for r in units))
        snap.files = [{**snap.files[0], "rows": len(units)}]
        if not m.error_count:
            _insert_units(db, snap.id, units)
            diff = _unit_diff(db, previous, units)
    else:
        offices = parse_offices(text, path.name, m)
        counts = {
            "office": len(offices),
            "pin": len({o.pin for o in offices}),
            "link": sum(len(o.units) for o in offices),
        }
        snap.files = [{**snap.files[0], "rows": len(offices)}]
        if not m.error_count:
            _insert_offices(db, snap.id, offices, m)
            diff = _office_diff(db, previous, offices)
    snap.report = {
        "counts": counts,
        "error_count": m.error_count,
        "errors": m.errors,
        "warning_count": m.warning_count,
        "warnings": m.warnings,
        "diff": diff,
    }
    snap.status = GeoSnapshotStatus.FAILED if m.error_count else GeoSnapshotStatus.VALIDATED
    db.commit()
    return snap
