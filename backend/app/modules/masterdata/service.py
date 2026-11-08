"""Vocabulary lookups and family entries (ADR-0018)."""

from __future__ import annotations

import datetime as dt
import hashlib
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
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models import TreeVocabularyTerm, Vocabulary, VocabularyTerm
from app.models.enums import OfferStatus, VocabularyTermStatus
from app.modules.masterdata.match import keys_for, matches, same_value
from app.modules.masterdata.schemas import OfferOut, VocabularyOut, VocabularyTermOut

MAX_RESULTS = 200
# a family's own entries that may be offered to the common lists (ADR-0026 §4)
OFFERABLE = frozenset({"kuladevata", "kuladevi", "devak", "gotra", "kula"})


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
        offer_status=t.offer_status,
        promoted_code=t.promoted_code,
    )


def _global_terms(
    db: Session,
    key: str,
    *,
    include_retired: bool = False,
    parent: str | None = None,
    reviewed_only: bool = False,
    scope: str | None = None,
) -> list[VocabularyTerm]:
    stmt = select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == key)
    if reviewed_only:
        stmt = stmt.where(VocabularyTerm.status == VocabularyTermStatus.REVIEWED)
    elif not include_retired:
        stmt = stmt.where(VocabularyTerm.status != VocabularyTermStatus.RETIRED)
    if parent is not None:
        stmt = stmt.where(VocabularyTerm.parent_code == parent)
    if scope is not None:
        stmt = stmt.where(VocabularyTerm.scope.contains([scope]))
    return list(db.scalars(stmt.order_by(VocabularyTerm.sort_order, VocabularyTerm.code)))


def vocabulary_etag(db: Session, key: str, *parts: object) -> str:
    """A validator for ``GET /vocabularies/{key}``: changes whenever the pack is reloaded."""
    vocab = _vocabulary(db, key)
    count, latest = db.execute(
        select(func.count(), func.max(VocabularyTerm.updated_at)).where(VocabularyTerm.vocabulary_key == key)
    ).one()
    seed = "|".join(str(x) for x in (key, vocab.version, vocab.updated_at, count, latest, *parts))
    return 'W/"' + hashlib.sha256(seed.encode()).hexdigest()[:32] + '"'


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
    reviewed_only: bool = False,
    scope: str | None = None,
) -> tuple[VocabularyOut, list[VocabularyTermOut]]:
    vocab = _vocabulary(db, key)
    rows = _global_terms(
        db,
        key,
        include_retired=include_retired,
        parent=parent,
        reviewed_only=reviewed_only,
        scope=scope,
    )
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
    own = _tree_terms(ctx, key)
    family = [_family_out(t) for t in own if matches(q, *keys_for(t.label, *t.aliases))]
    # a promoted entry keeps the family's own code; the global term it became is not listed twice
    promoted = {t.promoted_code for t in own if t.promoted_code}
    global_items = [g for g in global_items if g.code not in promoted]
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


# ---------------------------------------------------------------- offers (ADR-0026 §4)
def _offer_out(t: TreeVocabularyTerm) -> OfferOut:
    return OfferOut(
        id=t.id,
        vocabulary_key=t.vocabulary_key,
        code=t.code,
        label=t.label,
        aliases=t.aliases,
        offer_status=t.offer_status,
        offered_at=t.offered_at,
        offer_note=t.offer_note,
        offer_temple=t.offer_temple,
        promoted_code=t.promoted_code,
    )


def _own_term(ctx: TreeContext, key: str, code: str) -> TreeVocabularyTerm:
    row = ctx.db.scalar(
        select(TreeVocabularyTerm).where(
            TreeVocabularyTerm.tree_id == ctx.tree_id,
            TreeVocabularyTerm.vocabulary_key == key,
            TreeVocabularyTerm.code == code,
        )
    )
    if row is None:
        raise NotFound("Family entry not found")
    return row


def offer_tree_term(ctx: TreeContext, key: str, code: str, note: str | None, temple: str | None) -> OfferOut:
    """A tree admin offers one of the family's own entries to the common lists. Opt-in, per entry.

    The offer carries the label, aliases, an optional temple name and note; who offered it and the
    tree stay with the row (operators only) and never reach the shared term.
    """
    ctx.require(Permission.TREE_MANAGE)
    _vocabulary(ctx.db, key)
    if key not in OFFERABLE:
        raise Unprocessable("Entries in this list cannot be offered", code="vocabulary_not_offerable")
    row = _own_term(ctx, key, code)
    if row.offer_status in (OfferStatus.OFFERED, OfferStatus.ACCEPTED):
        raise Conflict("This entry has already been offered", code="already_offered")
    row.offer_status = OfferStatus.OFFERED
    row.offered_by = ctx.user_id
    row.offered_at = dt.datetime.now(dt.UTC)
    row.offer_note = note
    row.offer_temple = temple
    ctx.db.flush()
    audit.log(
        ctx,
        "vocabulary.family_term_offered",
        target_type="tree_vocabulary_term",
        target_id=row.id,
        details={"vocabulary": key},
    )
    return _offer_out(row)


def withdraw_offer(ctx: TreeContext, key: str, code: str) -> OfferOut:
    ctx.require(Permission.TREE_MANAGE)
    row = _own_term(ctx, key, code)
    if row.offer_status != OfferStatus.OFFERED:
        raise Conflict("Only a pending offer can be withdrawn", code="offer_not_pending")
    row.offer_status = OfferStatus.NONE
    row.offered_by = None
    row.offered_at = None
    row.offer_note = None
    row.offer_temple = None
    ctx.db.flush()
    audit.log(
        ctx,
        "vocabulary.family_term_offer_withdrawn",
        target_type="tree_vocabulary_term",
        target_id=row.id,
        details={"vocabulary": key},
    )
    return _offer_out(row)


def list_offers(ctx: TreeContext) -> list[OfferOut]:
    ctx.require(Permission.TREE_MANAGE)
    rows = ctx.db.scalars(
        select(TreeVocabularyTerm)
        .where(TreeVocabularyTerm.tree_id == ctx.tree_id, TreeVocabularyTerm.offer_status != OfferStatus.NONE)
        .order_by(TreeVocabularyTerm.offered_at.desc().nulls_last(), TreeVocabularyTerm.label)
    )
    return [_offer_out(t) for t in rows]
