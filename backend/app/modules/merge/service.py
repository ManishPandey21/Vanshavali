"""Reversible person merge (PRS §24, §53).

A merge re-points every reference from the merged person to the survivor. Rows that would become
duplicates (or self-relationships) are snapshotted and removed. Every change is written to
``MergeRecord.changes`` so the merge can be undone. Merging requires tree-admin approval.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Conflict, Unprocessable
from app.models import (
    AccessGrant,
    Assertion,
    AstrologyProfile,
    BranchMembership,
    Citation,
    ConsentRecord,
    DocumentLink,
    EventParticipant,
    ExtractionProposal,
    FamilyBranch,
    GedcomExtension,
    HouseholdMembership,
    MergeRecord,
    NameRecord,
    Person,
    ProfileClaim,
    PropertyInterest,
    Relationship,
    TreeMembership,
)
from app.models.base import Base
from app.models.enums import SYMMETRIC_TYPES, CitationTarget, DocumentLinkTarget, GrantResource
from app.modules.genealogy import lookup

# (model, column, optional polymorphic filter)
_REFS: list[tuple[type[Base], str, tuple[str, Any] | None]] = [
    (NameRecord, "person_id", None),
    (EventParticipant, "person_id", None),
    (Assertion, "person_id", None),
    (AstrologyProfile, "person_id", None),
    (HouseholdMembership, "person_id", None),
    (BranchMembership, "person_id", None),
    (PropertyInterest, "holder_person_id", None),
    (GedcomExtension, "person_id", None),
    (ConsentRecord, "subject_person_id", None),
    (ProfileClaim, "person_id", None),
    (TreeMembership, "linked_person_id", None),
    (FamilyBranch, "founder_person_id", None),
    (ExtractionProposal, "subject_person_id", None),
    (Citation, "target_id", ("target_type", CitationTarget.PERSON)),
    (DocumentLink, "target_id", ("target_type", DocumentLinkTarget.PERSON)),
    (AccessGrant, "resource_id", ("resource_type", GrantResource.PERSON)),
]
_MODELS = {m.__tablename__: m for m, _, _ in _REFS} | {
    "relationship": Relationship,
    "name_record": NameRecord,
}


def _snapshot(obj: Base) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for attr in inspect(obj).mapper.column_attrs:
        v = getattr(obj, attr.key)
        if isinstance(v, uuid.UUID):
            v = {"$uuid": str(v)}
        elif isinstance(v, dt.datetime):
            v = {"$dt": v.isoformat()}
        elif isinstance(v, dt.date):
            v = {"$d": v.isoformat()}
        elif hasattr(v, "value") and not isinstance(v, (int, float, str)):
            v = v.value
        out[attr.key] = v
    return out


def _restore(model: type[Base], snap: dict[str, Any]) -> Base:
    vals: dict[str, Any] = {}
    for k, v in snap.items():
        if isinstance(v, dict) and "$uuid" in v:
            v = uuid.UUID(v["$uuid"])
        elif isinstance(v, dict) and "$dt" in v:
            v = dt.datetime.fromisoformat(v["$dt"])
        elif isinstance(v, dict) and "$d" in v:
            v = dt.date.fromisoformat(v["$d"])
        vals[k] = v
    return model(**vals)


def _try_update(db: Session, obj: Base, values: dict[str, Any]) -> bool:
    old = {k: getattr(obj, k) for k in values}
    try:
        with db.begin_nested():
            for k, v in values.items():
                setattr(obj, k, v)
            db.flush()
        return True
    except IntegrityError:
        db.expire(obj)
        for k, v in old.items():
            setattr(obj, k, v)
        return False


def preview(ctx: TreeContext, survivor_id: uuid.UUID, merged_id: uuid.UUID) -> dict[str, Any]:
    survivor = lookup.get_person(ctx, survivor_id)
    merged = lookup.get_person(ctx, merged_id)
    if survivor.id == merged.id:
        raise Unprocessable("Choose two different people")
    counts: dict[str, int] = {}
    for model, col, poly in _REFS:
        q = select(model).where(model.tree_id == ctx.tree_id, getattr(model, col) == merged.id)  # type: ignore[attr-defined]
        if poly:
            q = q.where(getattr(model, poly[0]) == poly[1])
        n = len(ctx.db.scalars(q).all())
        if n:
            counts[model.__tablename__] = n
    rels = ctx.db.scalars(
        select(Relationship).where(
            Relationship.tree_id == ctx.tree_id,
            (Relationship.person_a_id == merged.id) | (Relationship.person_b_id == merged.id),
        )
    ).all()
    between = [r for r in rels if survivor.id in (r.person_a_id, r.person_b_id)]
    return {
        "survivor_id": survivor.id,
        "merged_id": merged.id,
        "references_to_move": counts,
        "relationships_to_move": len(rels) - len(between),
        "relationships_between_them_removed": len(between),
        "warnings": ["Sex at birth differs"]
        if survivor.sex_at_birth and merged.sex_at_birth and survivor.sex_at_birth != merged.sex_at_birth
        else [],
    }


def merge(ctx: TreeContext, survivor_id: uuid.UUID, merged_id: uuid.UUID, reason: str | None) -> MergeRecord:
    ctx.require(Permission.TREE_MANAGE)  # privileged approval (PRS §53)
    survivor = lookup.get_person(ctx, survivor_id)
    merged = lookup.get_person(ctx, merged_id)
    if survivor.id == merged.id:
        raise Unprocessable("Choose two different people")
    db = ctx.db
    changes: list[dict[str, Any]] = []

    for model, col, poly in _REFS:
        q = select(model).where(model.tree_id == ctx.tree_id, getattr(model, col) == merged.id)  # type: ignore[attr-defined]
        if poly:
            q = q.where(getattr(model, poly[0]) == poly[1])
        for obj in db.scalars(q).all():
            extra: dict[str, Any] = {}
            if model is NameRecord and obj.is_preferred:  # type: ignore[attr-defined]
                extra["is_preferred"] = False
            old = {col: str(merged.id), **{k: getattr(obj, k) for k in extra}}
            if _try_update(db, obj, {col: survivor.id, **extra}):
                changes.append(
                    {
                        "op": "update",
                        "table": model.__tablename__,
                        "id": str(obj.id),  # type: ignore[attr-defined]
                        "old": old,
                        "new": {col: str(survivor.id), **extra},
                    }
                )
            else:
                changes.append({"op": "delete", "table": model.__tablename__, "row": _snapshot(obj)})
                db.delete(obj)
                db.flush()

    rels = db.scalars(
        select(Relationship).where(
            Relationship.tree_id == ctx.tree_id,
            (Relationship.person_a_id == merged.id) | (Relationship.person_b_id == merged.id),
        )
    ).all()
    # children linked to unions that will be deleted must be detached first
    for r in rels:
        a = survivor.id if r.person_a_id == merged.id else r.person_a_id
        b = survivor.id if r.person_b_id == merged.id else r.person_b_id
        if r.type in SYMMETRIC_TYPES and str(a) > str(b):
            a, b = b, a
        old = {"person_a_id": str(r.person_a_id), "person_b_id": str(r.person_b_id)}
        if a == b or not _try_update(db, r, {"person_a_id": a, "person_b_id": b}):
            for child in db.scalars(
                select(Relationship).where(Relationship.tree_id == ctx.tree_id, Relationship.union_id == r.id)
            ).all():
                changes.append(
                    {
                        "op": "update",
                        "table": "relationship",
                        "id": str(child.id),
                        "old": {"union_id": str(r.id)},
                        "new": {"union_id": None},
                    }
                )
                child.union_id = None
            db.flush()
            changes.append({"op": "delete", "table": "relationship", "row": _snapshot(r)})
            db.delete(r)
            db.flush()
        else:
            changes.append(
                {
                    "op": "update",
                    "table": "relationship",
                    "id": str(r.id),
                    "old": old,
                    "new": {"person_a_id": str(a), "person_b_id": str(b)},
                }
            )

    merged.deleted_at = dt.datetime.now(dt.UTC)
    merged.merged_into_id = survivor.id
    rec = MergeRecord(
        tree_id=ctx.tree_id,
        survivor_id=survivor.id,
        merged_id=merged.id,
        reason=reason,
        changes=changes,
        created_by=ctx.user_id,
    )
    db.add(rec)
    db.flush()
    audit.log(
        ctx,
        "person.merged",
        target_type="person",
        target_id=survivor.id,
        details={"merged_id": str(merged.id), "changes": len(changes)},
    )
    return rec


def _coerce(model: type[Base], col: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and col.endswith("_id"):
        return uuid.UUID(value)
    return value


def revert(ctx: TreeContext, merge_id: uuid.UUID) -> MergeRecord:
    ctx.require(Permission.TREE_MANAGE)
    rec = lookup.get_in_tree(ctx, MergeRecord, merge_id, "Merge")
    if rec.reverted_at is not None:
        raise Conflict("This merge has already been undone", code="already_reverted")
    db = ctx.db
    merged = lookup.get_in_tree(ctx, Person, rec.merged_id, "Person")
    merged.deleted_at = None
    merged.merged_into_id = None
    db.flush()
    # undo in reverse order: recreate deleted rows, restore updated columns
    for ch in reversed(rec.changes):
        model = _MODELS[ch["table"]]
        if ch["op"] == "delete":
            db.add(_restore(model, ch["row"]))
            db.flush()
        else:
            obj = db.get(model, uuid.UUID(ch["id"]))
            if obj is None:
                continue  # removed since the merge; nothing to restore
            for col, v in ch["old"].items():
                setattr(obj, col, _coerce(model, col, v))
            db.flush()
    rec.reverted_at = dt.datetime.now(dt.UTC)
    rec.reverted_by = ctx.user_id
    audit.log(
        ctx,
        "person.merge_reverted",
        target_type="person",
        target_id=rec.survivor_id,
        details={"merged_id": str(rec.merged_id)},
    )
    return rec
