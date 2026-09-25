"""Deterministic, versioned field extractors (ADR-0009 §2).

Each extractor scans OCR lines for known labels (English + common Hindi forms) and parses the value
that follows. Several labels may share one line ("Sex: Male  Date of Birth: 12/03/1985"): every
label occurrence is located first and a value runs up to the next label. A label alone at the end
of a line takes its value from the next line when that line carries no label.

Output is a list of *drafts* — proposals only. Nothing here touches the database.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from app.core.dates import TimeSource
from app.models.enums import PROPERTY_CATEGORIES, DocumentCategory
from app.modules.astrology import vocab
from app.modules.extraction import fields as F
from app.modules.extraction.masking import mask_aadhaar, mask_value
from app.modules.extraction.ocr import OcrResult

_L = r"A-Za-zऀ-ॿ"
_APOS = "['’`]?"
_SEP = re.compile(r"^[\s:：\-–—=|.)(]*")
_VALUE_END = " \t:;,|-–—"


@dataclass
class Draft:
    field: str
    label: str
    value: Any
    display: str
    confidence: float
    location: dict[str, Any]


@dataclass
class _Hit:
    field: str
    start: int
    end: int


@dataclass
class _Found:
    field: str
    raw: str
    page: int
    line_no: int
    line_confidence: float
    line_text: str


@dataclass
class Rule:
    field: str
    patterns: list[str]
    multiple: bool = False
    compiled: list[re.Pattern[str]] = dc_field(default_factory=list)

    def __post_init__(self) -> None:
        self.compiled = [re.compile(rf"(?<![{_L}])(?:{p})(?![{_L}])", re.IGNORECASE) for p in self.patterns]


def _hits(text: str, rules: list[Rule]) -> list[_Hit]:
    cands: list[_Hit] = []
    for rule in rules:
        for pat in rule.compiled:
            for m in pat.finditer(text):
                if m.end() > m.start():
                    cands.append(_Hit(rule.field, m.start(), m.end()))
    # earliest first; at the same start the longest label wins ("Date of Registration" over "Date")
    cands.sort(key=lambda h: (h.start, -(h.end - h.start)))
    chosen: list[_Hit] = []
    for h in cands:
        if chosen and h.start < chosen[-1].end:
            continue
        chosen.append(h)
    return chosen


def scan(result: OcrResult, rules: list[Rule]) -> list[_Found]:
    found: list[_Found] = []
    for page in result.pages:
        lines = page.lines
        per_line = [_hits(ln.text, rules) for ln in lines]
        for idx, ln in enumerate(lines):
            hits = per_line[idx]
            for j, h in enumerate(hits):
                stop = hits[j + 1].start if j + 1 < len(hits) else len(ln.text)
                rest = ln.text[h.end : stop]
                rest = _SEP.sub("", rest).strip(_VALUE_END)
                src_line, src_conf = ln, ln.confidence
                if not rest and j == len(hits) - 1 and idx + 1 < len(lines) and not per_line[idx + 1]:
                    nxt = lines[idx + 1]
                    rest = nxt.text.strip(_VALUE_END)
                    src_line, src_conf = nxt, min(ln.confidence, nxt.confidence)
                if rest:
                    found.append(_Found(h.field, rest, page.page, src_line.line_no, src_conf, src_line.text))
    return found


class Extractor:
    name: str = "base"
    version: str = "0"
    rules: list[Rule] = []

    def parse(self, fld: str, raw: str) -> tuple[Any, float] | None:
        """Parse ``raw`` for ``fld``; returns (value, parse confidence factor) or None."""
        raise NotImplementedError

    def supplementary(self, result: OcrResult) -> list[Draft]:
        return []

    def extract(self, result: OcrResult) -> list[Draft]:
        drafts: list[Draft] = []
        seen: set[tuple[str, str]] = set()
        single_done: set[str] = set()
        multiple = {r.field for r in self.rules if r.multiple}
        for f in scan(result, self.rules):
            if f.field in single_done:
                continue
            parsed = self.parse(f.field, mask_aadhaar(f.raw))
            if parsed is None:
                continue
            value, factor = parsed
            value = mask_value(value)
            key = (f.field, repr(value))
            if key in seen:
                continue
            seen.add(key)
            if f.field not in multiple:
                single_done.add(f.field)
            drafts.append(
                Draft(
                    field=f.field,
                    label=F.FIELD_SPECS[f.field].label,
                    value=value,
                    display=mask_aadhaar(F.display(f.field, value)),
                    confidence=round(max(0.0, min(1.0, f.line_confidence * factor)), 3),
                    location={"page": f.page, "line": f.line_no},
                )
            )
        present = {d.field for d in drafts}
        drafts.extend(d for d in self.supplementary(result) if d.field not in present)
        return drafts


def _generic_parse(kind: str, raw: str, time_source: TimeSource) -> tuple[Any, float] | None:
    if kind == "date":
        d = F.parse_date(raw)
        return (d, 1.0 if d.get("precision") == "exact" else 0.8) if d else None
    if kind == "time":
        tm = F.parse_time(raw, time_source)
        return (tm, 1.0) if tm else None
    if kind == "sex":
        s = F.parse_sex(raw)
        return (s, 0.95) if s else None
    if kind == "name":
        n = F.clean_name(raw)
        return (n, 0.9) if n else None
    if kind == "identifier":
        i = F.clean_identifier(raw)
        return (i, 0.9) if i else None
    if kind == "area":
        a = F.parse_area(raw)
        return (a, 0.9 if a and a.get("unit") else 0.6) if a else None
    txt = F.clean_text(raw)
    return (txt, 0.85) if txt else None


# ---------------------------------------------------------------- birth certificate
_NAME_SEP = r"(?=\s*[:：\-–—])"


class BirthCertificateExtractor(Extractor):
    name = "birth_certificate_rules"
    version = "1.0.0"
    rules = [
        Rule(
            "name",
            [
                r"name\s+of\s+(?:the\s+)?(?:child|new\s*born|baby|registrant)",
                rf"child{_APOS}s?\s+name",
                r"बच्चे\s+का\s+नाम",
                r"शिशु\s+का\s+नाम",
                r"बालक\s*/\s*बालिका\s+का\s+नाम",
                rf"name{_NAME_SEP}",
                rf"नाम{_NAME_SEP}",
            ],
        ),
        Rule(
            "date_of_birth",
            [
                r"date\s+of\s+birth",
                r"birth\s+date",
                r"d\.?\s?o\.?\s?b\.?",
                r"जन्म\s+(?:की\s+)?(?:तिथि|तारीख|दिनांक)",
            ],
        ),
        Rule("time_of_birth", [r"time\s+of\s+birth", r"birth\s+time", r"जन्म\s+(?:का\s+)?समय"]),
        Rule("sex", [r"sex", r"gender", r"लिंग"]),
        Rule("place_of_birth", [r"place\s+of\s+birth", r"birth\s+place", r"जन्म\s+(?:का\s+)?स्थान"]),
        Rule(
            "father_name",
            [
                rf"father{_APOS}s?\s+name",
                r"name\s+of\s+(?:the\s+)?father",
                r"पिता\s+का\s+नाम",
                rf"पिता{_NAME_SEP}",
            ],
        ),
        Rule(
            "mother_name",
            [
                rf"mother{_APOS}s?\s+name",
                r"name\s+of\s+(?:the\s+)?mother",
                r"(?:माता|माँ|मां)\s+का\s+नाम",
                rf"माता{_NAME_SEP}",
            ],
        ),
        Rule(
            "registration_number",
            [
                r"registration\s+(?:no|number|num)\.?",
                r"reg(?:n|d|istration)?\.?\s*no\.?",
                r"(?:पंजीकरण|पंजीयन)\s+(?:संख्या|सं\.?|क्रमांक|नं\.?|नंबर)",
            ],
        ),
        Rule(
            "registration_date",
            [
                r"date\s+of\s+registration",
                r"registration\s+date",
                r"(?:पंजीकरण|पंजीयन)\s+(?:की\s+)?(?:तिथि|दिनांक|तारीख)",
            ],
        ),
        Rule(
            "issuing_authority",
            [
                r"issuing\s+authority",
                r"issued\s+by",
                r"registrar(?:\s+of\s+births?(?:\s+(?:&|and)\s+deaths?)?)?",
                r"जारीकर्ता(?:\s+प्राधिकारी)?",
                r"रजिस्ट्रार",
                r"निबंधक",
            ],
        ),
    ]

    _KINDS = {
        "name": "name",
        "date_of_birth": "date",
        "time_of_birth": "time",
        "sex": "sex",
        "place_of_birth": "text",
        "father_name": "name",
        "mother_name": "name",
        "registration_number": "identifier",
        "registration_date": "date",
        "issuing_authority": "text",
    }

    def parse(self, fld: str, raw: str) -> tuple[Any, float] | None:
        return _generic_parse(self._KINDS[fld], raw, TimeSource.BIRTH_CERTIFICATE)


# ---------------------------------------------------------------- kundli
_PADA_IN_VALUE = re.compile(r"(?<![0-9])([1-4])(?![0-9])")
_PAKSHA_PHRASE = re.compile(r"(shukla|sukla|krishna|krushna|शुक्ल|कृष्ण)\s*(?:paksha?|पक्ष)", re.IGNORECASE)


class KundliExtractor(Extractor):
    name = "kundli_rules"
    version = "1.0.0"
    rules = [
        Rule(
            "chart_birth_date",
            [
                r"date\s+of\s+birth",
                r"birth\s+date",
                r"d\.?\s?o\.?\s?b\.?",
                r"जन्म\s+(?:की\s+)?(?:तारीख|दिनांक|तिथि)",
                rf"date{_NAME_SEP}",
                rf"दिनांक{_NAME_SEP}",
            ],
        ),
        Rule(
            "chart_birth_time",
            [
                r"time\s+of\s+birth",
                r"birth\s+time",
                r"janma\s+samay",
                r"जन्म\s+(?:का\s+)?समय",
                rf"time{_NAME_SEP}",
                rf"समय{_NAME_SEP}",
            ],
        ),
        Rule(
            "chart_birth_place",
            [
                r"place\s+of\s+birth",
                r"birth\s+place",
                r"janma\s+sthan",
                r"जन्म\s+(?:का\s+)?स्थान",
                rf"place{_NAME_SEP}",
                rf"स्थान{_NAME_SEP}",
            ],
        ),
        Rule(
            "nakshatra",
            [
                r"(?:janma\s+)?naks?h?atra(?:m)?",
                r"nakshtra",
                r"birth\s+star",
                rf"star{_NAME_SEP}",
                r"(?:जन्म\s+)?नक्षत्र",
            ],
        ),
        Rule("nakshatra_pada", [r"pada", r"charana?", r"चरण", rf"पद{_NAME_SEP}"]),
        Rule(
            "rashi",
            [
                r"(?:janma\s+|chandra\s+|moon\s+)?r(?:aa|a)sh?i",
                r"moon\s+sign",
                r"(?:जन्म\s+|चन्द्र\s+|चंद्र\s+)?राशि",
            ],
        ),
        Rule("lagna", [r"lagna(?:m)?", r"ascendant", r"लग्न"]),
        Rule("tithi", [r"tithi", r"तिथि"]),
        # "Shukla Paksha Ekadashi" is a tithi value, not a paksha label (handled in extra()).
        Rule(
            "paksha",
            [
                r"(?<!shukla )(?<!sukla )(?<!krishna )(?<!krushna )paksha?",
                r"(?<!शुक्ल )(?<!कृष्ण )पक्ष",
            ],
        ),
        Rule("ayanamsha", [r"ayanam?sh?a", r"अयनांश"]),
    ]

    def parse(self, fld: str, raw: str) -> tuple[Any, float] | None:
        if fld == "chart_birth_date":
            return _generic_parse("date", raw, TimeSource.KUNDLI)
        if fld == "chart_birth_time":
            return _generic_parse("time", raw, TimeSource.KUNDLI)
        if fld == "chart_birth_place":
            return _generic_parse("text", raw, TimeSource.KUNDLI)
        finder: Callable[[str], str | None] | None = {
            "nakshatra": vocab.find_nakshatra,
            "rashi": vocab.find_rashi,
            "lagna": vocab.find_rashi,
            "tithi": vocab.find_tithi,
            "paksha": vocab.find_paksha,
            "ayanamsha": vocab.find_ayanamsha,
        }.get(fld)
        if finder is not None:
            v = finder(raw)
            return (v, 0.95) if v else None
        if fld == "nakshatra_pada":
            m = re.match(r"\s*([1-4१-४])(?![0-9])", raw)
            return (int(F.ascii_digits(m[1])), 0.9) if m else None
        return None

    def supplementary(self, result: OcrResult) -> list[Draft]:
        """Pada printed right after the nakshatra ("Rohini - 2", "Rohini (2)") and paksha phrases
        inside other lines ("Shukla Paksha Ekadashi")."""
        out: list[Draft] = []
        for f in scan(result, self.rules):
            if f.field != "nakshatra" or not vocab.find_nakshatra(f.raw):
                continue
            m = _PADA_IN_VALUE.search(F.ascii_digits(f.raw))
            if m:
                pada = int(m[1])
                out.append(
                    Draft(
                        "nakshatra_pada",
                        F.FIELD_SPECS["nakshatra_pada"].label,
                        pada,
                        str(pada),
                        round(f.line_confidence * 0.85, 3),
                        {"page": f.page, "line": f.line_no},
                    )
                )
                break
        for page in result.pages:
            for ln in page.lines:
                pm = _PAKSHA_PHRASE.search(ln.text)
                p = vocab.find_paksha(pm[1]) if pm else None
                if p:
                    out.append(
                        Draft(
                            "paksha",
                            F.FIELD_SPECS["paksha"].label,
                            p,
                            p,
                            round(ln.confidence * 0.9, 3),
                            {"page": page.page, "line": ln.line_no},
                        )
                    )
                    return out
        return out


# ---------------------------------------------------------------- land records
_NO = r"(?:\s*(?:no|number|sankhya|num)\.?)"
_HNO = r"(?:\s*(?:संख्या|सं\.?|सं०|नं\.?|नंबर|क्रमांक))"


class LandRecordExtractor(Extractor):
    name = "land_record_rules"
    version = "1.0.0"
    rules = [
        Rule(
            "khasra_or_gata_number",
            [rf"khasra{_NO}?", rf"gata{_NO}?", rf"खसरा{_HNO}?", rf"गाटा{_HNO}?"],
        ),
        Rule("khata_number", [rf"khata{_NO}", rf"khata{_NAME_SEP}", rf"खाता{_HNO}", rf"खाता{_NAME_SEP}"]),
        Rule("khatauni_number", [rf"khatauni{_NO}?", rf"खतौनी{_HNO}?"]),
        Rule("survey_number", [rf"survey{_NO}", r"sy\.?\s*no\.?", rf"सर्वे{_HNO}"]),
        Rule("patta_number", [rf"patta{_NO}?", rf"पट्टा{_HNO}?"]),
        Rule("village", [r"village", r"mauza", r"mouza", r"ग्राम", r"गांव", r"गाँव", r"मौजा"]),
        Rule("tehsil_taluk", [r"tehsil", r"tahsil", r"taluka?", r"तहसील"]),
        Rule("district", [r"district", r"zila", r"जिला", r"ज़िला", r"जनपद"]),
        Rule("area", [r"area", r"rakba", r"extent", r"रकबा", r"क्षेत्रफल"]),
        Rule(
            "holder_name",
            [
                r"name\s+of\s+(?:the\s+)?(?:owner|holder|khatedar|tenure[\s-]*holder|pattadar|occupant|bhumidhar)",
                rf"(?:owner|holder|khatedar|pattadar|bhumidhar|occupant){_APOS}s?(?:\s+name)?",
                r"खातेदार(?:\s+का\s+नाम)?",
                r"भूमिधर(?:\s+का\s+नाम)?",
                r"(?:स्वामी|धारक)(?:\s+का\s+नाम)?",
            ],
            multiple=True,
        ),
        Rule(
            "holder_relative_name",
            [
                rf"father{_APOS}s?\s*/\s*husband{_APOS}s?\s+name",
                rf"(?:father|husband|spouse){_APOS}s?\s+name",
                r"[sdw]\s*/\s*o",
                r"पिता\s*/\s*पति\s+का\s+नाम",
                r"(?:पिता|पति)\s+का\s+नाम",
            ],
            multiple=True,
        ),
        Rule(
            "mutation_number",
            [
                rf"mutation{_NO}",
                rf"dakhil[\s-]*kharij{_NO}?",
                rf"दाखिल[\s-]*खारिज{_HNO}?",
                rf"नामांतरण{_HNO}",
            ],
        ),
        Rule(
            "mutation_date",
            [r"date\s+of\s+mutation", r"mutation\s+date", r"नामांतरण\s+(?:की\s+)?(?:तिथि|दिनांक)"],
        ),
        Rule(
            "deed_registration_number",
            [
                r"registration\s+(?:no|number)\.?",
                r"regd?\.?\s*no\.?",
                r"document\s+no\.?",
                r"(?:पंजीकरण|पंजीयन)\s+(?:संख्या|सं\.?|क्रमांक|नं\.?)",
            ],
        ),
        Rule(
            "deed_registration_date",
            [
                r"date\s+of\s+registration",
                r"registration\s+date",
                r"(?:पंजीकरण|पंजीयन)\s+(?:की\s+)?(?:तिथि|दिनांक)",
            ],
        ),
    ]

    def parse(self, fld: str, raw: str) -> tuple[Any, float] | None:
        return _generic_parse(F.FIELD_SPECS[fld].kind, raw, TimeSource.UNKNOWN)


BIRTH_CERTIFICATE = BirthCertificateExtractor()
KUNDLI = KundliExtractor()
LAND_RECORD = LandRecordExtractor()

EXTRACTORS: dict[str, Extractor] = {e.name: e for e in (BIRTH_CERTIFICATE, KUNDLI, LAND_RECORD)}


def extractor_for(category: DocumentCategory | str) -> Extractor | None:
    cat = DocumentCategory(category)
    if cat == DocumentCategory.BIRTH_CERTIFICATE:
        return BIRTH_CERTIFICATE
    if cat == DocumentCategory.KUNDLI:
        return KUNDLI
    if cat in PROPERTY_CATEGORIES and cat != DocumentCategory.CADASTRAL_MAP:
        return LAND_RECORD
    return None
