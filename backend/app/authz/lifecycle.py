"""Person lifecycle: who is an *active* member of a tree (ADR-0034).

A person is in exactly one of three states:

- **active**: ``deleted_at IS NULL``. May be visible, or hidden by privacy (an anonymous placeholder
  where the privacy model allows one).
- **removed**: ``deleted_at`` set, ``erased_at IS NULL``. Restorable by a tree admin.
- **permanently deleted**: ``erased_at`` set (``deleted_at`` is set with it). An inert tombstone
  with no personal data and no relationships. Never restorable.

Removed and permanently deleted people are *absent*: no node, no edge, no placeholder, no count, and
nothing is reached through them. Every projection that follows a reference to a person (relationship,
membership, participant…) must leave these ids out *before* traversal, not after. This module is the
single place that answers "is this person still part of the tree?"; ``authz.privacy`` answers the
separate question "may this viewer see them?".
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select

from app.authz.context import TreeContext
from app.models import Person


def is_active(person: Person) -> bool:
    return person.deleted_at is None and person.erased_at is None


def inactive_person_ids(ctx: TreeContext) -> frozenset[uuid.UUID]:
    """Ids of removed and permanently deleted people in this tree (cached on the request context).

    Removed people are few compared with the tree (they are mistakes, duplicates and undone
    additions), so one indexed query per request is cheaper than a join in every traversal.
    """
    if ctx._inactive_people is None:
        ctx._inactive_people = frozenset(
            ctx.db.scalars(
                select(Person.id).where(
                    Person.tree_id == ctx.tree_id,
                    Person.deleted_at.is_not(None) | Person.erased_at.is_not(None),
                )
            )
        )
    return ctx._inactive_people


def forget(ctx: TreeContext) -> None:
    """Drop the cached set after removing, restoring or permanently deleting someone."""
    ctx._inactive_people = None


def active_only(ctx: TreeContext, person_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    return set(person_ids) - inactive_person_ids(ctx)
