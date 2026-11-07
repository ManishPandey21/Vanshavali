"""Load the JSON vocabulary packs into the global tables (ADR-0018 §4). Idempotent.

New terms are inserted, changed ones updated; a term no longer in its pack is marked ``retired``
(never deleted) so stored references keep resolving. Terms curated in the Super Admin console
(``managed_by = admin``, ADR-0026 §4) are never changed or retired by a pack: the report lists them
as ``kept`` so an operator can see where a pack and the console disagree. Run after
``alembic upgrade``:

    uv run python -m app.cli.masterdata load [--dry-run]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Vocabulary, VocabularyTerm
from app.models.enums import VocabularyTermManagedBy, VocabularyTermStatus

PACK_DIR = Path(__file__).parent / "packs"
_CODE = re.compile(r"^[a-z0-9][a-z0-9_]{0,79}$")
_LANGS_REQUIRED = ("en", "hi")
# console groups (ADR-0026 §6); the frontend has a label for each
CATEGORIES = ("heritage", "languages_terminology", "astrology", "religion_community", "geography", "other")


class PackError(ValueError):
    pass


def validate_pack(pack: dict[str, Any], name: str = "pack") -> None:
    """Raise PackError when a pack is malformed (also used by the tests on every shipped pack)."""
    for k in ("key", "version", "description", "source", "licence", "allows_custom", "terms"):
        if k not in pack:
            raise PackError(f"{name}: missing {k}")
    if not _CODE.match(pack["key"]) or len(pack["key"]) > 40:
        raise PackError(f"{name}: bad key {pack['key']!r}")
    if not isinstance(pack["version"], int) or pack["version"] < 1:
        raise PackError(f"{name}: version must be a positive integer")
    if pack.get("category", "other") not in CATEGORIES:
        raise PackError(f"{name}: bad category {pack.get('category')!r}")
    if not isinstance(pack.get("fixed_membership", False), bool):
        raise PackError(f"{name}: fixed_membership must be true or false")
    seen: set[str] = set()
    for t in pack["terms"]:
        code = t.get("code", "")
        if not _CODE.match(code):
            raise PackError(f"{name}: bad code {code!r}")
        if code in seen:
            raise PackError(f"{name}: duplicate code {code}")
        seen.add(code)
        labels = t.get("labels") or {}
        for lang in _LANGS_REQUIRED:
            if not str(labels.get(lang, "")).strip():
                raise PackError(f"{name}: {code} has no {lang} label")
        if t.get("status", "draft") not in {s.value for s in VocabularyTermStatus}:
            raise PackError(f"{name}: {code} has a bad status")
        unknown = set(t) - {
            "code",
            "labels",
            "aliases",
            "scope",
            "parent",
            "attributes",
            "source_url",
            "status",
        }
        if unknown:
            raise PackError(f"{name}: {code} has unknown fields {sorted(unknown)}")


def read_packs(directory: Path = PACK_DIR) -> list[dict[str, Any]]:
    packs = []
    for path in sorted(directory.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        validate_pack(pack, path.name)
        if pack["key"] != path.stem:
            raise PackError(f"{path.name}: key {pack['key']!r} does not match the file name")
        packs.append(pack)
    return packs


@dataclass
class LoadReport:
    vocabularies: int = 0
    inserted: int = 0
    updated: int = 0
    retired: int = 0
    unchanged: int = 0
    kept: int = 0  # console-curated terms the pack would have changed or retired
    changes: list[str] = field(default_factory=list)


def load_packs(
    db: Session, packs: list[dict[str, Any]] | None = None, *, dry_run: bool = False
) -> LoadReport:
    packs = read_packs() if packs is None else packs
    report = LoadReport()
    for pack in packs:
        validate_pack(pack, pack.get("key", "pack"))
        report.vocabularies += 1
        vocab = db.get(Vocabulary, pack["key"])
        meta = {
            "description": pack["description"],
            "version": pack["version"],
            "source": pack["source"],
            "licence": pack["licence"],
            "allows_custom": bool(pack["allows_custom"]),
            "category": pack.get("category", "other"),
            "fixed_membership": bool(pack.get("fixed_membership", False)),
        }
        is_new = vocab is None
        if vocab is None:
            vocab = Vocabulary(key=pack["key"], **meta)
            db.add(vocab)
            report.changes.append(f"+ vocabulary {pack['key']}")
        else:
            for k, v in meta.items():
                setattr(vocab, k, v)
        db.flush()
        changed_terms = 0
        existing = {
            t.code: t
            for t in db.scalars(select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == pack["key"]))
        }
        for order, t in enumerate(pack["terms"]):
            values = {
                "labels": t["labels"],
                "aliases": list(t.get("aliases", [])),
                "scope": list(t.get("scope", [])),
                "parent_code": t.get("parent"),
                "attributes": t.get("attributes", {}),
                "source_url": t.get("source_url"),
                "status": VocabularyTermStatus(t.get("status", "draft")),
                "sort_order": order,
            }
            row = existing.pop(t["code"], None)
            if row is None:
                db.add(VocabularyTerm(vocabulary_key=pack["key"], code=t["code"], **values))
                report.inserted += 1
                changed_terms += 1
                report.changes.append(f"+ {pack['key']}:{t['code']}")
            elif row.managed_by == VocabularyTermManagedBy.ADMIN:
                if any(getattr(row, k) != v for k, v in values.items() if k != "sort_order"):
                    report.kept += 1
                    report.changes.append(f"= {pack['key']}:{t['code']} (curated in the console, kept)")
                else:
                    report.unchanged += 1
            elif any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items():
                    setattr(row, k, v)
                row.revision += 1
                report.updated += 1
                changed_terms += 1
                report.changes.append(f"~ {pack['key']}:{t['code']}")
            else:
                report.unchanged += 1
        for row in existing.values():  # dropped from the pack: retire, never delete
            if row.managed_by == VocabularyTermManagedBy.ADMIN:
                continue  # added or adopted in the console: not the pack's to retire
            if row.status != VocabularyTermStatus.RETIRED:
                row.status = VocabularyTermStatus.RETIRED
                row.revision += 1
                report.retired += 1
                changed_terms += 1
                report.changes.append(f"- {pack['key']}:{row.code} (retired)")
        if changed_terms and not is_new:
            vocab.revision += 1  # clients holding the old list refresh it (ADR-0026 §7)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report
