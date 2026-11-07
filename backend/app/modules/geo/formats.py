"""Readers for the published LGD and India Post CSV layouts (ADR-0019 §3).

Headers are matched tolerantly: case, spacing and punctuation are ignored ("State Name (In English)"
and "statenameinenglish" are the same column), and the header row may follow a few title lines. A
file whose columns do not match any known layout is refused: nothing is guessed.

Every value is validated as plain text before it can reach the database: NFC-normalised,
whitespace collapsed, control and bidirectional-override characters refused (the zero-width
joiners that Indic scripts need are allowed), and length-limited. Codes must be digits.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from app.core.textnorm import SCRIPT_CODES, detect_script
from app.models.enums import GeoLevel

MAX_NAME = 200
MAX_CODE = 20
HEADER_SCAN_LINES = 10
_CODE = re.compile(r"^\d{1,20}$")
_PIN = re.compile(r"^[1-9]\d{5}$")
_ALLOWED_FORMAT_CHARS = {"‌", "‍"}  # ZWNJ, ZWJ: part of Indic spelling

# canonical field -> accepted normalised header spellings
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "state_code": ("statecode", "statelgdcode", "stcode"),
    "state_name": ("statenameinenglish", "statename", "statenameenglish"),
    "state_name_local": ("statenameinlocallanguage", "statenameinlocal", "statenamelocal"),
    "district_code": ("districtcode", "districtlgdcode"),
    "district_name": ("districtnameinenglish", "districtname", "districtnameenglish"),
    "district_name_local": ("districtnameinlocallanguage", "districtnameinlocal", "districtnamelocal"),
    "sub_district_code": ("subdistrictcode", "subdistrictlgdcode"),
    "sub_district_name": ("subdistrictnameinenglish", "subdistrictname", "subdistrictnameenglish"),
    "sub_district_name_local": (
        "subdistrictnameinlocallanguage",
        "subdistrictnameinlocal",
        "subdistrictnamelocal",
    ),
    "village_code": ("villagecode", "villagelgdcode"),
    "village_name": ("villagenameinenglish", "villagename", "villagenameenglish"),
    "village_name_local": ("villagenameinlocallanguage", "villagenameinlocal", "villagenamelocal"),
    "ulb_code": ("localbodycode", "localbodylgdcode", "ulbcode"),
    "ulb_name": ("localbodynameinenglish", "localbodyname", "ulbname", "localbodynameenglish"),
    "ulb_name_local": ("localbodynameinlocallanguage", "localbodynameinlocal", "localbodynamelocal"),
    "ulb_type": ("localbodytypename", "localbodytype", "ulbtype"),
}

_PIN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "pincode": ("pincode", "pin"),
    "office_name": ("officename", "postofficename", "officenamebo"),
    "office_type": ("officetype",),
    "delivery": ("delivery", "deliverystatus"),
    "division": ("divisionname", "division"),
    "region": ("regionname", "region"),
    "circle": ("circlename", "circle"),
    "district": ("district", "districtname"),
    "state": ("statename", "state"),
    "taluk": ("taluk", "talukname", "subdistrict"),
}

# (level, its own code / name / local-name / category fields)
_OWN: dict[GeoLevel, tuple[str, str, str, str | None]] = {
    GeoLevel.STATE: ("state_code", "state_name", "state_name_local", None),
    GeoLevel.DISTRICT: ("district_code", "district_name", "district_name_local", None),
    GeoLevel.SUB_DISTRICT: ("sub_district_code", "sub_district_name", "sub_district_name_local", None),
    GeoLevel.VILLAGE: ("village_code", "village_name", "village_name_local", None),
    GeoLevel.URBAN_BODY: ("ulb_code", "ulb_name", "ulb_name_local", "ulb_type"),
}
_REQUIRED: dict[GeoLevel, tuple[str, ...]] = {
    GeoLevel.STATE: ("state_code", "state_name"),
    GeoLevel.DISTRICT: ("state_code", "district_code", "district_name"),
    GeoLevel.SUB_DISTRICT: ("state_code", "district_code", "sub_district_code", "sub_district_name"),
    GeoLevel.VILLAGE: ("state_code", "district_code", "sub_district_code", "village_code", "village_name"),
    GeoLevel.URBAN_BODY: ("state_code", "ulb_code", "ulb_name"),
}
_PIN_REQUIRED = ("pincode", "office_name", "district", "state")


class FormatError(ValueError):
    """The file cannot be imported. ``problems`` lists (line, message), at most 50."""

    def __init__(self, message: str, problems: list[tuple[int, str]] | None = None):
        super().__init__(message)
        self.problems = problems or []


@dataclass(frozen=True)
class UnitRow:
    line: int
    level: GeoLevel
    code: str
    name_en: str
    name_local: str | None
    local_script: str | None
    parent_level: GeoLevel | None
    parent_code: str | None
    category: str | None = None


@dataclass(frozen=True)
class PinRow:
    line: int
    pincode: str
    office_name: str
    office_type: str | None
    delivery: bool | None
    division: str | None
    region: str | None
    circle: str | None
    district: str | None
    state: str | None
    taluk: str | None


@dataclass
class ParsedFile:
    kind: str  # a GeoLevel value, or "pincode"
    units: list[UnitRow] = field(default_factory=list)
    pins: list[PinRow] = field(default_factory=list)


def norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", h or "").lower())


def clean_text(value: str | None, *, what: str, required: bool = False, limit: int = MAX_NAME) -> str | None:
    """Validated plain text, or None for an empty optional value. Raises ValueError with a reason."""
    v = unicodedata.normalize("NFC", value or "")
    for ch in v:
        cat = unicodedata.category(ch)
        if (cat == "Cc" and ch not in "\t\n\r") or (cat == "Cf" and ch not in _ALLOWED_FORMAT_CHARS):
            raise ValueError(f"{what} contains a control character (U+{ord(ch):04X})")
    v = re.sub(r"\s+", " ", v).strip()
    if not v:
        if required:
            raise ValueError(f"{what} is empty")
        return None
    if len(v) > limit:
        raise ValueError(f"{what} is longer than {limit} characters")
    return v


def clean_required(value: str | None, *, what: str, limit: int = MAX_NAME) -> str:
    v = clean_text(value, what=what, limit=limit)
    if v is None:
        raise ValueError(f"{what} is empty")
    return v


def clean_code(value: str | None, *, what: str) -> str:
    v = (value or "").strip()
    if not _CODE.match(v):
        raise ValueError(f"{what} must be 1-{MAX_CODE} digits, got {v[:30]!r}")
    return v.lstrip("0") or "0"


def script_code(text: str | None) -> str | None:
    if not text:
        return None
    s = detect_script(text)
    return SCRIPT_CODES.get(s, s) if s else None


def _match_columns(header: list[str], synonyms: dict[str, tuple[str, ...]]) -> dict[str, int]:
    normed = [norm_header(h) for h in header]
    out: dict[str, int] = {}
    for canon, spellings in synonyms.items():
        for i, h in enumerate(normed):
            if h in spellings:
                out[canon] = i
                break
    return out


def _detect(cols: dict[str, int], pin_cols: dict[str, int]) -> str | None:
    if all(c in pin_cols for c in _PIN_REQUIRED):
        return "pincode"
    for level in (
        GeoLevel.VILLAGE,
        GeoLevel.URBAN_BODY,
        GeoLevel.SUB_DISTRICT,
        GeoLevel.DISTRICT,
        GeoLevel.STATE,
    ):
        if all(c in cols for c in _REQUIRED[level]):
            return level.value
    return None


def _rows(path: Path) -> Iterator[tuple[int, list[str]]]:
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FormatError(f"{path.name}: not UTF-8 text ({exc.reason})") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        for row in reader:
            yield reader.line_num, row
    except csv.Error as exc:
        raise FormatError(f"{path.name}: malformed CSV near line {reader.line_num}: {exc}") from exc


def read_file(path: Path) -> ParsedFile:
    """Recognise the file's layout from its header row and parse every row, or raise FormatError."""
    rows = _rows(path)
    header: list[str] | None = None
    cols: dict[str, int] = {}
    pin_cols: dict[str, int] = {}
    kind: str | None = None
    seen: list[str] = []
    for line, row in rows:
        cols = _match_columns(row, _SYNONYMS)
        pin_cols = _match_columns(row, _PIN_SYNONYMS)
        kind = _detect(cols, pin_cols)
        if kind:
            header = row
            break
        seen.append(",".join(row)[:120])
        if line >= HEADER_SCAN_LINES:
            break
    if header is None or kind is None:
        raise FormatError(
            f"{path.name}: not a recognised LGD or India Post layout (no known header row in the first "
            f"{HEADER_SCAN_LINES} lines). First line: {seen[0] if seen else '(empty)'!r}"
        )
    parsed = ParsedFile(kind=kind)
    problems: list[tuple[int, str]] = []
    for line, row in rows:
        if not any(c.strip() for c in row):
            continue
        try:
            if kind == "pincode":
                parsed.pins.append(_pin_row(line, row, pin_cols))
            else:
                parsed.units.append(_unit_row(line, row, cols, GeoLevel(kind)))
        except (ValueError, IndexError) as exc:
            problems.append((line, str(exc)))
            if len(problems) >= 50:
                break
    if problems:
        raise FormatError(f"{path.name}: {len(problems)} invalid row(s)", problems)
    return parsed


def _get(row: list[str], cols: dict[str, int], key: str) -> str | None:
    i = cols.get(key)
    return row[i] if i is not None and i < len(row) else None


def _unit_row(line: int, row: list[str], cols: dict[str, int], level: GeoLevel) -> UnitRow:
    code_f, name_f, local_f, cat_f = _OWN[level]
    code = clean_code(_get(row, cols, code_f), what=code_f)
    name = clean_required(_get(row, cols, name_f), what=name_f)
    local = clean_text(_get(row, cols, local_f), what=local_f)
    category = clean_text(_get(row, cols, cat_f), what=cat_f, limit=80) if cat_f else None
    parent_level: GeoLevel | None
    parent_code: str | None
    if level == GeoLevel.STATE:
        parent_level, parent_code = None, None
    elif level == GeoLevel.DISTRICT:
        parent_level, parent_code = (
            GeoLevel.STATE,
            clean_code(_get(row, cols, "state_code"), what="state_code"),
        )
    elif level == GeoLevel.SUB_DISTRICT:
        parent_level = GeoLevel.DISTRICT
        parent_code = clean_code(_get(row, cols, "district_code"), what="district_code")
    elif level == GeoLevel.VILLAGE:
        parent_level = GeoLevel.SUB_DISTRICT
        parent_code = clean_code(_get(row, cols, "sub_district_code"), what="sub_district_code")
    else:  # urban body: its district when the file gives one, else its state
        district = (_get(row, cols, "district_code") or "").strip()
        if district:
            parent_level, parent_code = GeoLevel.DISTRICT, clean_code(district, what="district_code")
        else:
            parent_level = GeoLevel.STATE
            parent_code = clean_code(_get(row, cols, "state_code"), what="state_code")
    return UnitRow(
        line=line,
        level=level,
        code=code,
        name_en=name,
        name_local=local,
        local_script=script_code(local),
        parent_level=parent_level,
        parent_code=parent_code,
        category=category,
    )


def _pin_row(line: int, row: list[str], cols: dict[str, int]) -> PinRow:
    pin = (_get(row, cols, "pincode") or "").strip()
    if not _PIN.match(pin):
        raise ValueError(f"pincode must be six digits not starting with 0, got {pin[:20]!r}")
    office = clean_required(_get(row, cols, "office_name"), what="office_name")
    delivery_raw = (clean_text(_get(row, cols, "delivery"), what="delivery", limit=40) or "").lower()
    delivery = None if not delivery_raw else not delivery_raw.startswith("non")
    return PinRow(
        line=line,
        pincode=pin,
        office_name=office,
        office_type=clean_text(_get(row, cols, "office_type"), what="office_type", limit=20),
        delivery=delivery,
        division=clean_text(_get(row, cols, "division"), what="division", limit=120),
        region=clean_text(_get(row, cols, "region"), what="region", limit=120),
        circle=clean_text(_get(row, cols, "circle"), what="circle", limit=120),
        district=clean_text(_get(row, cols, "district"), what="district", limit=120),
        state=clean_text(_get(row, cols, "state"), what="state", limit=120),
        taluk=clean_text(_get(row, cols, "taluk"), what="taluk", limit=120),
    )


def read_successors(path: Path) -> dict[tuple[GeoLevel, str], list[str]]:
    """Operator-prepared merges and splits from LGD's change reports: level, lgd_code, successor codes.

    Columns (tolerant): ``level``, ``lgd code`` / ``old code``, ``successor codes`` / ``new codes``
    (separated by ``;`` or spaces).
    """
    out: dict[tuple[GeoLevel, str], list[str]] = {}
    syn: dict[str, tuple[str, ...]] = {
        "level": ("level", "entitytype", "unitlevel"),
        "code": ("lgdcode", "oldcode", "code"),
        "successors": ("successorcodes", "newcodes", "successors"),
    }
    rows = _rows(path)
    cols: dict[str, int] = {}
    for _line, row in rows:
        cols = _match_columns(row, syn)
        if len(cols) == 3:
            break
    else:
        raise FormatError(f"{path.name}: expected columns level, lgd_code, successor_codes")
    if len(cols) != 3:
        raise FormatError(f"{path.name}: expected columns level, lgd_code, successor_codes")
    problems: list[tuple[int, str]] = []
    for line, row in rows:
        if not any(c.strip() for c in row):
            continue
        try:
            level = GeoLevel((_get(row, cols, "level") or "").strip().lower().replace("-", "_"))
            code = clean_code(_get(row, cols, "code"), what="lgd_code")
            succ = [
                clean_code(s, what="successor code")
                for s in re.split(r"[;\s]+", _get(row, cols, "successors") or "")
                if s
            ]
            if not succ:
                raise ValueError("no successor codes")
            out[(level, code)] = succ
        except ValueError as exc:
            problems.append((line, str(exc)))
    if problems:
        raise FormatError(f"{path.name}: {len(problems)} invalid row(s)", problems)
    return out
