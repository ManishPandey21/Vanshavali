"""Super Admin curation of the global vocabularies (ADR-0025).

Every edit is a ``vocabulary_change``: saved as a draft (pending) or published at once. Publishing
applies the change to ``vocabulary_term`` in one transaction, checks that the term has not moved on
since the editor loaded it (optimistic concurrency), bumps the term and vocabulary revisions, and
writes an audit event. Terms are never deleted; retirement keeps them resolvable for stored values.

This module only reads and writes the *global* tables. It never touches ``tree_vocabulary_term``
or any other tree data, so curating master data grants no view into any family.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AdminContext
from app.api.schemas import decode_cursor, encode_cursor
from app.core import audit
from app.core.config import get_settings
from app.core.errors import ApiError, Conflict, NotFound, Unprocessable
from app.models import User, Vocabulary, VocabularyChange, VocabularyTerm
from app.models.enums import (
    VocabularyChangeAction,
    VocabularyChangeStatus,
    VocabularyTermManagedBy,
    VocabularyTermStatus,
)
from app.modules.masterdata.admin_schemas import (
    AdminTermDetailOut,
    AdminTermOut,
    AdminTermPage,
    AdminVocabularyOut,
    MasterDataChangeIn,
    MasterDataChangeOut,
    MasterDataChangePage,
    VocabularyDuplicateOut,
)
from app.modules.masterdata.match import keys_for, matches, same_value

A = VocabularyChangeAction
S = VocabularyChangeStatus
FIELDS = (
    "labels",
    "aliases",
    "scope",
    "parent_code",
    "attributes",
    "source_url",
    "status",
    "sort_order",
    "successor_code",
)
MAX_PAGE = 200


# ---------------------------------------------------------------- reads
def _vocabulary(db: Session, key: str) -> Vocabulary:
    vocab = db.get(Vocabulary, key)
    if vocab is None:
        raise NotFound("Vocabulary not found")
    return vocab


def _term(db: Session, key: str, code: str) -> VocabularyTerm | None:
    return db.scalar(
        select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == key, VocabularyTerm.code == code)
    )


def _pending_for(db: Session, key: str) -> dict[str, uuid.UUID]:
    rows = db.execute(
        select(VocabularyChange.term_code, VocabularyChange.id).where(
            VocabularyChange.vocabulary_key == key, VocabularyChange.status == S.PENDING
        )
    )
    return dict(rows.tuples().all())


def _vocab_out(db: Session, v: Vocabulary) -> AdminVocabularyOut:
    counts = {s.value: 0 for s in VocabularyTermStatus}
    for status, n in db.execute(
        select(VocabularyTerm.status, func.count())
        .where(VocabularyTerm.vocabulary_key == v.key)
        .group_by(VocabularyTerm.status)
    ):
        counts[VocabularyTermStatus(status).value] = n
    pending = db.scalar(
        select(func.count())
        .select_from(VocabularyChange)
        .where(VocabularyChange.vocabulary_key == v.key, VocabularyChange.status == S.PENDING)
    )
    return AdminVocabularyOut(
        key=v.key,
        description=v.description,
        category=v.category,
        version=v.version,
        revision=v.revision,
        source=v.source,
        licence=v.licence,
        allows_custom=v.allows_custom,
        fixed_membership=v.fixed_membership,
        counts=counts,
        pending_changes=pending or 0,
    )


def list_vocabularies(ctx: AdminContext) -> list[AdminVocabularyOut]:
    rows = ctx.db.scalars(select(Vocabulary).order_by(Vocabulary.category, Vocabulary.key))
    return [_vocab_out(ctx.db, v) for v in rows]


def _term_out(t: VocabularyTerm, pending: uuid.UUID | None = None) -> AdminTermOut:
    return AdminTermOut(
        code=t.code,
        labels=t.labels,
        aliases=t.aliases,
        scope=t.scope,
        parent_code=t.parent_code,
        attributes=t.attributes,
        source_url=t.source_url,
        status=t.status,
        sort_order=t.sort_order,
        successor_code=t.successor_code,
        managed_by=t.managed_by,
        revision=t.revision,
        updated_at=t.updated_at,
        pending_change_id=pending,
    )


def list_terms(
    ctx: AdminContext,
    key: str,
    *,
    q: str = "",
    status: VocabularyTermStatus | None = None,
    managed_by: VocabularyTermManagedBy | None = None,
    sort: str = "order",
    cursor: str | None = None,
    limit: int = 50,
) -> AdminTermPage:
    vocab = _vocabulary(ctx.db, key)
    stmt = select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == key)
    if status is not None:
        stmt = stmt.where(VocabularyTerm.status == status)
    if managed_by is not None:
        stmt = stmt.where(VocabularyTerm.managed_by == managed_by)
    order = {
        "order": (VocabularyTerm.sort_order, VocabularyTerm.code),
        "code": (VocabularyTerm.code,),
        "updated": (VocabularyTerm.updated_at.desc(), VocabularyTerm.code),
    }.get(sort, (VocabularyTerm.sort_order, VocabularyTerm.code))
    rows = [
        t
        for t in ctx.db.scalars(stmt.order_by(*order))
        if matches(q, *keys_for(t.code.replace("_", " "), *t.labels.values(), *t.aliases))
    ]
    offset = decode_cursor(cursor)
    limit = max(1, min(limit, MAX_PAGE))
    page = rows[offset : offset + limit]
    pending = _pending_for(ctx.db, key)
    return AdminTermPage(
        vocabulary=_vocab_out(ctx.db, vocab),
        items=[_term_out(t, pending.get(t.code)) for t in page],
        total=len(rows),
        next_cursor=encode_cursor(offset + limit) if offset + limit < len(rows) else None,
    )


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return {u.id: u.display_name for u in db.scalars(select(User).where(User.id.in_(wanted)))}


def _changes_out(ctx: AdminContext, rows: list[VocabularyChange]) -> list[MasterDataChangeOut]:
    names = _names(ctx.db, {r.proposed_by for r in rows} | {r.decided_by for r in rows})
    revisions: dict[tuple[str, str], int] = {}
    out = []
    for r in rows:
        stale = False
        if r.status == S.PENDING:
            k = (r.vocabulary_key, r.term_code)
            if k not in revisions:
                t = _term(ctx.db, *k)
                revisions[k] = t.revision if t is not None else 0
            current = revisions[k]
            stale = (r.base_revision or 0) != current
        out.append(
            MasterDataChangeOut(
                id=r.id,
                vocabulary_key=r.vocabulary_key,
                term_code=r.term_code,
                action=r.action,
                status=r.status,
                base_revision=r.base_revision,
                previous=r.previous,
                proposed=r.proposed,
                reason=r.reason,
                source_reference=r.source_reference,
                proposed_by_name=names.get(r.proposed_by) if r.proposed_by else None,
                proposed_by_me=r.proposed_by == ctx.user_id,
                proposed_at=r.proposed_at,
                decided_by_name=names.get(r.decided_by) if r.decided_by else None,
                decided_at=r.decided_at,
                decision_note=r.decision_note,
                stale=stale,
            )
        )
    return out


def term_detail(ctx: AdminContext, key: str, code: str) -> AdminTermDetailOut:
    _vocabulary(ctx.db, key)
    t = _term(ctx.db, key, code)
    if t is None:
        raise NotFound("Term not found")
    history = list(
        ctx.db.scalars(
            select(VocabularyChange)
            .where(VocabularyChange.vocabulary_key == key, VocabularyChange.term_code == code)
            .order_by(VocabularyChange.proposed_at.desc(), VocabularyChange.id.desc())
        )
    )
    pending = next((c.id for c in history if c.status == S.PENDING), None)
    return AdminTermDetailOut(term=_term_out(t, pending), history=_changes_out(ctx, history))


def list_changes(
    ctx: AdminContext,
    *,
    status: VocabularyChangeStatus | None = None,
    vocabulary: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> MasterDataChangePage:
    stmt = select(VocabularyChange)
    if status is not None:
        stmt = stmt.where(VocabularyChange.status == status)
    if vocabulary:
        stmt = stmt.where(VocabularyChange.vocabulary_key == vocabulary)
    offset = decode_cursor(cursor)
    limit = max(1, min(limit, MAX_PAGE))
    rows = list(
        ctx.db.scalars(
            stmt.order_by(VocabularyChange.proposed_at.desc(), VocabularyChange.id.desc())
            .offset(offset)
            .limit(limit + 1)
        )
    )
    more = len(rows) > limit
    return MasterDataChangePage(
        items=_changes_out(ctx, rows[:limit]), next_cursor=encode_cursor(offset + limit) if more else None
    )


def get_change(ctx: AdminContext, change_id: uuid.UUID) -> MasterDataChangeOut:
    return _changes_out(ctx, [_change(ctx.db, change_id)])[0]


def _change(db: Session, change_id: uuid.UUID) -> VocabularyChange:
    row = db.get(VocabularyChange, change_id)
    if row is None:
        raise NotFound("Change not found")
    return row


# ---------------------------------------------------------------- duplicate detection
def find_similar(
    db: Session, key: str, labels: dict[str, str], aliases: list[str], *, exclude_code: str | None = None
) -> list[VocabularyDuplicateOut]:
    """Existing terms (retired included) whose label or alias is the same word written differently."""
    texts = [x for x in (*labels.values(), *aliases) if x and x.strip()]
    out: list[VocabularyDuplicateOut] = []
    if not texts:
        return out
    for t in db.scalars(select(VocabularyTerm).where(VocabularyTerm.vocabulary_key == key)):
        if t.code == exclude_code:
            continue
        theirs = [*t.labels.values(), *t.aliases]
        hit = next((b for a in texts for b in theirs if same_value(a, b)), None)
        if hit is not None:
            label = t.labels.get("en") or next(iter(t.labels.values()), t.code)
            out.append(VocabularyDuplicateOut(code=t.code, label=label, status=t.status, matched=hit))
    return out[:20]


def check_duplicates(
    ctx: AdminContext, key: str, labels: dict[str, str], aliases: list[str], exclude_code: str | None
) -> list[VocabularyDuplicateOut]:
    _vocabulary(ctx.db, key)
    return find_similar(ctx.db, key, labels, aliases, exclude_code=exclude_code)


# ---------------------------------------------------------------- proposing
def _snapshot(t: VocabularyTerm | None) -> dict[str, Any]:
    if t is None:
        return {}
    snap = {f: getattr(t, f) for f in FIELDS}
    snap["status"] = VocabularyTermStatus(t.status).value
    return snap


def _check_reference(db: Session, key: str, code: str | None, own: str, what: str) -> None:
    if code is None:
        return
    if code == own:
        raise Unprocessable(f"A term cannot be its own {what}", code=f"invalid_{what}")
    ref = _term(db, key, code)
    if ref is None or ref.status == VocabularyTermStatus.RETIRED:
        raise Unprocessable(
            f"The {what} must be an existing, active term in this list", code=f"invalid_{what}"
        )


def _validate(db: Session, vocab: Vocabulary, change: VocabularyChange, term: VocabularyTerm | None) -> None:
    """Rules checked when a change is proposed and again when it is published."""
    action = VocabularyChangeAction(change.action)
    if vocab.fixed_membership and action in (A.CREATE, A.RETIRE, A.REACTIVATE):
        raise Unprocessable(
            "This list is a fixed set: its labels can be corrected, but terms cannot be added or removed",
            code="fixed_vocabulary",
        )
    if action == A.CREATE:
        if term is not None:
            raise Conflict("A term with this code already exists", code="code_taken")
    elif term is None:
        raise NotFound("Term not found")
    elif action == A.RETIRE and term.status == VocabularyTermStatus.RETIRED:
        raise Conflict("The term is already retired", code="already_retired")
    elif action == A.REACTIVATE and term.status != VocabularyTermStatus.RETIRED:
        raise Conflict("Only a retired term can be reactivated", code="not_retired")
    elif action == A.UPDATE and term.status == VocabularyTermStatus.RETIRED:
        raise Conflict("Reactivate the term before editing it", code="term_retired")
    if action in (A.CREATE, A.UPDATE):
        _check_reference(db, vocab.key, change.proposed.get("parent_code"), change.term_code, "parent")
    if action == A.RETIRE:
        _check_reference(db, vocab.key, change.proposed.get("successor_code"), change.term_code, "successor")


def propose(ctx: AdminContext, key: str, body: MasterDataChangeIn) -> MasterDataChangeOut:
    db = ctx.db
    # serialise proposals per vocabulary: the "one open change per term" check, the code check and
    # the revision counter must not race (backed by a partial unique index on pending changes)
    vocab = db.get(Vocabulary, key, with_for_update=True)
    if vocab is None:
        raise NotFound("Vocabulary not found")
    term = _term(db, key, body.code)
    if body.publish and get_settings().masterdata_require_second_admin:
        raise ApiError(
            "Another administrator must publish this change. Save it as a draft instead.",
            code="second_admin_required",
            status_code=403,
        )
    if term is not None and body.base_revision is not None and term.revision != body.base_revision:
        raise Conflict(
            "Someone changed this term after you opened it. Reload it and make your change again.",
            code="stale_revision",
            details={"current_revision": term.revision},
        )
    clash = db.scalar(
        select(VocabularyChange.id).where(
            VocabularyChange.vocabulary_key == key,
            VocabularyChange.term_code == body.code,
            VocabularyChange.status == S.PENDING,
        )
    )
    if clash is not None:
        raise Conflict(
            "This term already has a change waiting for review. Publish, reject or withdraw it first.",
            code="change_pending",
            details={"change_id": str(clash)},
        )
    previous = _snapshot(term)
    if body.action in (A.CREATE, A.UPDATE):
        if body.term is None:  # guaranteed by MasterDataChangeIn; kept for the type checker
            raise Unprocessable("The term fields are missing")
        proposed = body.term.model_dump()
        proposed["successor_code"] = None
        if not body.allow_similar:
            similar = find_similar(db, key, body.term.labels, body.term.aliases, exclude_code=body.code)
            if similar:
                raise Conflict(
                    "This looks like an entry that already exists. Use it, add your spelling as an alias, "
                    "or confirm that it is a different entry.",
                    code="possible_duplicate",
                    details={"matches": [m.model_dump(mode="json") for m in similar]},
                )
        if body.action == A.UPDATE and proposed == previous:
            raise Unprocessable("Nothing changed", code="no_change")
    elif body.action == A.RETIRE:
        proposed = {
            **previous,
            "status": VocabularyTermStatus.RETIRED.value,
            "successor_code": body.successor_code,
        }
    else:  # reactivate
        proposed = {**previous, "status": body.reactivate_as, "successor_code": None}
    change = VocabularyChange(
        vocabulary_key=key,
        term_code=body.code,
        action=body.action,
        status=S.PENDING,
        base_revision=term.revision if term is not None else None,
        previous=previous,
        proposed=proposed,
        reason=body.reason,
        source_reference=body.source_reference,
        proposed_by=ctx.user_id,
    )
    _validate(db, vocab, change, term)
    db.add(change)
    db.flush()
    _audit(ctx, "masterdata.change_proposed", change)
    if body.publish:
        _publish(ctx, vocab, change, None)
    return get_change(ctx, change.id)


# ---------------------------------------------------------------- deciding
def _audit(ctx: AdminContext, action: str, change: VocabularyChange) -> None:
    # global reference data only; the values themselves are kept in vocabulary_change
    audit.record(
        ctx.db,
        action=action,
        actor_user_id=ctx.user_id,
        target_type="vocabulary_change",
        target_id=change.id,
        details={
            "vocabulary": change.vocabulary_key,
            "code": change.term_code,
            "action": VocabularyChangeAction(change.action).value,
        },
        ip=ctx.request.ip,
        user_agent=ctx.request.user_agent,
    )


def _pending(db: Session, change_id: uuid.UUID) -> VocabularyChange:
    change = _change(db, change_id)
    if change.status != S.PENDING:
        raise Conflict("This change has already been decided", code="change_decided")
    return change


def _publish(ctx: AdminContext, vocab: Vocabulary, change: VocabularyChange, note: str | None) -> None:
    db = ctx.db
    if get_settings().masterdata_require_second_admin and change.proposed_by == ctx.user_id:
        raise ApiError(
            "Another administrator must publish a change you proposed.",
            code="second_admin_required",
            status_code=403,
        )
    term = db.scalar(
        select(VocabularyTerm)
        .where(VocabularyTerm.vocabulary_key == vocab.key, VocabularyTerm.code == change.term_code)
        .with_for_update()
    )
    current = term.revision if term is not None else None
    if current != change.base_revision:
        raise Conflict(
            "The term changed after this draft was prepared. Withdraw or reject it and propose it again.",
            code="stale_change",
        )
    _validate(db, vocab, change, term)
    p = change.proposed
    values = {f: p.get(f) for f in FIELDS}
    values["status"] = VocabularyTermStatus(p["status"])
    if term is None:
        term = VocabularyTerm(
            vocabulary_key=vocab.key,
            code=change.term_code,
            created_by=change.proposed_by,
            revision=1,
            **values,
        )
        db.add(term)
    else:
        for k, v in values.items():
            setattr(term, k, v)
        term.revision += 1
    term.managed_by = VocabularyTermManagedBy.ADMIN
    term.updated_by = ctx.user_id
    vocab.revision += 1
    change.status = S.PUBLISHED
    change.decided_by = ctx.user_id
    change.decided_at = dt.datetime.now(dt.UTC)
    change.decision_note = note
    db.flush()
    _audit(ctx, "masterdata.change_published", change)


def publish(ctx: AdminContext, change_id: uuid.UUID, note: str | None) -> MasterDataChangeOut:
    change = _pending(ctx.db, change_id)
    vocab = ctx.db.get(Vocabulary, change.vocabulary_key, with_for_update=True)
    if vocab is None:
        raise NotFound("Vocabulary not found")
    _publish(ctx, vocab, change, note)
    return get_change(ctx, change.id)


def reject(ctx: AdminContext, change_id: uuid.UUID, note: str) -> MasterDataChangeOut:
    change = _pending(ctx.db, change_id)
    change.status = S.REJECTED
    change.decided_by = ctx.user_id
    change.decided_at = dt.datetime.now(dt.UTC)
    change.decision_note = note.strip()
    _audit(ctx, "masterdata.change_rejected", change)
    return get_change(ctx, change.id)


def withdraw(ctx: AdminContext, change_id: uuid.UUID) -> MasterDataChangeOut:
    change = _pending(ctx.db, change_id)
    if change.proposed_by != ctx.user_id:
        raise ApiError(
            "Only the administrator who proposed a change can withdraw it",
            code="not_proposer",
            status_code=403,
        )
    change.status = S.WITHDRAWN
    change.decided_by = ctx.user_id
    change.decided_at = dt.datetime.now(dt.UTC)
    _audit(ctx, "masterdata.change_withdrawn", change)
    return get_change(ctx, change.id)
