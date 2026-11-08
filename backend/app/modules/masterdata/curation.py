"""Operator curation of entries families offered to the common lists (ADR-0026 §4).

Runs as the schema owner from ``python -m app.cli.masterdata offers``. Accepting an offer writes the
term into its pack JSON, so promotion goes through code review like every other pack change; the
next ``load`` makes it a global ``reviewed`` term. The pack term never names the family or the tree.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TreeMembership, TreeVocabularyTerm, UserNotification, VocabularyTerm
from app.models.enums import NotificationKind, OfferStatus
from app.modules.masterdata.loader import _CODE, PACK_DIR, PackError, validate_pack
from app.modules.masterdata.match import loose_key, same_value


@dataclass
class PendingOffer:
    row: TreeVocabularyTerm
    # global terms and other pending offers that look like the same entry (for merging)
    similar_terms: list[str] = field(default_factory=list)
    similar_offers: list[uuid.UUID] = field(default_factory=list)


def _texts(row: TreeVocabularyTerm) -> list[str]:
    return [row.label, *row.aliases]


def _alike(a: list[str], b: list[str]) -> bool:
    if any(same_value(x, y) for x in a for y in b):
        return True
    # "Khandoba" and "Khandoba of Jejuri": one loose key starts the other
    ka = {loose_key(x) for x in a if len(loose_key(x)) >= 4}
    kb = {loose_key(y) for y in b if len(loose_key(y)) >= 4}
    return any(x.startswith(y) or y.startswith(x) for x in ka for y in kb)


def pending(db: Session, vocabulary: str | None = None) -> list[PendingOffer]:
    stmt = select(TreeVocabularyTerm).where(TreeVocabularyTerm.offer_status == OfferStatus.OFFERED)
    if vocabulary:
        stmt = stmt.where(TreeVocabularyTerm.vocabulary_key == vocabulary)
    rows = list(db.scalars(stmt.order_by(TreeVocabularyTerm.vocabulary_key, TreeVocabularyTerm.offered_at)))
    out = []
    for row in rows:
        terms = db.scalars(select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == row.vocabulary_key))
        similar_terms = [t.code for t in terms if _alike(_texts(row), [*t.labels.values(), *t.aliases])]
        similar_offers = [
            o.id
            for o in rows
            if o.id != row.id and o.vocabulary_key == row.vocabulary_key and _alike(_texts(row), _texts(o))
        ]
        out.append(PendingOffer(row, similar_terms, similar_offers))
    return out


def _offers(db: Session, ids: list[uuid.UUID]) -> list[TreeVocabularyTerm]:
    rows = list(db.scalars(select(TreeVocabularyTerm).where(TreeVocabularyTerm.id.in_(ids))))
    if len(rows) != len(set(ids)):
        raise PackError("unknown offer id")
    if any(r.offer_status != OfferStatus.OFFERED for r in rows):
        raise PackError("only pending offers can be decided")
    if len({r.vocabulary_key for r in rows}) != 1:
        raise PackError("offers to merge must belong to one vocabulary")
    return rows


def _notify(db: Session, row: TreeVocabularyTerm, kind: NotificationKind) -> None:
    """Tell whoever offered the entry, if they are still a member of that tree."""
    if row.offered_by is None:
        return
    member = db.scalar(
        select(TreeMembership.id).where(
            TreeMembership.tree_id == row.tree_id, TreeMembership.user_id == row.offered_by
        )
    )
    if member is None:
        return
    db.add(UserNotification(tree_id=row.tree_id, user_id=row.offered_by, kind=kind, subject_id=row.id))


def _same_text(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def accept(
    db: Session,
    ids: list[uuid.UUID],
    *,
    code: str,
    en: str | None = None,
    hi: str | None = None,
    pack_dir: Path = PACK_DIR,
) -> dict[str, Any]:
    """Write the offered entry (or entries, merged) into the pack and mark the offers accepted.

    An existing ``code`` gains the offered labels as aliases; a new one needs English and Hindi
    labels from the operator. Returns the pack term as written. The caller commits.
    """
    rows = _offers(db, ids)
    key = rows[0].vocabulary_key
    if not _CODE.match(code):
        raise PackError(f"bad code {code!r}")
    path = pack_dir / f"{key}.json"
    pack = json.loads(path.read_text(encoding="utf-8"))
    term = next((t for t in pack["terms"] if t["code"] == code), None)
    offered = list(dict.fromkeys(x for r in rows for x in _texts(r)))
    if term is None:
        if not (en and en.strip() and hi and hi.strip()):
            raise PackError("a new term needs --en and --hi labels")
        term = {
            "code": code,
            "labels": {"en": en.strip(), "hi": hi.strip()},
            "aliases": [],
            "status": "reviewed",
        }
        temples = [r.offer_temple for r in rows if r.offer_temple]
        if temples:
            term["attributes"] = {"temple": temples[0]}
        pack["terms"].append(term)
    known = [*term["labels"].values(), *term.get("aliases", [])]
    for text in offered:
        if not any(_same_text(text, k) for k in known):
            term.setdefault("aliases", []).append(text)
            known.append(text)
    pack["version"] = int(pack["version"]) + 1
    validate_pack(pack, path.name)
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for r in rows:
        r.offer_status = OfferStatus.ACCEPTED
        r.promoted_code = code
        _notify(db, r, NotificationKind.OFFER_ACCEPTED)
    db.flush()
    return term


def decline(db: Session, ids: list[uuid.UUID]) -> int:
    """Decline offers. The family is told, without a reason that could name other families."""
    rows = _offers(db, ids)
    for r in rows:
        r.offer_status = OfferStatus.DECLINED
        _notify(db, r, NotificationKind.OFFER_DECLINED)
    db.flush()
    return len(rows)


def describe(p: PendingOffer) -> str:
    r = p.row
    when = r.offered_at.astimezone(dt.UTC).date().isoformat() if r.offered_at else "?"
    parts = [f"{r.id}  {r.vocabulary_key}  {r.label!r}"]
    if r.aliases:
        parts.append(f"aliases={r.aliases}")
    if r.offer_temple:
        parts.append(f"temple={r.offer_temple!r}")
    if r.offer_note:
        parts.append(f"note={r.offer_note!r}")
    parts.append(f"offered={when}")
    if p.similar_terms:
        parts.append(f"like-terms={p.similar_terms}")
    if p.similar_offers:
        parts.append(f"like-offers={[str(x) for x in p.similar_offers]}")
    return "  ".join(parts)
