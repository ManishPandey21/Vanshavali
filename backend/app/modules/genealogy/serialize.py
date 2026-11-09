"""Privacy-aware serialisation of genealogy objects (ADR-0006). All person output passes here."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import FieldGroup, Subject, can_view_field, level_allows
from app.core.dates import GenealogicalDate, GenealogicalTime
from app.models import (
    BranchMembership,
    Citation,
    Event,
    EventParticipant,
    NameRecord,
    Place,
    Relationship,
)
from app.models.enums import CitationTarget, EventType, ParticipantRole
from app.modules.genealogy import provisional
from app.modules.genealogy.geo import coarsen, may_see_exact
from app.modules.genealogy.schemas import (
    EventOut,
    NameOut,
    ParticipantOut,
    PersonOut,
    PersonSummary,
    ProvenanceOut,
    RelationshipOut,
    VitalSummary,
)


def name_display(n: NameRecord) -> str:
    if n.full_name_as_recorded and not (n.given_name or n.surname):
        return n.full_name_as_recorded
    parts = [n.honorific_prefix, n.given_name, n.middle_names, n.surname, n.honorific_suffix]
    text = " ".join(p for p in parts if p)
    return text or n.full_name_as_recorded or n.romanized_value or ""


def name_out(n: NameRecord) -> NameOut:
    out = NameOut.model_validate(n)
    return out.model_copy(update={"provenance": ProvenanceOut.of(n), "display": name_display(n)})


def date_display(raw: dict[str, Any] | None) -> str | None:
    return GenealogicalDate.model_validate(raw).display() if raw else None


def time_display(raw: dict[str, Any] | None) -> str | None:
    if not raw:
        return None
    t = GenealogicalTime.model_validate(raw)
    if t.value is None:
        return "unknown"
    base = t.value.strftime("%H:%M")
    if t.precision.value == "exact":
        return base
    return f"{base} ({t.precision.value.replace('_', ' ')})"


def _redact_event_fields(
    ctx: TreeContext, subject: Subject | None, ev: Event, data: dict[str, Any]
) -> list[str]:
    """Apply field-group rules for an event whose principal is ``subject``."""
    redacted: list[str] = []
    if subject is None:
        return redacted
    if ev.type == EventType.BIRTH:
        if not can_view_field(ctx, subject, FieldGroup.BIRTH_DATE_FULL):
            if ev.date:
                data["date"] = (
                    GenealogicalDate.model_validate(ev.date)
                    .year_only()
                    .model_dump(mode="json", exclude_none=True)
                )
                data["date_display"] = date_display(data["date"])
            redacted.append(FieldGroup.BIRTH_DATE_FULL)
        if not can_view_field(ctx, subject, FieldGroup.BIRTH_TIME):
            if ev.time or ev.timezone_id or ev.utc_offset_minutes is not None:
                redacted.append(FieldGroup.BIRTH_TIME)
            data.update(time=None, time_display=None, timezone_id=None, utc_offset_minutes=None)
        if not can_view_field(ctx, subject, FieldGroup.BIRTH_PLACE_DETAIL):
            if ev.place_as_recorded or ev.latitude is not None or ev.place_id:
                redacted.append(FieldGroup.BIRTH_PLACE_DETAIL)
            data.update(place_as_recorded=None, latitude=None, longitude=None, place_id=None, place_name=None)
    elif ev.type == EventType.RESIDENCE and not can_view_field(ctx, subject, FieldGroup.ADDRESS):
        data.update(
            place_as_recorded=None,
            latitude=None,
            longitude=None,
            place_id=None,
            place_name=None,
            description=None,
        )
        redacted.append(FieldGroup.ADDRESS)
    elif subject.is_protected and not can_view_field(ctx, subject, FieldGroup.BIRTH_DATE_FULL) and ev.date:
        # other life events of living people: keep year-level dates only
        data["date"] = (
            GenealogicalDate.model_validate(ev.date).year_only().model_dump(mode="json", exclude_none=True)
        )
        data["date_display"] = date_display(data["date"])
        redacted.append("event_date_full")
    if ctx.public:
        data.update(latitude=None, longitude=None, description=None, provenance=None, location_precision=None)
    return redacted


class Serializer:
    """Batch serialiser holding per-request caches (places, subjects)."""

    def __init__(self, ctx: TreeContext) -> None:
        self.ctx = ctx
        self._places: dict[uuid.UUID, Place] = {}

    # ---- places ----
    def places(self, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, Place]:
        missing = {i for i in ids if i and i not in self._places}
        if missing:
            for p in self.ctx.db.scalars(
                select(Place).where(Place.tree_id == self.ctx.tree_id, Place.id.in_(missing))
            ):
                self._places[p.id] = p
        return self._places

    # ---- events ----
    def event_out(
        self,
        ev: Event,
        participants: list[EventParticipant],
        subjects: dict[uuid.UUID, Subject],
        citation_counts: dict[uuid.UUID, int] | None = None,
        media: dict[uuid.UUID, tuple[int, uuid.UUID | None]] | None = None,
    ) -> EventOut | None:
        ctx = self.ctx
        principal = next((p for p in participants if p.role == ParticipantRole.PRINCIPAL), None)
        subject = subjects.get(principal.person_id) if principal else None
        if principal is not None and subject is None:
            return None  # principal hidden → event hidden
        if ev.privacy_level is not None and not level_allows(ctx, ev.privacy_level, subject=subject):
            return None
        places = self.places({ev.place_id, ev.origin_place_id})
        data: dict[str, Any] = {
            "id": ev.id,
            "type": ev.type,
            "subtype": ev.subtype,
            "date": ev.date,
            "date_display": date_display(ev.date),
            "time": ev.time,
            "time_display": time_display(ev.time),
            "timezone_id": ev.timezone_id,
            "utc_offset_minutes": ev.utc_offset_minutes,
            "place_id": ev.place_id,
            "place_name": places[ev.place_id].canonical_name if ev.place_id in places else None,
            "place_as_recorded": ev.place_as_recorded,
            "origin_place_id": ev.origin_place_id,
            "origin_place_name": places[ev.origin_place_id].canonical_name
            if ev.origin_place_id in places
            else None,
            "origin_place_as_recorded": ev.origin_place_as_recorded,
            "latitude": float(ev.latitude) if ev.latitude is not None else None,
            "longitude": float(ev.longitude) if ev.longitude is not None else None,
            "reason": ev.reason,
            "description": ev.description,
            "is_preferred": ev.is_preferred,
            "evidence_status": ev.evidence_status,
            "confidence": ev.confidence,
            "provenance": ProvenanceOut.of(ev),
            "citation_count": (citation_counts or {}).get(ev.id, 0),
            "title": ev.title,
            "category": ev.category,
            "significance": ev.significance,
            "location_precision": ev.location_precision,
            "privacy_level": None if ctx.public else ev.privacy_level,
            "media_count": (media or {}).get(ev.id, (0, None))[0],
            "review_state": ev.review_state,
            "cover_document_id": (media or {}).get(ev.id, (0, None))[1],
        }
        place = places.get(ev.place_id) if ev.place_id else None
        if place is not None and data["latitude"] is not None and not may_see_exact(ctx, place):
            c = coarsen(data["latitude"], data["longitude"], ev.location_precision)
            data.update(latitude=c.latitude, longitude=c.longitude, location_precision=c.precision)
        redacted = _redact_event_fields(ctx, subject, ev, data)
        parts = []
        for p in participants:
            s = subjects.get(p.person_id)
            if s is None:
                continue  # hidden co-participant
            parts.append(
                ParticipantOut(
                    person_id=p.person_id,
                    role=p.role,
                    role_detail=p.role_detail,
                    display_name=s.person.preferred_display_name,
                )
            )
        data["participants"] = parts
        data["redacted_fields"] = redacted
        return EventOut(**data)

    def events_for(
        self,
        person_ids: list[uuid.UUID],
        subjects: dict[uuid.UUID, Subject],
        types: set[EventType] | None = None,
    ) -> dict[uuid.UUID, list[EventOut]]:
        """Events in which the given people participate, grouped by person, privacy-filtered."""
        ctx = self.ctx
        if not person_ids:
            return {}
        q = (
            select(Event, EventParticipant)
            .join(
                EventParticipant,
                (EventParticipant.event_id == Event.id) & (EventParticipant.tree_id == Event.tree_id),
            )
            .where(Event.tree_id == ctx.tree_id, EventParticipant.person_id.in_(person_ids))
        )
        if types:
            q = q.where(Event.type.in_(types))
        rows = ctx.db.execute(q).all()
        event_ids = {e.id for e, _ in rows}
        all_parts: dict[uuid.UUID, list[EventParticipant]] = defaultdict(list)
        if event_ids:
            for p in ctx.db.scalars(
                select(EventParticipant).where(
                    EventParticipant.tree_id == ctx.tree_id, EventParticipant.event_id.in_(event_ids)
                )
            ):
                all_parts[p.event_id].append(p)
        extra_ids = {p.person_id for ps in all_parts.values() for p in ps} - set(subjects)
        if extra_ids:
            from app.modules.genealogy.lookup import visible_subjects

            subjects = {**subjects, **visible_subjects(ctx, extra_ids)}
        counts = citation_counts(ctx, CitationTarget.EVENT, event_ids)
        media = media_summary(ctx, event_ids)
        out: dict[uuid.UUID, list[EventOut]] = defaultdict(list)
        cache: dict[uuid.UUID, EventOut | None] = {}
        for ev, part in rows:
            if ev.id not in cache:
                cache[ev.id] = self.event_out(ev, all_parts[ev.id], subjects, counts, media)
            eo = cache[ev.id]
            if eo is not None:
                out[part.person_id].append(eo)
        for lst in out.values():
            lst.sort(key=lambda e: (_sort_key(e.date), e.type.value))
        return out

    # ---- persons ----
    def summary(self, s: Subject, vitals: dict[str, EventOut | None] | None = None) -> PersonSummary:
        birth = (vitals or {}).get("birth")
        death = (vitals or {}).get("death")
        by = (
            (birth.date or {}).get("year")
            if birth and birth.date
            else (s.birth_date.year if s.birth_date else None)
        )
        if ctx_public_hides_birth(self.ctx, s):
            by = None
        return PersonSummary(
            id=s.id,
            display_name=s.person.preferred_display_name,
            profile_status=s.person.profile_status,
            sex_at_birth=s.person.sex_at_birth,
            birth_year=by,
            death_year=(death.date or {}).get("year") if death and death.date else None,
            birth_date=None if by is None or birth is None else birth.date,
            birth_display=None if by is None or birth is None else birth.date_display,
            death_date=death.date if death else None,
            death_display=death.date_display if death else None,
            is_minor=s.is_minor if not self.ctx.public else False,
            is_protected=s.is_protected,
            privacy_level=None if self.ctx.public else s.person.privacy_level,
            is_provisional=s.person.is_provisional,
            provisional_state=(
                provisional.states(self.ctx).get(s.id, provisional.ProvisionalState.NEEDS_DETAILS).value
                if s.person.is_provisional and not self.ctx.public
                else None
            ),
        )

    def summaries(self, subjects: dict[uuid.UUID, Subject]) -> dict[uuid.UUID, PersonSummary]:
        ids = list(subjects)
        ev = self.events_for(ids, subjects, {EventType.BIRTH, EventType.DEATH})
        out = {}
        for pid, s in subjects.items():
            out[pid] = self.summary(s, _pick_vitals(ev.get(pid, []), pid))
        return out

    def person_out(self, s: Subject) -> PersonOut:
        ctx = self.ctx
        p = s.person
        names = ctx.db.scalars(
            select(NameRecord)
            .where(NameRecord.tree_id == ctx.tree_id, NameRecord.person_id == p.id)
            .order_by(NameRecord.is_preferred.desc(), NameRecord.created_at)
        ).all()
        events = self.events_for([p.id], {p.id: s}, {EventType.BIRTH, EventType.DEATH}).get(p.id, [])
        vitals = _pick_vitals(events, p.id)
        summary = self.summary(s, vitals)
        redacted: list[str] = []

        def gated(group: str, value: Any) -> Any:
            if value is None:
                return None
            if can_view_field(ctx, s, group):
                return value
            redacted.append(group)
            return None

        birth = vitals.get("birth")
        death = vitals.get("death")
        branch_ids = (
            []
            if ctx.public
            else list(
                ctx.db.scalars(
                    select(BranchMembership.branch_id).where(
                        BranchMembership.tree_id == ctx.tree_id, BranchMembership.person_id == p.id
                    )
                )
            )
        )
        can_edit = False
        if not ctx.public and ctx.has(Permission.PERSON_WRITE):
            can_edit = ctx.branch_scope is None or p.id in ctx.branch_people()
        out = PersonOut(
            **summary.model_dump(),
            gender_identity=gated(FieldGroup.GENDER_IDENTITY, p.gender_identity),
            primary_language=p.primary_language,
            scripts_used=list(p.scripts_used or []),
            occupation=None if ctx.public else p.occupation,
            notes=None if ctx.public else gated(FieldGroup.NOTES, p.notes),
            contact_info=None if ctx.public else gated(FieldGroup.CONTACT, p.contact_info),
            residential_address=None if ctx.public else gated(FieldGroup.ADDRESS, p.residential_address),
            field_privacy=dict(p.field_privacy or {})
            if ctx.is_admin or (ctx.user is not None and p.claimed_by_user_id == ctx.user.id)
            else None,
            claimed_by_user_id=p.claimed_by_user_id if not ctx.public else None,
            names=[name_out(n) for n in names]
            if not ctx.public
            else [name_out(n).model_copy(update={"provenance": None}) for n in names],
            birth=_vital_summary(birth),
            death=_vital_summary(death),
            branch_ids=branch_ids,
            can_edit=can_edit,
            created_at=None if ctx.public else p.created_at,
            updated_at=None if ctx.public else p.updated_at,
        )
        redacted += birth.redacted_fields if birth else []
        out.redacted_fields = sorted(set(redacted))
        return out


def ctx_public_hides_birth(ctx: TreeContext, s: Subject) -> bool:
    return ctx.public and s.is_protected


def _sort_key(date: dict[str, Any] | None) -> str:
    if not date:
        return "9999"
    key = GenealogicalDate.model_validate(date).sort_key()
    return key.isoformat() if key else "9999"


def _pick_vitals(events: list[EventOut], person_id: uuid.UUID) -> dict[str, EventOut | None]:
    def pick(t: EventType) -> EventOut | None:
        cands = [
            e
            for e in events
            if e.type == t
            and any(p.person_id == person_id and p.role == ParticipantRole.PRINCIPAL for p in e.participants)
        ]
        cands.sort(key=lambda e: (not e.is_preferred,))
        return cands[0] if cands else None

    return {"birth": pick(EventType.BIRTH), "death": pick(EventType.DEATH)}


def _vital_summary(e: EventOut | None) -> VitalSummary | None:
    if e is None:
        return None
    return VitalSummary(
        event_id=e.id,
        date=e.date,
        date_display=e.date_display,
        time=e.time,
        time_display=e.time_display,
        place_name=e.place_name,
        place_as_recorded=e.place_as_recorded,
        redacted_fields=e.redacted_fields,
    )


def relationship_out(r: Relationship) -> RelationshipOut:
    return RelationshipOut.model_validate(r).model_copy(update={"provenance": ProvenanceOut.of(r)})


def citation_counts(ctx: TreeContext, target: CitationTarget, ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    rows = ctx.db.execute(
        select(Citation.target_id, func.count())
        .where(Citation.tree_id == ctx.tree_id, Citation.target_type == target, Citation.target_id.in_(ids))
        .group_by(Citation.target_id)
    ).all()
    return {tid: int(n) for tid, n in rows}


def media_summary(
    ctx: TreeContext, event_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, uuid.UUID | None]]:
    """Per event: how many album photos the viewer may see, and the cover (if the viewer may see it)."""
    if not event_ids or ctx.public:
        return {}
    from app.models import Document, EventMedia
    from app.modules.documents.access import can_view_document

    rows = ctx.db.execute(
        select(EventMedia, Document)
        .join(
            Document,
            (Document.id == EventMedia.document_id) & (Document.tree_id == EventMedia.tree_id),
        )
        .where(
            EventMedia.tree_id == ctx.tree_id,
            EventMedia.event_id.in_(event_ids),
            Document.deleted_at.is_(None),
        )
    ).all()
    out: dict[uuid.UUID, tuple[int, uuid.UUID | None]] = {}
    first: dict[uuid.UUID, uuid.UUID] = {}
    for m, doc in sorted(rows, key=lambda r: (r[0].sort_order, r[0].created_at)):
        if not can_view_document(ctx, doc):
            continue
        n, cover = out.get(m.event_id, (0, None))
        out[m.event_id] = (n + 1, doc.id if m.is_cover else cover)
        first.setdefault(m.event_id, doc.id)
    # a cover the viewer may not see is replaced by their first visible photo (ADR-0027 §6)
    return {eid: (n, cover or first.get(eid)) for eid, (n, cover) in out.items()}
