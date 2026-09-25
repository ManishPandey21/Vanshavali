"""Astrology profiles (PRS §11). Optional heritage data; nothing here is calculated.

Visibility = the person is visible, the viewer may see the person's ``astrology`` field group, and
the profile's own privacy level admits the viewer. Writes need ``astrology.write`` (branch-scoped).

DEFERRED: an ephemeris-based calculation engine. ``calculated`` provenance is accepted only with the
external ``calculation_system`` and ``ephemeris_version`` that produced the values.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import FieldGroup, Subject, can_view_field, level_allows
from app.core import audit
from app.core.dates import date_to_json
from app.core.errors import NotFound, Unprocessable
from app.models import AstrologyProfile, Citation, Event, EventParticipant
from app.models.enums import (
    CitationTarget,
    EventType,
    GrantResource,
    ParticipantRole,
    PrivacyLevel,
)
from app.modules.astrology.schemas import AstrologyIn, AstrologyOut, AstrologyUpdate, check_calculated
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import ProvenanceOut
from app.modules.genealogy.serialize import citation_counts


def can_view_profile(ctx: TreeContext, prof: AstrologyProfile, subject: Subject) -> bool:
    if not can_view_field(ctx, subject, FieldGroup.ASTROLOGY):
        return False
    return level_allows(ctx, prof.privacy_level, subject=subject, grant=(GrantResource.PERSON, subject.id))


def profile_out(
    ctx: TreeContext, prof: AstrologyProfile, counts: dict[uuid.UUID, int] | None = None
) -> AstrologyOut:
    if counts is None:
        counts = citation_counts(ctx, CitationTarget.ASTROLOGY_PROFILE, {prof.id})
    from app.core.dates import date_from_json

    d = date_from_json(prof.chart_birth_date)
    return AstrologyOut.model_validate(prof).model_copy(
        update={
            "chart_birth_date_display": d.display() if d else None,
            "provenance": ProvenanceOut.of(prof),
            "citation_count": counts.get(prof.id, 0),
            "place_latitude": float(prof.place_latitude) if prof.place_latitude is not None else None,
            "place_longitude": float(prof.place_longitude) if prof.place_longitude is not None else None,
        }
    )


def _profiles(ctx: TreeContext, person_id: uuid.UUID) -> list[AstrologyProfile]:
    return list(
        ctx.db.scalars(
            select(AstrologyProfile)
            .where(AstrologyProfile.tree_id == ctx.tree_id, AstrologyProfile.person_id == person_id)
            .order_by(AstrologyProfile.is_preferred.desc(), AstrologyProfile.created_at)
        )
    )


def list_profiles(ctx: TreeContext, person_id: uuid.UUID) -> list[AstrologyOut]:
    subject = lookup.get_person_subject(ctx, person_id)
    rows = [p for p in _profiles(ctx, person_id) if can_view_profile(ctx, p, subject)]
    counts = citation_counts(ctx, CitationTarget.ASTROLOGY_PROFILE, {p.id for p in rows})
    return [profile_out(ctx, p, counts) for p in rows]


def visible_profiles(ctx: TreeContext, subject: Subject) -> list[AstrologyProfile]:
    return [p for p in _profiles(ctx, subject.id) if can_view_profile(ctx, p, subject)]


def get_profile(ctx: TreeContext, profile_id: uuid.UUID) -> tuple[AstrologyProfile, Subject]:
    prof = lookup.get_in_tree(ctx, AstrologyProfile, profile_id, "Astrology profile")
    subject = lookup.get_person_subject(ctx, prof.person_id)
    if not can_view_profile(ctx, prof, subject):
        raise NotFound("Astrology profile not found")
    return prof, subject


def _check_refs(
    ctx: TreeContext, person_id: uuid.UUID, birth_event_id: uuid.UUID | None, document_id: uuid.UUID | None
) -> None:
    if birth_event_id is not None:
        ok = ctx.db.scalar(
            select(Event.id)
            .join(
                EventParticipant,
                (EventParticipant.event_id == Event.id) & (EventParticipant.tree_id == Event.tree_id),
            )
            .where(
                Event.tree_id == ctx.tree_id,
                Event.id == birth_event_id,
                Event.type == EventType.BIRTH,
                EventParticipant.person_id == person_id,
                EventParticipant.role == ParticipantRole.PRINCIPAL,
            )
        )
        if ok is None:
            raise Unprocessable("birth_event_id must be a birth event of this person")
    if document_id is not None:
        from app.modules.documents.access import get_document

        get_document(ctx, document_id)


def _unset_other_preferred(ctx: TreeContext, prof: AstrologyProfile) -> None:
    for other in _profiles(ctx, prof.person_id):
        if other.id != prof.id and other.is_preferred:
            other.is_preferred = False


def create_profile(
    ctx: TreeContext, person_id: uuid.UUID, body: AstrologyIn, **provenance: Any
) -> AstrologyProfile:
    person = lookup.get_person(ctx, person_id)
    ctx.require(Permission.ASTROLOGY_WRITE, person_id=person.id)
    _check_refs(ctx, person.id, body.birth_event_id, body.document_id)
    existing = _profiles(ctx, person.id)
    data = body.model_dump(
        exclude={"chart_birth_date", "chart_birth_time", "is_preferred", "privacy_level"},
    )
    prof = AstrologyProfile(
        tree_id=ctx.tree_id,
        person_id=person.id,
        chart_birth_date=date_to_json(body.chart_birth_date),
        chart_birth_time=body.chart_birth_time.model_dump(mode="json", exclude_none=True)
        if body.chart_birth_time
        else None,
        privacy_level=body.privacy_level or PrivacyLevel.PRIVATE_TREE_ADMINS,
        created_by=ctx.user_id,
        **data,
        **provenance,
    )
    prof.is_preferred = (
        body.is_preferred if body.is_preferred is not None else not any(e.is_preferred for e in existing)
    )
    ctx.db.add(prof)
    ctx.db.flush()
    if prof.is_preferred:
        _unset_other_preferred(ctx, prof)
    audit.log(
        ctx,
        "astrology.profile_added",
        target_type="person",
        target_id=person.id,
        details={"profile_id": str(prof.id), "provenance_kind": prof.provenance_kind.value},
    )
    return prof


def update_profile(ctx: TreeContext, profile_id: uuid.UUID, body: AstrologyUpdate) -> AstrologyProfile:
    prof, subject = get_profile(ctx, profile_id)
    ctx.require(Permission.ASTROLOGY_WRITE, person_id=subject.id)
    fields = set(body.model_fields_set)
    for required in ("provenance_kind", "evidence_status", "confidence", "privacy_level"):
        if required in fields and getattr(body, required) is None:
            raise Unprocessable(f"{required} cannot be empty")
    _check_refs(
        ctx,
        subject.id,
        body.birth_event_id if "birth_event_id" in fields else None,
        body.document_id if "document_id" in fields else None,
    )
    kind = body.provenance_kind if "provenance_kind" in fields else prof.provenance_kind
    system = body.calculation_system if "calculation_system" in fields else prof.calculation_system
    eph = body.ephemeris_version if "ephemeris_version" in fields else prof.ephemeris_version
    try:
        check_calculated(kind, system, eph)
    except ValueError as exc:
        raise Unprocessable(str(exc))
    for f in fields - {"is_preferred"}:
        v = getattr(body, f)
        if f == "chart_birth_date":
            v = date_to_json(v)
        elif f == "chart_birth_time":
            v = v.model_dump(mode="json", exclude_none=True) if v is not None else None
        setattr(prof, f, v)
    if body.is_preferred is not None:
        prof.is_preferred = body.is_preferred
        if body.is_preferred:
            _unset_other_preferred(ctx, prof)
    prof.updated_by = ctx.user_id
    audit.log(
        ctx,
        "astrology.profile_changed",
        target_type="person",
        target_id=subject.id,
        details={"profile_id": str(prof.id), "fields": sorted(fields)},
    )
    return prof


def delete_profile(ctx: TreeContext, profile_id: uuid.UUID) -> None:
    prof, subject = get_profile(ctx, profile_id)
    ctx.require(Permission.ASTROLOGY_WRITE, person_id=subject.id)
    ctx.db.execute(
        sa_delete(Citation).where(
            Citation.tree_id == ctx.tree_id,
            Citation.target_type == CitationTarget.ASTROLOGY_PROFILE,
            Citation.target_id == prof.id,
        )
    )
    ctx.db.delete(prof)
    audit.log(
        ctx,
        "astrology.profile_removed",
        target_type="person",
        target_id=subject.id,
        details={"profile_id": str(prof.id)},
    )
