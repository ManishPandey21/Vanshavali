"""Value parsing and validation for extracted fields.

Parsers are deterministic and conservative: a date is only ``exact`` when day, month and year are
all present; otherwise the precision says what is missing (no invented day or month, ADR-0003).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from app.core.dates import GenealogicalDate, GenealogicalTime, TimePrecision, TimeSource
from app.core.errors import Unprocessable
from app.models.enums import SexAtBirth
from app.modules.astrology import vocab

_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    "जनवरी": 1, "फरवरी": 2, "फ़रवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
    "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "अक्तूबर": 10, "नवंबर": 11, "नवम्बर": 11,
    "दिसंबर": 12, "दिसम्बर": 12,
}  # fmt: skip

_MONTH_ALT = "|".join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))


def ascii_digits(text: str) -> str:
    return text.translate(_DEVANAGARI_DIGITS)


def _valid(y: int, m: int, d: int) -> bool:
    try:
        dt.date(y, m, d)
        return 1000 <= y <= 2200
    except ValueError:
        return False


def parse_date(text: str) -> dict[str, Any] | None:
    """Parse a civil (Gregorian) date as printed on Indian documents (day-first)."""
    raw = ascii_digits(text).strip()
    t = raw.lower()
    original = raw[:200]
    # yyyy-mm-dd
    m = re.search(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", t)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        if _valid(y, mo, d):
            return _date(y, mo, d, original)
    # dd/mm/yyyy (Indian day-first convention)
    m = re.search(r"(?<!\d)(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})(?!\d)", t)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if _valid(y, mo, d):
            return _date(y, mo, d, original)
    # 12 March 1985 / 12-Mar-1985 / 12 मार्च 1985
    m = re.search(
        rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s\-/.,]*({_MONTH_ALT})[a-z]*[\s\-/.,]*(\d{{4}})(?!\d)", t
    )
    if m:
        d, mo, y = int(m[1]), MONTHS[m[2]], int(m[3])
        if _valid(y, mo, d):
            return _date(y, mo, d, original)
    # March 12, 1985
    m = re.search(rf"({_MONTH_ALT})[a-z]*[\s\-/.,]*(\d{{1,2}})(?:st|nd|rd|th)?[\s,]+(\d{{4}})(?!\d)", t)
    if m:
        mo, d, y = MONTHS[m[1]], int(m[2]), int(m[3])
        if _valid(y, mo, d):
            return _date(y, mo, d, original)
    # March 1985 → month known, day not
    m = re.search(rf"({_MONTH_ALT})[a-z]*[\s\-/.,]*(\d{{4}})(?!\d)", t)
    if m:
        y = int(m[2])
        if 1000 <= y <= 2200:
            return GenealogicalDate(
                precision="day_unknown", year=y, month=MONTHS[m[1]], original_text=original
            ).model_dump(  # type: ignore[arg-type]
                mode="json", exclude_none=True
            )
    return None


def _date(y: int, mo: int, d: int, original: str) -> dict[str, Any]:
    return GenealogicalDate(precision="exact", year=y, month=mo, day=d, original_text=original).model_dump(  # type: ignore[arg-type]
        mode="json", exclude_none=True
    )


def parse_time(text: str, source: TimeSource) -> dict[str, Any] | None:
    raw = ascii_digits(text).strip()
    t = raw.lower()
    m = re.search(
        r"(?<!\d)(\d{1,2})\s*[:.hH]\s*(\d{2})(?:\s*[:.]\s*(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?|hrs|hours|बजे|प्रातः|सुबह|शाम|रात्रि|रात|दोपहर)?",
        t,
    )
    if not m:
        return None
    h, mi = int(m[1]), int(m[2])
    sec = int(m[3]) if m[3] else 0
    suffix = (m[4] or "").replace(".", "").replace(" ", "")
    if suffix in ("pm", "शाम", "रात", "रात्रि", "दोपहर") and h < 12:
        h += 12
    elif suffix in ("am", "प्रातः", "सुबह") and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= mi <= 59 and 0 <= sec <= 59):
        return None
    return GenealogicalTime(
        value=dt.time(h, mi, sec),
        precision=TimePrecision.DOCUMENT_RECORDED,
        source=source,
        original_text=raw[:200],
    ).model_dump(mode="json", exclude_none=True)


_SEX_WORDS = {
    SexAtBirth.MALE: ("male", "m", "boy", "पुरुष", "पु", "लड़का", "लडका", "बालक", "नर"),
    SexAtBirth.FEMALE: ("female", "f", "girl", "स्त्री", "महिला", "लड़की", "लडकी", "बालिका", "मादा"),
    SexAtBirth.INTERSEX: ("intersex", "transgender", "other", "अन्य"),
}


def parse_sex(text: str) -> str | None:
    t = re.sub(r"[^\wऀ-ॿ]+", " ", text.lower()).strip()
    tokens = t.split()
    if not tokens:
        return None
    for sex, words in _SEX_WORDS.items():
        if tokens[0] in words:
            return sex.value
    return None


def clean_text(text: str, max_len: int = 300) -> str | None:
    t = re.sub(r"\s+", " ", text).strip(" \t:;,-–—|_.")
    return t[:max_len] or None


def clean_name(text: str) -> str | None:
    # drop trailing labels/noise that OCR glues onto names
    t = re.sub(r"[|_*#@<>{}\[\]]+", " ", text)
    t = re.sub(r"\s+", " ", t).strip(" \t:;,-–—.")
    if not t or not re.search(r"[A-Za-zऀ-ॿ]", t):
        return None
    return t[:200]


def clean_identifier(text: str) -> str | None:
    t = ascii_digits(text).strip(" \t:;,–—|")
    m = re.match(r"[A-Za-z0-9][A-Za-z0-9/\-.() ]{0,58}", t)
    if not m:
        return None
    val = m.group(0).strip(" .-")
    if not re.search(r"\d", val):  # record numbers always carry a digit ("456/2", "B-1985-00432")
        return None
    return val


AREA_UNITS = {
    "hectare": ("hectares", "hectare", "hect", "ha", "हेक्टेयर", "हे0", "हे."),
    "acre": ("acres", "acre", "ac", "एकड़", "एकड"),
    "bigha": ("bighas", "bigha", "बीघा", "बिघा"),
    "biswa": ("biswas", "biswa", "बिस्वा"),
    "kanal": ("kanals", "kanal", "कनाल"),
    "marla": ("marlas", "marla", "मरला"),
    "guntha": ("gunthas", "guntha", "gunta", "गुंठा"),
    "cent": ("cents", "cent"),
    "square_metre": ("sq. m", "sq.m", "sq m", "sqm", "square metres", "square meters", "वर्ग मीटर"),
    "square_foot": ("sq. ft", "sq.ft", "sq ft", "sqft", "square feet", "वर्ग फुट"),
}


def parse_area(text: str) -> dict[str, Any] | None:
    t = ascii_digits(text).lower()
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(.*)", t)
    if not m:
        return None
    try:
        value = float(m[1].replace(",", "."))
    except ValueError:
        return None
    rest = m[2].strip()
    unit = None
    for canonical, words in AREA_UNITS.items():
        for w in sorted(words, key=len, reverse=True):
            if rest.startswith(w):
                unit = canonical
                break
        if unit:
            break
    return {"value": value, "unit": unit, "original_text": text.strip()[:200]}


# ---------------------------------------------------------------- field registry
@dataclass(frozen=True)
class FieldSpec:
    label: str
    kind: str  # text | name | identifier | date | time | sex | nakshatra | rashi | tithi | paksha | ayanamsha | pada | area


FIELD_SPECS: dict[str, FieldSpec] = {
    # birth certificate
    "name": FieldSpec("Name", "name"),
    "date_of_birth": FieldSpec("Date of birth", "date"),
    "time_of_birth": FieldSpec("Time of birth", "time"),
    "sex": FieldSpec("Sex", "sex"),
    "place_of_birth": FieldSpec("Place of birth", "text"),
    "father_name": FieldSpec("Father's name", "name"),
    "mother_name": FieldSpec("Mother's name", "name"),
    "registration_number": FieldSpec("Registration number", "identifier"),
    "registration_date": FieldSpec("Registration date", "date"),
    "issuing_authority": FieldSpec("Issuing authority", "text"),
    # kundli
    "chart_birth_date": FieldSpec("Birth date (chart)", "date"),
    "chart_birth_time": FieldSpec("Birth time (chart)", "time"),
    "chart_birth_place": FieldSpec("Birth place (chart)", "text"),
    "nakshatra": FieldSpec("Nakshatra", "nakshatra"),
    "nakshatra_pada": FieldSpec("Nakshatra pada", "pada"),
    "rashi": FieldSpec("Rashi", "rashi"),
    "lagna": FieldSpec("Lagna", "rashi"),
    "tithi": FieldSpec("Tithi", "tithi"),
    "paksha": FieldSpec("Paksha", "paksha"),
    "ayanamsha": FieldSpec("Ayanamsha", "ayanamsha"),
    # land records
    "khasra_or_gata_number": FieldSpec("Khasra / Gata number", "identifier"),
    "khata_number": FieldSpec("Khata number", "identifier"),
    "khatauni_number": FieldSpec("Khatauni number", "identifier"),
    "survey_number": FieldSpec("Survey number", "identifier"),
    "patta_number": FieldSpec("Patta number", "identifier"),
    "village": FieldSpec("Village", "text"),
    "tehsil_taluk": FieldSpec("Tehsil / Taluk", "text"),
    "district": FieldSpec("District", "text"),
    "area": FieldSpec("Area", "area"),
    "holder_name": FieldSpec("Owner / holder name", "name"),
    "holder_relative_name": FieldSpec("Holder's father / spouse name", "name"),
    "mutation_number": FieldSpec("Mutation number", "identifier"),
    "mutation_date": FieldSpec("Mutation date", "date"),
    "deed_registration_number": FieldSpec("Registration number", "identifier"),
    "deed_registration_date": FieldSpec("Registration date", "date"),
}


def display(field: str, value: Any) -> str:
    kind = FIELD_SPECS[field].kind if field in FIELD_SPECS else "text"
    if value is None:
        return ""
    if kind == "date" and isinstance(value, dict):
        return GenealogicalDate.model_validate(value).display()
    if kind == "time" and isinstance(value, dict):
        return str(value.get("value", ""))[:5] + (" (as recorded)" if value.get("value") else "")
    if kind == "area" and isinstance(value, dict):
        return f"{value.get('value')} {value.get('unit') or ''}".strip()
    return str(value)


def coerce(field: str, value: Any, *, time_source: TimeSource = TimeSource.UNKNOWN) -> Any:
    """Validate a reviewer-supplied value (``edit``) into the stored JSON shape. Raises 422."""
    spec = FIELD_SPECS.get(field)
    if spec is None:
        raise Unprocessable(f"Unknown extraction field '{field}'")
    kind = spec.kind
    bad = Unprocessable(f"Invalid value for {spec.label}", code="invalid_value")
    if value is None:
        raise bad
    if kind == "date":
        if isinstance(value, str):
            parsed = parse_date(value)
            if parsed is None:
                raise bad
            return parsed
        try:
            return GenealogicalDate.model_validate(value).model_dump(mode="json", exclude_none=True)
        except ValueError:
            raise bad
    if kind == "time":
        if isinstance(value, str):
            parsed = parse_time(value, time_source)
            if parsed is None:
                raise bad
            return parsed
        try:
            return GenealogicalTime.model_validate(value).model_dump(mode="json", exclude_none=True)
        except ValueError:
            raise bad
    if kind == "area":
        if isinstance(value, str):
            parsed = parse_area(value)
        elif isinstance(value, dict) and isinstance(value.get("value"), int | float):
            parsed = {"value": float(value["value"]), "unit": value.get("unit")}
        else:
            parsed = None
        if parsed is None or parsed["value"] < 0:
            raise bad
        return parsed
    if kind == "pada":
        try:
            pada = int(value)
        except (TypeError, ValueError):
            raise bad
        if not 1 <= pada <= 4:
            raise Unprocessable("Nakshatra pada must be between 1 and 4", code="invalid_value")
        return pada
    if not isinstance(value, str):
        raise bad
    if kind == "sex":
        sex = parse_sex(value) or (value if value in {s.value for s in SexAtBirth} else None)
        if sex is None:
            raise bad
        return sex
    vocab_fn = {
        "nakshatra": vocab.canonical_nakshatra,
        "rashi": vocab.canonical_rashi,
        "tithi": vocab.canonical_tithi,
        "paksha": vocab.canonical_paksha,
        "ayanamsha": vocab.canonical_ayanamsha,
    }.get(kind)
    if vocab_fn is not None:
        canonical = vocab_fn(value)
        if canonical is None:
            raise Unprocessable(f"'{value}' is not a recognised {spec.label.lower()}", code="invalid_value")
        return canonical
    if kind == "name":
        cleaned = clean_name(value)
    elif kind == "identifier":
        cleaned = clean_text(value, 60)
    else:
        cleaned = clean_text(value, 300)
    if cleaned is None:
        raise bad
    return cleaned
