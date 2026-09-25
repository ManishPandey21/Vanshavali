"""Sources and citations (PRS §18). Citation targets are validated to live in the same tree."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import level_allows
from app.core import audit
from app.core.dates import date_to_json
from app.core.errors import NotFound
from app.models import (
    Assertion,
    AstrologyProfile,
    Citation,
    Event,
    EventParticipant,
    Household,
    LandParcel,
    NameRecord,
    Person,
    Property,
    PropertyEvent,
    PropertyInterest,
    Relationship,
    Source,
)
from app.models.enums import CitationTarget, ParticipantRole, SourceType
from app.modules.evidence.schemas import CitationIn, SourceIn, SourceUpdate
from app.modules.genealogy import lookup

_TARGET_MODELS = {
    CitationTarget.PERSON: Person,
    CitationTarget.NAME_RECORD: NameRecord,
    CitationTarget.EVENT: Event,
    CitationTarget.RELATIONSHIP: Relationship,
    CitationTarget.ASSERTION: Assertion,
    CitationTarget.ASTROLOGY_PROFILE: AstrologyProfile,
    CitationTarget.PROPERTY: Property,
    CitationTarget.LAND_PARCEL: LandParcel,
    CitationTarget.PROPERTY_INTEREST: PropertyInterest,
    CitationTarget.PROPERTY_EVENT: PropertyEvent,
    CitationTarget.HOUSEHOLD: Household,
}

_PROPERTY_TARGETS = {
    CitationTarget.PROPERTY,
    CitationTarget.LAND_PARCEL,
    CitationTarget.PROPERTY_INTEREST,
    CitationTarget.PROPERTY_EVENT,
}


def can_view_source(ctx: TreeContext, s: Source) -> bool:
    return level_allows(ctx, s.privacy_level)


def get_source(ctx: TreeContext, source_id: uuid.UUID) -> Source:
    s = lookup.get_in_tree(ctx, Source, source_id, "Source")
    if not can_view_source(ctx, s):
        raise NotFound("Source not found")
    return s


def create_source(ctx: TreeContext, body: SourceIn) -> Source:
    ctx.require(Permission.SOURCE_WRITE)
    if body.place_id:
        lookup.get_place(ctx, body.place_id)
    if body.document_id:
        from app.models import Document

        lookup.get_in_tree(ctx, Document, body.document_id, "Document")
    data = body.model_dump(mode="json", exclude={"date", "tradition", "place_id", "document_id"})
    s = Source(
        tree_id=ctx.tree_id,
        created_by=ctx.user_id,
        place_id=body.place_id,
        document_id=body.document_id,
        date=date_to_json(body.date),
        tradition=body.tradition.model_dump(exclude_none=True) if body.tradition else None,
        **data,
    )
    ctx.db.add(s)
    ctx.db.flush()
    audit.log(ctx, "source.created", target_type="source", target_id=s.id)
    return s


def update_source(ctx: TreeContext, source_id: uuid.UUID, body: SourceUpdate) -> Source:
    ctx.require(Permission.SOURCE_WRITE)
    s = get_source(ctx, source_id)
    for f in body.model_fields_set:
        v = getattr(body, f)
        if f == "date":
            v = date_to_json(v)
        elif f == "tradition":
            v = v.model_dump(exclude_none=True) if v else None
        elif f == "place_id" and v is not None:
            lookup.get_place(ctx, v)
        setattr(s, f, v)
    s.updated_by = ctx.user_id
    audit.log(
        ctx,
        "source.changed",
        target_type="source",
        target_id=s.id,
        details={"fields": sorted(body.model_fields_set)},
    )
    return s


def ensure_document_source(
    ctx: TreeContext,
    document_id: uuid.UUID,
    title: str,
    source_type: SourceType,
    issuing_authority: str | None = None,
) -> Source:
    """One Source per uploaded document (created lazily when a fact cites it)."""
    s = ctx.db.scalar(select(Source).where(Source.tree_id == ctx.tree_id, Source.document_id == document_id))
    if s is None:
        from app.models import Document

        doc = lookup.get_in_tree(ctx, Document, document_id, "Document")
        s = Source(
            tree_id=ctx.tree_id,
            source_type=source_type,
            title=title,
            issuing_authority=issuing_authority,
            document_id=document_id,
            privacy_level=doc.privacy_level,
            created_by=ctx.user_id,
        )
        ctx.db.add(s)
        ctx.db.flush()
    return s


def _check_target_visible(ctx: TreeContext, target_type: CitationTarget, target_id: uuid.UUID) -> None:
    model = _TARGET_MODELS[target_type]
    obj: Any = lookup.get_in_tree(ctx, model, target_id, "Citation target")
    person_id: uuid.UUID | None = None
    if target_type == CitationTarget.PERSON:
        person_id = obj.id
    elif (
        target_type in (CitationTarget.NAME_RECORD, CitationTarget.ASTROLOGY_PROFILE)
        or target_type == CitationTarget.ASSERTION
    ):
        person_id = obj.person_id  # type: ignore[attr-defined]
    elif target_type == CitationTarget.EVENT:
        person_id = ctx.db.scalar(
            select(EventParticipant.person_id)
            .where(
                EventParticipant.tree_id == ctx.tree_id,
                EventParticipant.event_id == target_id,
                EventParticipant.role == ParticipantRole.PRINCIPAL,
            )
            .limit(1)
        )
    elif target_type == CitationTarget.RELATIONSHIP:
        lookup.get_person(ctx, obj.person_a_id)  # type: ignore[attr-defined]
        person_id = obj.person_b_id  # type: ignore[attr-defined]
    if person_id is not None:
        lookup.get_person(ctx, person_id)
    if target_type in _PROPERTY_TARGETS and not ctx.has(Permission.PROPERTY_READ):
        raise NotFound("Citation target not found")


def add_citation(ctx: TreeContext, body: CitationIn, *, check_permission: bool = True) -> Citation:
    if check_permission:
        ctx.require(Permission.SOURCE_WRITE)
    get_source(ctx, body.source_id)
    _check_target_visible(ctx, body.target_type, body.target_id)
    c = Citation(tree_id=ctx.tree_id, created_by=ctx.user_id, **body.model_dump())
    ctx.db.add(c)
    ctx.db.flush()
    audit.log(ctx, "citation.added", target_type=body.target_type.value, target_id=body.target_id)
    return c


def citations_for(
    ctx: TreeContext, target_type: CitationTarget, target_id: uuid.UUID
) -> list[tuple[Citation, Source]]:
    _check_target_visible(ctx, target_type, target_id)
    rows = ctx.db.execute(
        select(Citation, Source)
        .join(Source, (Source.id == Citation.source_id) & (Source.tree_id == Citation.tree_id))
        .where(
            Citation.tree_id == ctx.tree_id,
            Citation.target_type == target_type,
            Citation.target_id == target_id,
        )
        .order_by(Citation.created_at)
    ).all()
    return [(c, s) for c, s in rows if can_view_source(ctx, s)]


def citation_count(ctx: TreeContext, source_id: uuid.UUID) -> int:
    return int(
        ctx.db.scalar(
            select(func.count())
            .select_from(Citation)
            .where(Citation.tree_id == ctx.tree_id, Citation.source_id == source_id)
        )
        or 0
    )
