"""Exact share arithmetic and the documented-ownership invariant (ADR-0010).

Shares are rational numbers (``fractions.Fraction``) built from the stored numerator/denominator;
floats are never used for share arithmetic.

Invariant: at every moment, the *active* ``owner``/``co_owner`` interests with status
``documented`` add up to at most 1:

* property-wide interests (``parcel_id`` is null) on their own must be ≤ 1, and
* for every parcel, the property-wide interests **plus** that parcel's own interests must be ≤ 1.

Asserted, disputed and unknown-status claims are ignored here: overlapping claims are how
disputes appear. An interest is active at ``d`` when ``valid_from_sort <= d < valid_to_sort``
(a missing bound is open). Sums only grow at start dates, so checking every start date (plus
"the beginning of time") covers the whole timeline.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Protocol

from app.models.enums import OWNERSHIP_INTERESTS, InterestStatus, InterestType


class ShareLike(Protocol):
    id: uuid.UUID
    parcel_id: uuid.UUID | None
    interest_type: InterestType
    status: InterestStatus
    share_numerator: int
    share_denominator: int
    valid_from_sort: dt.date | None
    valid_to_sort: dt.date | None


def share_of(obj: Any) -> Fraction:
    return Fraction(int(obj.share_numerator), int(obj.share_denominator))


def fraction_str(f: Fraction) -> str:
    return f"{f.numerator}/{f.denominator}"


def active_at(obj: Any, at: dt.date | None) -> bool:
    """Half-open validity window [valid_from, valid_to). ``at=None`` means 'before any known date'."""
    lo, hi = obj.valid_from_sort, obj.valid_to_sort
    if at is None:
        return lo is None
    if lo is not None and lo > at:
        return False
    return not (hi is not None and hi <= at)


def counts_for_invariant(obj: Any) -> bool:
    return obj.interest_type in OWNERSHIP_INTERESTS and obj.status == InterestStatus.DOCUMENTED


@dataclass
class ShareViolation:
    at: dt.date | None
    scope: str  # property | parcel
    parcel_id: uuid.UUID | None
    total: Fraction
    interest_ids: list[uuid.UUID]

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat() if self.at else None,
            "scope": self.scope,
            "parcel_id": str(self.parcel_id) if self.parcel_id else None,
            "total": fraction_str(self.total),
            "interest_ids": [str(i) for i in self.interest_ids],
        }


def _active_for_checkpoint(items: list[Any], at: dt.date | None) -> list[Any]:
    # at=None is "the beginning of time": interests without a known start date
    return [i for i in items if active_at(i, at)]


def find_violations(interests: Iterable[Any]) -> list[ShareViolation]:
    items = [i for i in interests if counts_for_invariant(i)]
    checkpoints: set[dt.date | None] = {None}
    checkpoints |= {i.valid_from_sort for i in items if i.valid_from_sort is not None}
    out: list[ShareViolation] = []
    seen: set[tuple[str, uuid.UUID | None, frozenset[uuid.UUID]]] = set()
    for at in sorted(checkpoints, key=lambda d: d or dt.date.min):
        active = _active_for_checkpoint(items, at)
        wide = [i for i in active if i.parcel_id is None]
        wide_total = sum((share_of(i) for i in wide), Fraction(0))
        per_parcel: dict[uuid.UUID, list[Any]] = defaultdict(list)
        for i in active:
            if i.parcel_id is not None:
                per_parcel[i.parcel_id].append(i)
        candidates: list[tuple[str, uuid.UUID | None, list[Any], Fraction]] = []
        if wide_total > 1:
            candidates.append(("property", None, wide, wide_total))
        for pid, lst in per_parcel.items():
            total = wide_total + sum((share_of(i) for i in lst), Fraction(0))
            if total > 1:
                candidates.append(("parcel", pid, wide + lst, total))
        for scope, scope_parcel, lst, total in candidates:
            key = (scope, scope_parcel, frozenset(i.id for i in lst))
            if key in seen:
                continue
            seen.add(key)
            out.append(ShareViolation(at, scope, scope_parcel, total, sorted(i.id for i in lst)))
    return out


def documented_total(
    interests: Iterable[Any], at: dt.date | None, parcel_id: uuid.UUID | None = None
) -> Fraction:
    """Sum of active documented ownership shares at ``at`` (property-wide, plus one parcel if given)."""
    total = Fraction(0)
    for i in interests:
        if not counts_for_invariant(i):
            continue
        if at is not None and not active_at(i, at):
            continue
        if i.parcel_id is None or (parcel_id is not None and i.parcel_id == parcel_id):
            total += share_of(i)
    return total
