"""Load reference vocabularies into the database (ADR-0019).

The JSON files in ``data/`` are the source of truth; the jyotish lists are built from
``app.modules.astrology.vocab`` so validation and suggestion share one list. Loading is an idempotent
upsert by code. A term that disappears from its file is deactivated, never deleted: records may
still carry its code. Districts and sub-districts are imported from LGD (Local Government Directory)
CSV downloads instead of being typed in by hand.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.textnorm import romanize
from app.models import Vocabulary, VocabularyTerm
from app.modules.astrology import vocab as jyotish

DATA_DIR = Path(__file__).parent / "data"
JYOTISH_VERSION = "2026.10.1"


@dataclass
class LoadStats:
    vocabularies: int = 0
    created: int = 0
    updated: int = 0
    deactivated: int = 0
    skipped: list[str] = field(default_factory=list)


def search_text(label: str, labels: dict[str, str], aliases: list[str]) -> str:
    """Romanised keys of every name a term is known by, separated by `` | `` for whole-name matching."""
    keys: list[str] = []
    for part in (label, *labels.values(), *aliases):
        k = romanize(part)
        if k and k not in keys:
            keys.append(k)
    return " | ".join(keys)


# --------------------------------------------------------------------------- jyotish (from vocab.py)

_RANGES = {"hi": (0x0900, 0x097F), "ta": (0x0B80, 0x0BFF), "te": (0x0C00, 0x0C7F)}
_WESTERN = {
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
}


def _lang_of(text: str) -> str | None:
    for lang, (lo, hi) in _RANGES.items():
        if any(lo <= ord(ch) <= hi for ch in text):
            return lang
    return None


def _jyotish_term(code: str, variants: tuple[str, ...], number: int | None, **attrs: Any) -> dict[str, Any]:
    labels: dict[str, str] = {}
    aliases: list[str] = []
    for v in variants:
        lang = _lang_of(v)
        if lang and lang not in labels:
            labels[lang] = v
        elif v != code and v not in aliases:
            aliases.append(v)
    western = [a for a in aliases if a in _WESTERN]
    if western:
        attrs["western_gloss"] = western[0]
    if number is not None:
        attrs["number"] = number
    return {
        "code": code.lower().replace(" ", "_"),
        "label": code,
        "labels": labels,
        "aliases": aliases,
        "attributes": attrs,
    }


def _jyotish_docs() -> list[dict[str, Any]]:
    source = "app/modules/astrology/vocab.py (the lists used to validate and normalise astrology values)"
    base = {
        "version": JYOTISH_VERSION,
        "source": source,
        "license": "Project data (same terms as this repository)",
    }
    tithis = []
    for i, (name, variants) in enumerate(jyotish.TITHIS.items(), 1):
        if name == "Purnima":
            tithis.append(_jyotish_term(name, variants, 15, paksha="shukla"))
        elif name == "Amavasya":
            tithis.append(_jyotish_term(name, variants, 15, paksha="krishna"))
        else:
            tithis.append(_jyotish_term(name, variants, i))
    return [
        {
            **base,
            "code": "rashi",
            "name": "Rashi",
            "description": "The 12 rashis (sidereal signs). As a birth detail this is the moon sign, not the "
            "Western sun sign; the Western gloss is shown only to help recognition.",
            "terms": [_jyotish_term(n, v, i) for i, (n, v) in enumerate(jyotish.RASHIS.items(), 1)],
        },
        {
            **base,
            "code": "nakshatra",
            "name": "Nakshatra",
            "description": "The 27 nakshatras (birth stars).",
            "terms": [_jyotish_term(n, v, i) for i, (n, v) in enumerate(jyotish.NAKSHATRAS.items(), 1)],
        },
        {
            **base,
            "code": "tithi",
            "name": "Tithi",
            "description": "Lunar day. 1–14 occur in both pakshas; 15 is Purnima (Shukla) or Amavasya (Krishna).",
            "terms": tithis,
        },
        {
            **base,
            "code": "paksha",
            "name": "Paksha",
            "description": "Lunar fortnight: Shukla (Sudi, waxing) or Krishna (Badi/Vadi, waning).",
            "terms": [_jyotish_term(n, v, None) for n, v in jyotish.PAKSHAS.items()],
        },
        {
            **base,
            "code": "ayanamsha",
            "name": "Ayanamsha",
            "description": "Ayanamsha a horoscope was cast with.",
            "terms": [_jyotish_term(n, v, None) for n, v in jyotish.AYANAMSHAS.items()],
        },
    ]


# --------------------------------------------------------------------------- loading


def read_documents(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(data_dir.glob("*.json"))]
    docs += _jyotish_docs()
    codes = [d["code"] for d in docs]
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate vocabulary code")
    # parents first, so parent terms exist when children are linked
    by_code = {d["code"]: d for d in docs}
    ordered: list[dict[str, Any]] = []

    def visit(d: dict[str, Any], seen: tuple[str, ...] = ()) -> None:
        if d in ordered:
            return
        parent = d.get("parent_vocabulary")
        if parent:
            if parent in seen or parent not in by_code:
                raise ValueError(f"vocabulary {d['code']}: bad parent {parent}")
            visit(by_code[parent], (*seen, d["code"]))
        ordered.append(d)

    for d in docs:
        visit(d)
    return ordered


def _term_ids(db: Session, vocabulary_code: str) -> dict[str, Any]:
    rows = db.execute(
        select(VocabularyTerm.code, VocabularyTerm.id).where(
            VocabularyTerm.vocabulary_code == vocabulary_code
        )
    )
    return dict(rows.tuples().all())


def _upsert_vocabulary(db: Session, doc: dict[str, Any]) -> None:
    v = db.get(Vocabulary, doc["code"]) or Vocabulary(code=doc["code"])
    v.name = doc["name"]
    v.description = doc.get("description")
    v.parent_vocabulary_code = doc.get("parent_vocabulary")
    v.version = doc["version"]
    v.source = doc.get("source")
    v.license = doc.get("license")
    db.add(v)
    db.flush()


def _apply(term: VocabularyTerm, data: dict[str, Any], parent_id: Any, sort_order: int) -> bool:
    """Copy ``data`` onto ``term``; True when anything changed."""
    labels = data.get("labels") or {}
    aliases = list(data.get("aliases") or [])
    values = {
        "label": data["label"],
        "labels": labels,
        "aliases": aliases,
        "tags": list(data.get("tags") or []),
        "attributes": data.get("attributes") or {},
        "parent_id": parent_id,
        "sort_order": sort_order,
        "is_active": True,
        "search_text": search_text(data["label"], labels, aliases),
    }
    changed = False
    for k, v in values.items():
        if getattr(term, k) != v:
            setattr(term, k, v)
            changed = True
    return changed


def load_vocabularies(db: Session, data_dir: Path = DATA_DIR) -> LoadStats:
    stats = LoadStats()
    for doc in read_documents(data_dir):
        _upsert_vocabulary(db, doc)
        stats.vocabularies += 1
        parent_ids = _term_ids(db, doc["parent_vocabulary"]) if doc.get("parent_vocabulary") else {}
        existing = {
            t.code: t
            for t in db.scalars(select(VocabularyTerm).where(VocabularyTerm.vocabulary_code == doc["code"]))
        }
        seen: set[str] = set()
        for i, data in enumerate(doc["terms"]):
            parent_code = data.get("parent")
            parent_id = None
            if parent_code:
                parent_id = parent_ids.get(parent_code)
                if parent_id is None:
                    raise ValueError(f"{doc['code']}/{data['code']}: unknown parent {parent_code}")
            term = existing.get(data["code"])
            if term is None:
                term = VocabularyTerm(vocabulary_code=doc["code"], code=data["code"])
                _apply(term, data, parent_id, i)
                db.add(term)
                stats.created += 1
            elif _apply(term, data, parent_id, i):
                stats.updated += 1
            seen.add(data["code"])
        if doc.get("external_import"):
            # terms come from an external import (LGD); the file only declares the vocabulary
            continue
        for code, term in existing.items():
            if code not in seen and term.is_active:
                term.is_active = False
                stats.deactivated += 1
        db.flush()
    return stats


# --------------------------------------------------------------------------- LGD import


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _read_lgd_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    """LGD downloads may start with title lines; the header is the first row naming a code column."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    for i, row in enumerate(rows):
        normed = [_norm(c) for c in row]
        if any(n.endswith("code") for n in normed) and sum(1 for n in normed if n) >= 2:
            return normed, [r for r in rows[i + 1 :] if any(c.strip() for c in r)]
    raise ValueError(f"{path}: no header row with a code column")


def _col(headers: list[str], *, prefix: str, want: str, avoid: tuple[str, ...] = ()) -> int:
    for i, h in enumerate(headers):
        if h.startswith(prefix) and want in h and not any(a in h for a in avoid):
            return i
    raise ValueError(f"LGD CSV: no column like {prefix}…{want} in {headers}")


def _col_opt(headers: list[str], *, prefix: str, want: str, avoid: tuple[str, ...] = ()) -> int | None:
    try:
        return _col(headers, prefix=prefix, want=want, avoid=avoid)
    except ValueError:
        return None


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    return name.title() if name.isupper() else name


def _import_level(
    db: Session,
    path: Path,
    *,
    vocabulary_code: str,
    level: str,
    parent_vocabulary: str,
    parent_level: str,
    parent_key: str,
) -> LoadStats:
    """Upsert one LGD level (``district`` or ``subdistrict``) under its parent level."""
    if db.get(Vocabulary, vocabulary_code) is None:
        raise ValueError(f"vocabulary {vocabulary_code} not loaded; run load_vocabularies first")
    headers, rows = _read_lgd_csv(path)
    code_i = _col(headers, prefix=level, want="code", avoid=("census", "name"))
    name_i = _col(headers, prefix=level, want="name", avoid=("local", "code"))
    local_i = _col_opt(headers, prefix=level, want="local")
    census_i = _col_opt(headers, prefix="census2011", want="code")
    parent_i = _col(headers, prefix=parent_level, want="code", avoid=("census", "name"))

    # parents by LGD code (states carry attributes.lgd_code; districts are coded lgd:<code>)
    parent_terms = db.scalars(
        select(VocabularyTerm).where(VocabularyTerm.vocabulary_code == parent_vocabulary)
    )
    parents = {}
    for p in parent_terms:
        key = p.attributes.get(parent_key) if parent_key != "code" else p.code.removeprefix("lgd:")
        if key:
            parents[str(key)] = p.id
    existing = {
        t.code: t
        for t in db.scalars(select(VocabularyTerm).where(VocabularyTerm.vocabulary_code == vocabulary_code))
    }
    stats = LoadStats(vocabularies=1)
    for row in rows:
        lgd_code = row[code_i].strip() if code_i < len(row) else ""
        if not lgd_code.isdigit():
            continue
        parent_code = row[parent_i].strip()
        parent_id = parents.get(parent_code)
        if parent_id is None:
            stats.skipped.append(f"{lgd_code}: unknown {parent_level} code {parent_code}")
            continue
        labels = {}
        if local_i is not None and local_i < len(row) and row[local_i].strip():
            labels["native"] = " ".join(row[local_i].split())
        attrs: dict[str, Any] = {"lgd_code": lgd_code}
        if census_i is not None and census_i < len(row) and row[census_i].strip() not in ("", "0"):
            attrs["census_2011_code"] = row[census_i].strip()
        data = {"label": _clean_name(row[name_i]), "labels": labels, "aliases": [], "attributes": attrs}
        code = f"lgd:{lgd_code}"
        term = existing.get(code)
        if term is None:
            term = VocabularyTerm(vocabulary_code=vocabulary_code, code=code)
            _apply(term, data, parent_id, 0)
            db.add(term)
            existing[code] = term
            stats.created += 1
        elif _apply(term, data, parent_id, 0):
            stats.updated += 1
    db.flush()
    return stats


def import_lgd_districts(db: Session, path: Path) -> LoadStats:
    return _import_level(
        db,
        path,
        vocabulary_code="district",
        level="district",
        parent_vocabulary="state",
        parent_level="state",
        parent_key="lgd_code",
    )


def import_lgd_subdistricts(db: Session, path: Path) -> LoadStats:
    return _import_level(
        db,
        path,
        vocabulary_code="sub_district",
        level="subdistrict",
        parent_vocabulary="district",
        parent_level="district",
        parent_key="code",
    )
