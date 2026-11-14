"""Tree-scoped person subjects used by central authorization policies."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import Subject, can_view_person, load_subjects
from app.core.errors import NotFound
from app.models import Person


def get_person_subject(ctx: TreeContext, person_id: uuid.UUID) -> Subject:
    """Return a visible person subject without depending on a domain module."""
    person = ctx.db.scalar(
        select(Person).where(
            Person.tree_id == ctx.tree_id,
            Person.id == person_id,
            Person.deleted_at.is_(None),
            Person.erased_at.is_(None),
        )
    )
    if person is None:
        raise NotFound("Person not found")
    subject = load_subjects(ctx, [person])[person.id]
    if not can_view_person(ctx, subject):
        raise NotFound("Person not found")
    return subject
