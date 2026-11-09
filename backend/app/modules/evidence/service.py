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
    TraditionEntry,
)
from app.models.enums import CitationTarget, ParticipantRole, PrivacyLevel, SourceType
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
    CitationTarget.TRADITION: TraditionEntry,
}

_PROPERTY_TARGETS = {
    CitationTarget.PROPERTY,
    CitationTarget.LAND_PARCEL,
    CitationTarget.PROPERTY_INTEREST,
    CitationTarget.PROPERTY_EVENT,
}


SYSTEM_SOURCE_MARKER = "Vanshavali document vault"


def can_view_source(ctx: TreeContext, s: Source) -> bool:
    """A source about a private record (ADR-0027) is seen exactly by those who see that record, so a
    citation never reveals it; any other source follows its own level."""
    if s.document_id is not None:
        from app.authz.privacy import is_private_record_level
        from app.models import Document
        from app.modules.documents.access import can_view_document

        doc = ctx.db.get(Document, s.document_id)
        if doc is not None and doc.tree_id == ctx.tree_id and is_private_record_level(doc.privacy_level):
            return can_view_document(ctx, doc)
    return level_allows(ctx, s.privacy_level)


def source_level_for(level: str) -> PrivacyLevel:
    """The stored level of a document's system source. Private record audiences have no person-level
    equivalent; their sources are evaluated through the document (``can_view_source``)."""
    private = {"ONLY_ME": PrivacyLevel.PRIVATE_SELF, "SELECTED_MEMBERS": PrivacyLevel.CUSTOM}
    return private.get(str(level)) or PrivacyLevel(str(level))


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
        # SEC-5: binding a source to a document requires the right to read that document's content
        from app.modules.documents import access as doc_access

        doc_access.require_content(ctx, doc_access.get_document(ctx, body.document_id))
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
    """The system source for an uploaded document (created lazily when a fact cites it).

    SEC-5: only a source created by this function (``repository`` marker) at the document's own
    privacy level is reused — never a user-created source that merely points at the document.
    """
    from app.models import Document

    doc = lookup.get_in_tree(ctx, Document, document_id, "Document")
    s = ctx.db.scalar(
        select(Source).where(
            Source.tree_id == ctx.tree_id,
            Source.document_id == document_id,
            Source.repository == SYSTEM_SOURCE_MARKER,
            Source.privacy_level == source_level_for(doc.privacy_level),
        )
    )
    if s is None:
        s = Source(
            tree_id=ctx.tree_id,
            source_type=source_type,
            title=title,
            issuing_authority=issuing_authority,
            document_id=document_id,
            repository=SYSTEM_SOURCE_MARKER,
            privacy_level=source_level_for(doc.privacy_level),
            created_by=ctx.user_id,
        )
        ctx.db.add(s)
        ctx.db.flush()
    return s


def _check_target_visible(ctx: TreeContext, target_type: CitationTarget, target_id: uuid.UUID) -> None:
    if target_type == CitationTarget.TRADITION:
        from app.modules.traditions.service import get_entry

        get_entry(ctx, target_id)  # the entry's own privacy level
        return
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


_TARGET_WRITE = {
    CitationTarget.PROPERTY: Permission.PROPERTY_WRITE,
    CitationTarget.LAND_PARCEL: Permission.PROPERTY_WRITE,
    CitationTarget.PROPERTY_INTEREST: Permission.PROPERTY_WRITE,
    CitationTarget.PROPERTY_EVENT: Permission.PROPERTY_WRITE,
    CitationTarget.HOUSEHOLD: Permission.FAMILY_WRITE,
    CitationTarget.TRADITION: Permission.FAMILY_WRITE,
    CitationTarget.ASSERTION: Permission.ASSERTION_WRITE,
    CitationTarget.ASTROLOGY_PROFILE: Permission.ASTROLOGY_WRITE,
}


def require_citation_delete(ctx: TreeContext, c: Citation) -> None:
    """SEC-7: removing evidence needs write rights on the cited record (or authorship of the citation)."""
    ctx.require(Permission.SOURCE_WRITE)
    _check_target_visible(ctx, c.target_type, c.target_id)
    if c.created_by is not None and c.created_by == ctx.user_id:
        return
    perm = _TARGET_WRITE.get(c.target_type, Permission.PERSON_WRITE)
    person_id = None
    if perm in (Permission.PERSON_WRITE, Permission.ASSERTION_WRITE, Permission.ASTROLOGY_WRITE):
        model = _TARGET_MODELS[c.target_type]
        stmt: Any = select(model).where(model.tree_id == ctx.tree_id, model.id == c.target_id)  # type: ignore[attr-defined]
        obj: Any = ctx.db.scalar(stmt)
        person_id = getattr(obj, "person_id", None) if c.target_type != CitationTarget.PERSON else c.target_id
    ctx.require(perm, person_id=person_id)
