"""Heritage assertions and profiles (PRS §13; ADR-0003).

INVARIANT (PRS §2.3, §58 "Gotra"): nothing in this module — or anywhere else — derives heritage
values from surnames, places, languages or relatives. Assertions are created only from explicit
user input or reviewed extraction proposals.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import FieldGroup, Subject, can_view_field, level_allows
from app.core import audit
from app.core.errors import NotFound, Unprocessable
from app.models import Assertion, FamilyBranch, Place
from app.models.enums import (
    AssertionSubject,
    CitationTarget,
    HeritageAttribute,
    PrivacyLevel,
    Role,
    ValueStatus,
)
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import ProvenanceOut
from app.modules.genealogy.serialize import citation_counts
from app.modules.heritage.schemas import (
    AssertionIn,
    AssertionOut,
    AssertionUpdate,
    HeritageAttributeView,
    HeritageProfileOut,
)

ATTRIBUTE_GROUP = {
    HeritageAttribute.JATI_OR_SUBGROUP.value: FieldGroup.JATI,
    HeritageAttribute.COMMUNITY.value: FieldGroup.COMMUNITY,
    HeritageAttribute.RELIGION.value: FieldGroup.RELIGION,
}


def _group(attribute: str) -> str:
    return ATTRIBUTE_GROUP.get(attribute, FieldGroup.HERITAGE)


def _visible(ctx: TreeContext, a: Assertion, subject: Subject | None) -> bool:
    if subject is not None:
        if not can_view_field(ctx, subject, _group(a.attribute)):
            return False
        if a.privacy_level is not None and not level_allows(ctx, a.privacy_level, subject=subject):
            return False
        return True
    # branch assertions
    if a.attribute in ATTRIBUTE_GROUP:
        default = (
            PrivacyLevel.PRIVATE_TREE_ADMINS
            if a.attribute == HeritageAttribute.JATI_OR_SUBGROUP.value
            else PrivacyLevel.TREE_MEMBERS
        )
        return level_allows(ctx, a.privacy_level or default)
    return level_allows(ctx, a.privacy_level or PrivacyLevel.TREE_MEMBERS)


def _out(
    ctx: TreeContext, a: Assertion, places: dict[uuid.UUID, str], counts: dict[uuid.UUID, int]
) -> AssertionOut:
    o = AssertionOut.model_validate(a)
    return o.model_copy(
        update={
            "place_name": places.get(a.place_id) if a.place_id else None,
            "provenance": None if ctx.public else ProvenanceOut.of(a),
            "citation_count": counts.get(a.id, 0),
        }
    )


def _resolve_subject(
    ctx: TreeContext, subject_type: AssertionSubject, subject_id: uuid.UUID
) -> Subject | None:
    if subject_type == AssertionSubject.PERSON:
        return lookup.get_person_subject(ctx, subject_id)
    lookup.get_in_tree(ctx, FamilyBranch, subject_id, "Branch")
    return None


def create_assertion(
    ctx: TreeContext,
    subject_type: AssertionSubject,
    subject_id: uuid.UUID,
    body: AssertionIn,
    **provenance: Any,
) -> Assertion:
    _resolve_subject(ctx, subject_type, subject_id)
    if subject_type == AssertionSubject.PERSON:
        ctx.require(Permission.ASSERTION_WRITE, person_id=subject_id)
    else:
        ctx.require(Permission.FAMILY_WRITE)
    if body.place_id:
        lookup.get_place(ctx, body.place_id)
    researcher_only = ctx.roles <= {Role.RESEARCHER}
    a = Assertion(
        tree_id=ctx.tree_id,
        subject_type=subject_type,
        person_id=subject_id if subject_type == AssertionSubject.PERSON else None,
        branch_id=subject_id if subject_type == AssertionSubject.BRANCH else None,
        attribute=body.attribute.value,
        value_text=(body.value_text or "").strip() or None,
        value_json=body.value_json,
        place_id=body.place_id,
        value_status=body.value_status,
        evidence_status=body.evidence_status,
        confidence=body.confidence,
        privacy_level=body.privacy_level,
        notes=body.notes,
        created_by=ctx.user_id,
        **provenance,
    )
    existing = _assertions(ctx, subject_type, subject_id, body.attribute.value)
    has_preferred = any(e.is_preferred for e in existing)
    if researcher_only:
        a.is_preferred = False  # researchers propose; admins/contributors decide (PRS §5)
    elif body.is_preferred is None:
        a.is_preferred = not has_preferred
    else:
        a.is_preferred = body.is_preferred
    ctx.db.add(a)
    ctx.db.flush()
    if a.is_preferred:
        for e in existing:
            if e.id != a.id:
                e.is_preferred = False
    audit.log(
        ctx,
        "heritage.assertion_added",
        target_type=subject_type.value,
        target_id=subject_id,
        details={"attribute": a.attribute, "evidence_status": a.evidence_status.value},
    )
    return a


def _assertions(
    ctx: TreeContext, subject_type: AssertionSubject, subject_id: uuid.UUID, attribute: str | None = None
) -> list[Assertion]:
    col = Assertion.person_id if subject_type == AssertionSubject.PERSON else Assertion.branch_id
    q = select(Assertion).where(Assertion.tree_id == ctx.tree_id, col == subject_id)
    if attribute:
        q = q.where(Assertion.attribute == attribute)
    return list(ctx.db.scalars(q.order_by(Assertion.created_at)))


def get_assertion(ctx: TreeContext, assertion_id: uuid.UUID) -> tuple[Assertion, Subject | None]:
    a = lookup.get_in_tree(ctx, Assertion, assertion_id, "Assertion")
    subject = _resolve_subject(ctx, a.subject_type, a.person_id or a.branch_id)  # type: ignore[arg-type]
    if not _visible(ctx, a, subject):
        raise NotFound("Assertion not found")
    return a, subject


def update_assertion(ctx: TreeContext, assertion_id: uuid.UUID, body: AssertionUpdate) -> Assertion:
    a, _subject = get_assertion(ctx, assertion_id)
    if a.subject_type == AssertionSubject.PERSON:
        ctx.require(Permission.ASSERTION_WRITE, person_id=a.person_id)
    else:
        ctx.require(Permission.FAMILY_WRITE)
    researcher_only = ctx.roles <= {Role.RESEARCHER}
    if researcher_only and (a.created_by != ctx.user_id or body.is_preferred):
        from app.core.errors import Forbidden

        raise Forbidden("Researchers may only edit their own proposals and cannot mark values preferred")
    for f in body.model_fields_set - {"is_preferred"}:
        setattr(a, f, getattr(body, f))
    has_value = bool(a.value_text) or a.value_json is not None or a.place_id is not None
    if a.value_status == ValueStatus.KNOWN and not has_value:
        raise Unprocessable("a known value needs value_text, value_json or place_id")
    if body.is_preferred is not None:
        a.is_preferred = body.is_preferred
        if body.is_preferred:
            for e in _assertions(ctx, a.subject_type, a.person_id or a.branch_id, a.attribute):  # type: ignore[arg-type]
                if e.id != a.id:
                    e.is_preferred = False
    a.updated_by = ctx.user_id
    audit.log(
        ctx,
        "heritage.assertion_changed",
        target_type=a.subject_type.value,
        target_id=a.person_id or a.branch_id,
        details={"attribute": a.attribute, "fields": sorted(body.model_fields_set)},
    )
    return a


def delete_assertion(ctx: TreeContext, assertion_id: uuid.UUID) -> None:
    a, _ = get_assertion(ctx, assertion_id)
    if a.subject_type == AssertionSubject.PERSON:
        ctx.require(Permission.PERSON_WRITE, person_id=a.person_id)
    else:
        ctx.require(Permission.FAMILY_WRITE)
    ctx.db.delete(a)
    audit.log(
        ctx,
        "heritage.assertion_removed",
        target_type=a.subject_type.value,
        target_id=a.person_id or a.branch_id,
        details={"attribute": a.attribute},
    )


def profile(ctx: TreeContext, subject_type: AssertionSubject, subject_id: uuid.UUID) -> HeritageProfileOut:
    subject = _resolve_subject(ctx, subject_type, subject_id)
    rows = _assertions(ctx, subject_type, subject_id)
    place_ids = {a.place_id for a in rows if a.place_id}
    places = (
        {
            p.id: p.canonical_name
            for p in ctx.db.scalars(
                select(Place).where(Place.tree_id == ctx.tree_id, Place.id.in_(place_ids))
            )
        }
        if place_ids
        else {}
    )
    counts = citation_counts(ctx, CitationTarget.ASSERTION, {a.id for a in rows})
    by_attr: dict[str, list[Assertion]] = {}
    withheld: set[str] = set()
    for a in rows:
        if _visible(ctx, a, subject):
            by_attr.setdefault(a.attribute, []).append(a)
        else:
            withheld.add(a.attribute)
    views = []
    for attr, items in by_attr.items():
        preferred = next((a for a in items if a.is_preferred), None)
        alts = [a for a in items if a is not preferred]
        live_values = {
            (a.value_text or "").strip().lower() or str(a.value_json) or str(a.place_id)
            for a in items
            if a.value_status == ValueStatus.KNOWN
            and a.evidence_status.value not in ("DISPROVEN", "SUPERSEDED")
        }
        disputed = len(live_values) > 1 or any(a.evidence_status.value == "DISPUTED" for a in items)
        views.append(
            HeritageAttributeView(
                attribute=attr,
                preferred=_out(ctx, preferred, places, counts) if preferred else None,
                alternatives=[] if ctx.public else [_out(ctx, a, places, counts) for a in alts],
                disputed=disputed,
            )
        )
    order = [a.value for a in HeritageAttribute]
    views.sort(key=lambda v: order.index(v.attribute) if v.attribute in order else 999)
    return HeritageProfileOut(
        subject_type=subject_type,
        subject_id=subject_id,
        attributes=views,
        withheld_attributes=[] if ctx.public else sorted(withheld - set(by_attr)),
    )
