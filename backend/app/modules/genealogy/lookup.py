"""Tree-scoped lookups. Every getter filters by tree_id; missing or invisible → 404."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import TypeVar

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import Subject, can_view_person, load_subjects
from app.authz.subjects import get_person_subject as _get_person_subject
from app.core.errors import NotFound
from app.models import Event, NameRecord, Person, Place, Relationship
from app.models.base import Base

M = TypeVar("M", bound=Base)


def get_in_tree(ctx: TreeContext, model: type[M], obj_id: uuid.UUID, label: str = "Resource") -> M:
    stmt = select(model).where(model.tree_id == ctx.tree_id, model.id == obj_id)  # type: ignore[attr-defined]
    obj = ctx.db.scalar(stmt)
    if obj is None:
        raise NotFound(f"{label} not found")
    return obj


def get_person_subject(ctx: TreeContext, person_id: uuid.UUID) -> Subject:
    return _get_person_subject(ctx, person_id)


def get_person(ctx: TreeContext, person_id: uuid.UUID) -> Person:
    return get_person_subject(ctx, person_id).person


def visible_subjects(ctx: TreeContext, person_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Subject]:
    """Subjects for the ids that exist, are live and are visible to the viewer."""
    ids = list(set(person_ids))
    if not ids:
        return {}
    persons = ctx.db.scalars(
        select(Person).where(Person.tree_id == ctx.tree_id, Person.id.in_(ids), Person.deleted_at.is_(None))
    ).all()
    subjects = load_subjects(ctx, persons)
    return {pid: s for pid, s in subjects.items() if can_view_person(ctx, s)}


def get_place(ctx: TreeContext, place_id: uuid.UUID) -> Place:
    return get_in_tree(ctx, Place, place_id, "Place")


def get_event(ctx: TreeContext, event_id: uuid.UUID) -> Event:
    return get_in_tree(ctx, Event, event_id, "Event")


def get_relationship(ctx: TreeContext, rel_id: uuid.UUID) -> Relationship:
    return get_in_tree(ctx, Relationship, rel_id, "Relationship")


def get_name(ctx: TreeContext, name_id: uuid.UUID) -> NameRecord:
    return get_in_tree(ctx, NameRecord, name_id, "Name")
