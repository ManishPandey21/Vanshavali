"""Revision counters and value history for every write path (ADR-0021 §3).

One ``before_flush`` hook on every session sees every insert, update and delete of the five
reviewable record types (and traditions and family words, ADR-0026), whichever code path made it: the direct endpoints, Smart Add, GEDCOM
import, merge, an applied proposal. For each record whose *facts* changed it:

* increments ``revision`` (a create starts at 1);
* writes a ``record_revision`` row with only the changed fields, before and after;
* sets ``review_state`` back to ``unreviewed``, unless the same flush set the review state itself;
* increments the owning person's ``revision`` too (for a name, vital, heritage claim or
  relationship), so a proposal that adds something to a person binds to that person.

Who and why come from ``session.info``: ``actor_id`` (set when a tree context loads),
``proposal_id`` and ``reviewer_id`` (set while an accepted proposal is applied).
``revisions_suppressed`` turns the hook off while a person is erased.
"""

from __future__ import annotations

import datetime as dt
import decimal
import enum
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.core.ids import uuid7
from app.models import (
    Assertion,
    Event,
    EventParticipant,
    KinshipOverride,
    NameRecord,
    Person,
    RecordRevision,
    Relationship,
    TraditionEntry,
)
from app.models.enums import ParticipantRole, ProposalOp, ReviewState, ReviewTarget

TRACKED: dict[type, ReviewTarget] = {
    Person: ReviewTarget.PERSON,
    NameRecord: ReviewTarget.NAME,
    Event: ReviewTarget.EVENT,
    Relationship: ReviewTarget.RELATIONSHIP,
    Assertion: ReviewTarget.ASSERTION,
    # ADR-0026: not about one person; their history is read from the record itself
    TraditionEntry: ReviewTarget.TRADITION,
    KinshipOverride: ReviewTarget.KINSHIP_WORD,
}
MODEL_FOR: dict[ReviewTarget, type] = {v: k for k, v in TRACKED.items()}

# bookkeeping, derived or review columns: never a "fact change"
IGNORED = frozenset(
    {
        "id",
        "tree_id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "revision",
        "review_state",
        "review_state_by",
        "review_state_at",
        "search_text",
        "search_phonetic",
        "date_sort_from",
        "date_sort_to",
        "claimed_by_user_id",
    }
)

_PENDING_EVENTS = "review_pending_event_revisions"


def _json(v: Any) -> Any:
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_json(x) for x in v]
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    return v


def _fields(obj: Any) -> list[str]:
    return [
        a.key
        for a in inspect(type(obj)).column_attrs
        if a.key not in IGNORED and not a.key.startswith("prov_")
    ]


def _owners(obj: Any) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if isinstance(obj, Person):
        return obj.id, None
    if isinstance(obj, (NameRecord, Assertion)):
        return obj.person_id, None
    if isinstance(obj, Relationship):
        return obj.person_a_id, obj.person_b_id
    return None, None  # events: principal participants, resolved below


def _principals(session: Session, event_ids: set[uuid.UUID]) -> dict[uuid.UUID, set[uuid.UUID]]:
    out: dict[uuid.UUID, set[uuid.UUID]] = {}
    if not event_ids:
        return out
    with session.no_autoflush:
        rows = session.execute(
            select(EventParticipant.event_id, EventParticipant.person_id).where(
                EventParticipant.event_id.in_(event_ids), EventParticipant.role == ParticipantRole.PRINCIPAL
            )
        ).all()
    for eid, pid in rows:
        out.setdefault(eid, set()).add(pid)
    return out


def _before_flush(session: Session, _ctx: Any, _instances: Any) -> None:
    if session.info.get("revisions_suppressed"):
        return
    actor = session.info.get("actor_id")
    proposal = session.info.get("proposal_id")
    reviewer = session.info.get("reviewer_id")
    tracked_new = [o for o in session.new if type(o) in TRACKED]
    tracked_dirty = [o for o in session.dirty if type(o) in TRACKED and o not in session.deleted]
    tracked_deleted = [o for o in session.deleted if type(o) in TRACKED]
    principals_new = [
        o for o in session.new if isinstance(o, EventParticipant) and o.role == ParticipantRole.PRINCIPAL
    ]
    if not (tracked_new or tracked_dirty or tracked_deleted or principals_new):
        return

    bump: set[uuid.UUID] = set()  # owning people whose revision increments
    changed_people: set[uuid.UUID] = set()  # people whose own row already incremented
    rows: list[RecordRevision] = []
    events: list[tuple[Event, RecordRevision]] = []

    def record(obj: Any, op: ProposalOp, before: dict[str, Any], after: dict[str, Any]) -> RecordRevision:
        a, b = _owners(obj)
        rev = RecordRevision(
            id=uuid7(),
            tree_id=obj.tree_id,
            record_type=TRACKED[type(obj)],
            record_id=obj.id,
            revision=obj.revision,
            op=op,
            person_id=a,
            person_b_id=b,
            before=before,
            after=after,
            actor_id=actor,
            proposal_id=proposal,
            reviewer_id=reviewer,
        )
        rows.append(rev)
        if isinstance(obj, Person):
            changed_people.add(obj.id)
        else:
            bump.update(p for p in (a, b) if p)
        if isinstance(obj, Event):
            events.append((obj, rev))
        return rev

    for obj in tracked_new:
        if obj.id is None:
            obj.id = uuid7()
        obj.revision = 1
        created = {k: _json(getattr(obj, k)) for k in _fields(obj) if getattr(obj, k) is not None}
        record(obj, ProposalOp.CREATE, {}, created)

    for obj in tracked_dirty:
        state = inspect(obj)
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}
        for key in _fields(obj):
            hist = state.attrs[key].history
            if not hist.has_changes():
                continue
            old = _json(hist.deleted[0]) if hist.deleted else None
            new = _json(hist.added[0]) if hist.added else None
            if old != new:
                before[key], after[key] = old, new
        if not after:
            continue
        if (
            not state.attrs["review_state"].history.has_changes()
            and obj.review_state != ReviewState.UNREVIEWED
        ):
            obj.review_state = ReviewState.UNREVIEWED  # a changed fact is no longer the reviewed one
            obj.review_state_by = None
            obj.review_state_at = None
        obj.revision = (obj.revision or 1) + 1
        record(obj, ProposalOp.UPDATE, before, after)

    for obj in tracked_deleted:
        before = {k: _json(getattr(obj, k)) for k in _fields(obj) if getattr(obj, k) is not None}
        obj.revision = (obj.revision or 1) + 1
        record(obj, ProposalOp.DELETE, before, {})

    # vitals and events belong to their principal participants
    existing = {e.id for e, _ in events}
    by_event = _principals(session, existing)
    for e, rev in events:
        people = sorted(by_event.get(e.id, set()), key=str)
        if people:
            rev.person_id = people[0]
            rev.person_b_id = people[1] if len(people) > 1 else None
            bump.update(people)
        else:  # a new event: its participants arrive in a later flush of this transaction
            session.info.setdefault(_PENDING_EVENTS, {})[e.id] = rev
    pending: dict[uuid.UUID, RecordRevision] = session.info.get(_PENDING_EVENTS, {})
    for part in principals_new:
        bump.add(part.person_id)
        waiting = pending.get(part.event_id)
        if waiting is not None:
            if waiting.person_id is None:
                waiting.person_id = part.person_id
            elif waiting.person_b_id is None and waiting.person_id != part.person_id:
                waiting.person_b_id = part.person_id

    for rev in rows:
        session.add(rev)
    with session.no_autoflush:
        for pid in bump - changed_people:
            person = session.get(Person, pid)
            if person is not None and person not in session.deleted:
                person.revision = (person.revision or 1) + 1


def install() -> None:
    """Attach the hook to every ORM session (idempotent)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)


@contextmanager
def suppressed(session: Session) -> Iterator[None]:
    """No revisions while erasing: the erased values must not be copied into history."""
    prev = session.info.get("revisions_suppressed")
    session.info["revisions_suppressed"] = True
    try:
        yield
    finally:
        session.info["revisions_suppressed"] = prev


@contextmanager
def applying(
    session: Session, *, actor_id: uuid.UUID | None, proposal_id: uuid.UUID, reviewer_id: uuid.UUID
) -> Iterator[None]:
    """Attribute the writes of an accepted proposal to its proposer, proposal and reviewer."""
    keys = ("actor_id", "proposal_id", "reviewer_id")
    prev = {k: session.info.get(k) for k in keys}
    session.info.update(actor_id=actor_id, proposal_id=proposal_id, reviewer_id=reviewer_id)
    try:
        yield
    finally:
        session.info.update(prev)
