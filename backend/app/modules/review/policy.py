"""Which direct writes need family review (ADR-0021 §1, §4).

Called by the write services right after their permission check, so every caller is covered.
A write needs review when the tree's ``review_policy`` covers it, the member may not review the
people concerned, and the record is not the member's own still-unreviewed work. Adding new people
never needs review: people created earlier in the same request are remembered in ``db.info``.
Applying an accepted proposal (``db.info["applying_proposal"]``) is the reviewed path itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Literal

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core.errors import Conflict
from app.models.enums import ReviewPolicy, ReviewState

Category = Literal["structure", "all"]
NEW_PEOPLE = "review_new_person_ids"
APPLYING = "applying_proposal"


def remember_new_person(ctx: TreeContext, person_id: uuid.UUID) -> None:
    ctx.db.info.setdefault(NEW_PEOPLE, set()).add(person_id)


def is_new_person(ctx: TreeContext, person_id: uuid.UUID) -> bool:
    return person_id in ctx.db.info.get(NEW_PEOPLE, set())


def can_review(ctx: TreeContext, person_ids: Iterable[uuid.UUID | None]) -> bool:
    """change.review over every person concerned (branch admins: only inside their branch)."""
    if not ctx.has(Permission.CHANGE_REVIEW):
        return False
    if ctx.branch_scope is None:
        return True
    branch = ctx.branch_people()
    return all(p in branch for p in person_ids if p is not None)


def covers(ctx: TreeContext, category: Category) -> bool:
    policy = ctx.tree.review_policy
    return policy == ReviewPolicy.ALL or (policy == ReviewPolicy.STRUCTURE and category == "structure")


def _own_unreviewed(ctx: TreeContext, records: list[Any]) -> bool:
    return bool(records) and all(
        getattr(r, "created_by", None) == ctx.user_id
        and ctx.user_id is not None
        and getattr(r, "review_state", ReviewState.UNREVIEWED) == ReviewState.UNREVIEWED
        for r in records
    )


def needs_review(
    ctx: TreeContext, category: Category, person_ids: Iterable[uuid.UUID | None], records: list[Any]
) -> bool:
    if ctx.db.info.get(APPLYING) or not covers(ctx, category):
        return False
    people = list(person_ids)
    return not can_review(ctx, people) and not _own_unreviewed(ctx, records)


def require_direct(
    ctx: TreeContext, category: Category, person_ids: Iterable[uuid.UUID | None], records: list[Any]
) -> None:
    """Raise 409 review_required when this write must go through a proposal instead."""
    if needs_review(ctx, category, person_ids, records):
        raise Conflict(
            "This family reviews changes like this one. Send it as a proposed change instead.",
            code="review_required",
            details={"review_policy": ctx.tree.review_policy.value, "category": category},
        )
