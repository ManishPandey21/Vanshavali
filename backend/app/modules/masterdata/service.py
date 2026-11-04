"""Vocabulary lookups and family entries (ADR-0018)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.config import get_settings
from app.core.errors import NotFound, Unprocessable
from app.models import TreeVocabularyTerm, Vocabulary, VocabularyTerm
from app.models.enums import VocabularyTermStatus
from app.modules.masterdata.match import keys_for, matches, same_value
from app.modules.masterdata.schemas import VocabularyOut, VocabularyTermOut

MAX_RESULTS = 200


def _enabled() -> None:
    if not get_settings().masterdata_enabled:
        raise NotFound("Not found")


def _vocabulary(db: Session, key: str) -> Vocabulary:
    _enabled()
    vocab = db.get(Vocabulary, key)
    if vocab is None:
        raise NotFound("Vocabulary not found")
    return vocab


def _vocab_out(db: Session, v: Vocabulary) -> VocabularyOut:
    count = db.scalar(
        select(func.count())
        .select_from(VocabularyTerm)
        .where(VocabularyTerm.vocabulary_key == v.key, VocabularyTerm.status != VocabularyTermStatus.RETIRED)
    )
    return VocabularyOut(
        key=v.key,
        description=v.description,
        version=v.version,
        source=v.source,
        licence=v.licence,
        allows_custom=v.allows_custom,
        term_count=count or 0,
    )


def list_vocabularies(db: Session) -> list[VocabularyOut]:
    _enabled()
    return [_vocab_out(db, v) for v in db.scalars(select(Vocabulary).order_by(Vocabulary.key))]


def _label(labels: dict[str, str], lang: str) -> str:
    return labels.get(lang) or labels.get("en") or next(iter(labels.values()), "")


def _global_out(t: VocabularyTerm, lang: str) -> VocabularyTermOut:
    return VocabularyTermOut(
        code=t.code,
        label=_label(t.labels, lang),
        labels=t.labels,
        aliases=t.aliases,
        parent_code=t.parent_code,
        attributes=t.attributes,
        status=t.status,
    )


def _family_out(t: TreeVocabularyTerm) -> VocabularyTermOut:
    return VocabularyTermOut(
        code=t.code,
        label=t.label,
        labels={},
        aliases=t.aliases,
        status=VocabularyTermStatus.REVIEWED,
        origin="family",
        id=t.id,
    )


def _global_terms(
    db: Session, key: str, *, include_retired: bool = False, parent: str | None = None
) -> list[VocabularyTerm]:
    stmt = select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == key)
    if not include_retired:
        stmt = stmt.where(VocabularyTerm.status != VocabularyTermStatus.RETIRED)
    if parent is not None:
        stmt = stmt.where(VocabularyTerm.parent_code == parent)
    return list(db.scalars(stmt.order_by(VocabularyTerm.sort_order, VocabularyTerm.code)))


def _global_match(t: VocabularyTerm, q: str) -> bool:
    strict, loose = keys_for(t.code.replace("_", " "), *t.labels.values(), *t.aliases)
    return matches(q, strict, loose)


def global_terms(
    db: Session,
    key: str,
    *,
    q: str = "",
    lang: str = "en",
    parent: str | None = None,
    include_retired: bool = False,
) -> tuple[VocabularyOut, list[VocabularyTermOut]]:
    vocab = _vocabulary(db, key)
    rows = _global_terms(db, key, include_retired=include_retired, parent=parent)
    items = [_global_out(t, lang) for t in rows if _global_match(t, q)][:MAX_RESULTS]
    return _vocab_out(db, vocab), items


def _tree_terms(ctx: TreeContext, key: str) -> list[TreeVocabularyTerm]:
    return list(
        ctx.db.scalars(
            select(TreeVocabularyTerm)
            .where(TreeVocabularyTerm.tree_id == ctx.tree_id, TreeVocabularyTerm.vocabulary_key == key)
            .order_by(TreeVocabularyTerm.label)
        )
    )


def tree_terms(
    ctx: TreeContext, key: str, *, q: str = "", lang: str = "en"
) -> tuple[VocabularyOut, list[VocabularyTermOut]]:
    """Global suggestions plus this family's own entries (family entries first)."""
    ctx.require(Permission.TREE_READ)
    vocab_out, global_items = global_terms(ctx.db, key, q=q, lang=lang)
    family = [_family_out(t) for t in _tree_terms(ctx, key) if matches(q, *keys_for(t.label, *t.aliases))]
    return vocab_out, (family + global_items)[:MAX_RESULTS]


def _slug(label: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "_", ascii_.lower()).strip("_")
    return s[:60]


def add_tree_term(
    ctx: TreeContext, key: str, label: str, aliases: list[str], lang: str = "en"
) -> tuple[VocabularyTermOut, bool]:
    """Add a family entry, or return the existing global/family entry the label already names."""
    ctx.require(Permission.PERSON_WRITE)
    vocab = _vocabulary(ctx.db, key)
    if not vocab.allows_custom:
        raise Unprocessable("This list cannot be extended", code="vocabulary_closed")
    for t in _global_terms(ctx.db, key):
        if any(same_value(label, x) for x in (*t.labels.values(), *t.aliases)):
            return _global_out(t, lang), False
    for ft in _tree_terms(ctx, key):
        if any(same_value(label, x) for x in (ft.label, *ft.aliases)):
            return _family_out(ft), False
    base = _slug(label) or uuid.uuid4().hex[:12]
    code = f"t:{base}"
    taken = {ft.code for ft in _tree_terms(ctx, key)}
    n = 2
    while code in taken:
        code = f"t:{base}_{n}"
        n += 1
    row = TreeVocabularyTerm(
        tree_id=ctx.tree_id,
        vocabulary_key=key,
        code=code,
        label=label,
        aliases=aliases,
        created_by=ctx.user_id,
    )
    ctx.db.add(row)
    ctx.db.flush()
    # the label is family data (it may name a family deity): audit the fact, not the value
    audit.log(
        ctx,
        "vocabulary.family_term_added",
        target_type="tree_vocabulary_term",
        target_id=row.id,
        details={"vocabulary": key},
    )
    return _family_out(row), True


def check_reference(ctx: TreeContext, value: Any) -> None:
    """A stored ``{"vocabulary": key, "code": code}`` must name a global term or one of this tree's
    entries (ADR-0018 §6). Values without a vocabulary reference are not checked."""
    if not isinstance(value, dict) or "vocabulary" not in value:
        return
    key, code = value.get("vocabulary"), value.get("code")
    if not isinstance(key, str) or not isinstance(code, str):
        raise Unprocessable(
            "A vocabulary reference needs a vocabulary and a code", code="invalid_vocabulary_reference"
        )
    exists = ctx.db.scalar(
        select(VocabularyTerm.id).where(VocabularyTerm.vocabulary_key == key, VocabularyTerm.code == code)
    ) or ctx.db.scalar(
        select(TreeVocabularyTerm.id).where(
            TreeVocabularyTerm.tree_id == ctx.tree_id,
            TreeVocabularyTerm.vocabulary_key == key,
            TreeVocabularyTerm.code == code,
        )
    )
    if not exists:
        raise Unprocessable("Unknown vocabulary entry", code="invalid_vocabulary_reference")
