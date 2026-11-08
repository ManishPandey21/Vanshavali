"""Relative age between two relatives (ADR-0020 §5): family-confirmed order first, then birth dates
as the viewer may see them, otherwise unknown. Never guessed.

Used by the relationship calculator so regional terms can depend on age (Tau vs Chacha compares
the uncle with the *father*), by Smart Add, and by the "older or younger?" prompt.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import and_, or_, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.dates import GenealogicalDate
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models import RelativeAgeOrder
from app.models.enums import EventType, EvidenceStatus, ParticipantRole
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import AgeOrderOut

Order = Literal["elder", "younger"]
SIBLING_WORDS = frozenset({"brother", "sister", "sibling"})
_IGNORED_EVIDENCE = (EvidenceStatus.DISPROVEN, EvidenceStatus.SUPERSEDED)


def _recorded(ctx: TreeContext, a: uuid.UUID, b: uuid.UUID) -> RelativeAgeOrder | None:
    return ctx.db.scalar(
        select(RelativeAgeOrder).where(
            RelativeAgeOrder.tree_id == ctx.tree_id,
            or_(
                and_(RelativeAgeOrder.elder_person_id == a, RelativeAgeOrder.younger_person_id == b),
                and_(RelativeAgeOrder.elder_person_id == b, RelativeAgeOrder.younger_person_id == a),
            ),
        )
    )


def _birth_ranges(ctx: TreeContext, person_ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple | None]:
    """Each person's birth as a (from, to) date range, **as this viewer may see it** (living people's
    dates are year-only for most viewers). ``None`` when there is no usable date or when competing
    birth claims disagree: conflicting records never force an answer."""
    from app.modules.genealogy.serialize import Serializer

    subjects = lookup.visible_subjects(ctx, person_ids)
    events = Serializer(ctx).events_for(list(subjects), subjects, {EventType.BIRTH})
    out: dict[uuid.UUID, tuple | None] = {}
    for pid in person_ids:
        ranges = set()
        for e in events.get(pid, []):
            if e.evidence_status in _IGNORED_EVIDENCE or not e.date:
                continue
            if not any(p.person_id == pid and p.role == ParticipantRole.PRINCIPAL for p in e.participants):
                continue
            ranges.add(GenealogicalDate.model_validate(e.date).sort_range())
        only = ranges.pop() if len(ranges) == 1 else None
        # "before" / "after" dates have an open end: not enough to order two people
        out[pid] = only if only is not None and only[0] is not None and only[1] is not None else None
    return out


def _from_dates(a: tuple | None, b: tuple | None) -> Literal["elder", "younger", "unknown"]:
    """``a`` relative to ``b`` from non-overlapping birth ranges only."""
    if a is None or b is None:
        return "unknown"
    if a[1] < b[0]:
        return "elder"
    if b[1] < a[0]:
        return "younger"
    return "unknown"


def resolve(
    ctx: TreeContext, person_id: uuid.UUID, relative_to_id: uuid.UUID, chain_index: int = 0
) -> AgeOrderOut:
    """Age of ``person_id`` relative to ``relative_to_id``. Both must be visible to the viewer."""
    ranges = _birth_ranges(ctx, {person_id, relative_to_id})
    by_dates = _from_dates(ranges.get(person_id), ranges.get(relative_to_id))
    rec = _recorded(ctx, person_id, relative_to_id)
    if rec is not None:
        order: Order = "elder" if rec.elder_person_id == person_id else "younger"
        return AgeOrderOut(
            chain_index=chain_index,
            person_id=person_id,
            relative_to_id=relative_to_id,
            order=order,
            basis="family_confirmed",
            record_id=rec.id,
            dates_disagree=by_dates not in ("unknown", order),
        )
    return AgeOrderOut(
        chain_index=chain_index,
        person_id=person_id,
        relative_to_id=relative_to_id,
        order=by_dates,
        basis="birth_dates" if by_dates != "unknown" else "unknown",
    )


def for_sibling_hops(
    ctx: TreeContext, hops: list[tuple[str, uuid.UUID, uuid.UUID]], visible: set[uuid.UUID]
) -> list[AgeOrderOut]:
    """Age order for each sibling word of a relationship chain whose two people are both visible.
    A pair involving a hidden person is left out entirely, so nothing about them leaks."""
    out = []
    for i, (word, frm, to) in enumerate(hops):
        if word in SIBLING_WORDS and frm in visible and to in visible:
            out.append(resolve(ctx, to, frm, i))
    return out


def _are_siblings(ctx: TreeContext, a: uuid.UUID, b: uuid.UUID) -> bool:
    from app.modules.genealogy.engine import family

    return any(s.person is not None and s.person.id == b for s in family(ctx, a).siblings)


def record(
    ctx: TreeContext, person_id: uuid.UUID, relative_to_id: uuid.UUID, order: Order
) -> tuple[RelativeAgeOrder, bool]:
    """Record that ``person_id`` is ``order`` than ``relative_to_id`` (family-confirmed). Returns the
    row and whether it was created; the same order again is a no-op, the opposite one a 409."""
    if person_id == relative_to_id:
        raise Unprocessable("A person cannot be older or younger than themselves")
    lookup.get_person(ctx, person_id)
    lookup.get_person(ctx, relative_to_id)
    ctx.require(Permission.RELATIONSHIP_WRITE, person_id=person_id)
    ctx.require(Permission.RELATIONSHIP_WRITE, person_id=relative_to_id)
    elder, younger = (person_id, relative_to_id) if order == "elder" else (relative_to_id, person_id)
    existing = _recorded(ctx, elder, younger)
    if existing is not None:
        if existing.elder_person_id == elder:
            return existing, False
        raise Conflict(
            "The family has already recorded the opposite age order for these two people",
            code="age_order_conflict",
        )
    row = RelativeAgeOrder(
        tree_id=ctx.tree_id, elder_person_id=elder, younger_person_id=younger, created_by=ctx.user_id
    )
    ctx.db.add(row)
    ctx.db.flush()
    audit.log(ctx, "relative_age_order.recorded", target_type="relative_age_order", target_id=row.id)
    return row, True


def record_for_siblings(
    ctx: TreeContext, person_id: uuid.UUID, relative_to_id: uuid.UUID, order: Order
) -> tuple[RelativeAgeOrder, bool]:
    """The "older or younger?" prompt: only between people the tree records as siblings."""
    lookup.get_person(ctx, person_id)
    lookup.get_person(ctx, relative_to_id)
    if not _are_siblings(ctx, person_id, relative_to_id):
        raise Unprocessable("Age order is recorded between brothers and sisters", code="not_siblings")
    return record(ctx, person_id, relative_to_id, order)


def delete(ctx: TreeContext, record_id: uuid.UUID) -> None:
    row = ctx.db.scalar(
        select(RelativeAgeOrder).where(
            RelativeAgeOrder.tree_id == ctx.tree_id, RelativeAgeOrder.id == record_id
        )
    )
    if row is None:
        raise NotFound("Age order not found")
    # both people must be visible: a hidden person's record is not even confirmed to exist
    try:
        lookup.get_person(ctx, row.elder_person_id)
        lookup.get_person(ctx, row.younger_person_id)
    except NotFound:
        raise NotFound("Age order not found") from None
    ctx.require(Permission.RELATIONSHIP_WRITE, person_id=row.elder_person_id)
    ctx.require(Permission.RELATIONSHIP_WRITE, person_id=row.younger_person_id)
    ctx.db.delete(row)
    audit.log(ctx, "relative_age_order.deleted", target_type="relative_age_order", target_id=record_id)
