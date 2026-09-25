"""Turning an accepted/edited proposal into canonical data (ADR-0009 §3).

Each accepted value becomes a NEW claim with OCR provenance, ``evidence_status=SOURCED`` and a
citation to the document's Source. Existing preferred facts are never overwritten:

* birth date/time/place (certificate) → one birth Event per (person, document); it is not preferred
  when the person already has a preferred birth (a competing claim, surfaced by /birth-conflicts);
* name → a birth-type NameRecord (``full_name_as_recorded``), never made preferred;
* sex → only fills an empty ``sex_at_birth``; a different existing value is a 409;
* parents' names → ``recorded_parent_name`` assertions (people are never auto-linked);
* registration number/date, issuing authority → the document's Source;
* Kundli fields → one ``uploaded_chart`` AstrologyProfile per (person, document);
* land fields → LandParcel columns on the subject property (a parcel is created if none exists);
  values without a column go into ``extra_identifiers``. A filled column that differs is a 409.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.dates import TimeSource
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models import (
    AstrologyProfile,
    Citation,
    Document,
    DocumentLink,
    Event,
    EventParticipant,
    ExtractionProposal,
    LandParcel,
    Property,
    Source,
)
from app.models.enums import (
    AssertionSubject,
    AstrologyProvenance,
    CitationTarget,
    Confidence,
    DocumentCategory,
    DocumentLinkTarget,
    EventType,
    EvidenceStatus,
    HeritageAttribute,
    NameType,
    ParticipantRole,
    ProvenanceOrigin,
    SourceType,
)
from app.modules.extraction import fields as F
from app.modules.extraction.pipeline import linked_subjects
from app.modules.genealogy import lookup

BIRTH_EVENT_FIELDS = {"date_of_birth": "date", "time_of_birth": "time", "place_of_birth": "place_as_recorded"}
SOURCE_FIELDS = {
    "registration_number": "record_number",
    "deed_registration_number": "record_number",
    "registration_date": "date",
    "issuing_authority": "issuing_authority",
}
KUNDLI_FIELDS = {
    "chart_birth_date": "chart_birth_date",
    "chart_birth_time": "chart_birth_time",
    "chart_birth_place": "chart_birth_place",
    "nakshatra": "nakshatra",
    "nakshatra_pada": "nakshatra_pada",
    "rashi": "rashi",
    "lagna": "lagna",
    "tithi": "tithi",
    "paksha": "paksha",
    "ayanamsha": "ayanamsha",
}
PARCEL_COLUMNS = {
    "khasra_or_gata_number": 60,
    "khata_number": 60,
    "khatauni_number": 60,
    "survey_number": 60,
    "patta_number": 60,
    "village": 150,
    "tehsil_taluk": 100,
    "district": 100,
}
PARCEL_EXTRA_LISTS = {"holder_name": "recorded_holders", "holder_relative_name": "recorded_holder_relatives"}
PARCEL_EXTRA_SCALARS = {"mutation_number", "mutation_date", "deed_registration_date"}

SOURCE_TYPE_FOR = {
    DocumentCategory.BIRTH_CERTIFICATE: SourceType.CERTIFICATE,
    DocumentCategory.DEATH_CERTIFICATE: SourceType.CERTIFICATE,
    DocumentCategory.KUNDLI: SourceType.KUNDLI,
    DocumentCategory.TITLE_DEED: SourceType.DEED,
    DocumentCategory.SALE_DEED: SourceType.DEED,
    DocumentCategory.GIFT_DEED: SourceType.DEED,
    DocumentCategory.PARTITION_DEED: SourceType.DEED,
    DocumentCategory.RELINQUISHMENT_DEED: SourceType.DEED,
    DocumentCategory.COURT_ORDER: SourceType.COURT_RECORD,
}


class Applied:
    def __init__(self, target_type: str, target_id: uuid.UUID) -> None:
        self.target_type = target_type
        self.target_id = target_id


def time_source_for(p: ExtractionProposal) -> TimeSource:
    return TimeSource.KUNDLI if p.field.startswith("chart_") else TimeSource.BIRTH_CERTIFICATE


def _confidence(c: float) -> Confidence:
    return Confidence.HIGH if c >= 0.85 else Confidence.MEDIUM if c >= 0.6 else Confidence.LOW


def _location(p: ExtractionProposal) -> str:
    loc = p.source_location or {}
    parts = []
    if loc.get("page"):
        parts.append(f"page {loc['page']}")
    if loc.get("line"):
        parts.append(f"line {loc['line']}")
    return ", ".join(parts) or "document"


def _provenance(ctx: TreeContext, p: ExtractionProposal, doc: Document, now: dt.datetime) -> dict[str, Any]:
    return {
        "prov_origin": ProvenanceOrigin.OCR,
        "prov_algorithm": f"{p.extractor}"[:120],
        "prov_model_version": f"{p.extractor_version}; {p.engine or 'unknown engine'}"[:80],
        "prov_source_document_id": doc.id,
        "prov_source_location": _location(p),
        "prov_extracted_at": p.created_at,
        "prov_confirmed_by": ctx.user_id,
        "prov_confirmed_at": now,
    }


def _source(ctx: TreeContext, doc: Document) -> Source:
    from app.modules.evidence.service import ensure_document_source

    return ensure_document_source(
        ctx,
        doc.id,
        doc.title,
        SOURCE_TYPE_FOR.get(doc.category, _default_source_type(doc)),
        doc.issuing_authority,
    )


def _default_source_type(doc: Document) -> SourceType:
    from app.models.enums import PROPERTY_CATEGORIES

    return SourceType.LAND_RECORD if doc.category in PROPERTY_CATEGORIES else SourceType.OTHER


def _cite(
    ctx: TreeContext, source: Source, target_type: CitationTarget, target_id: uuid.UUID, p: ExtractionProposal
) -> None:
    """Cite the document's Source once per claim.

    Created directly (rather than via ``evidence.service.add_citation``) because the Source of a vault
    document inherits the document's admin-only privacy, which a document custodian reviewing the
    proposal may not pass; the reviewer's right to the document content was already checked.
    """
    exists = ctx.db.scalar(
        select(Citation.id).where(
            Citation.tree_id == ctx.tree_id,
            Citation.source_id == source.id,
            Citation.target_type == target_type,
            Citation.target_id == target_id,
        )
    )
    if exists is not None:
        return
    ctx.db.add(
        Citation(
            tree_id=ctx.tree_id,
            source_id=source.id,
            target_type=target_type,
            target_id=target_id,
            page_or_image=_location(p)[:200],
            confidence=_confidence(p.confidence),
            created_by=ctx.user_id,
        )
    )
    ctx.db.flush()
    audit.log(ctx, "citation.added", target_type=target_type.value, target_id=target_id)


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().casefold() == b.strip().casefold()
    if isinstance(a, dict) and isinstance(b, dict):
        # dates/times: compare the substantive parts, not original_text
        keys = (set(a) | set(b)) - {"original_text", "redacted"}
        return all(a.get(k) == b.get(k) for k in keys)
    return bool(a == b)


def _conflict(label: str) -> Conflict:
    return Conflict(
        f"The record already holds a different {label}; it was not overwritten. Reject this proposal or "
        "edit the value to match, and record the disagreement as a separate claim.",
        code="conflicting_value",
    )


# ---------------------------------------------------------------- subjects
def _person_id(ctx: TreeContext, p: ExtractionProposal, doc: Document, target: uuid.UUID | None) -> uuid.UUID:
    pid = target or p.subject_person_id or linked_subjects(ctx.db, doc)[0]
    if pid is None:
        raise Unprocessable(
            "Choose the person this document is about (target_person_id)", code="target_person_required"
        )
    person = lookup.get_person(ctx, pid)
    _ensure_link(ctx, doc, DocumentLinkTarget.PERSON, person.id)
    return person.id


def _ensure_link(
    ctx: TreeContext, doc: Document, target_type: DocumentLinkTarget, target_id: uuid.UUID
) -> None:
    exists = ctx.db.scalar(
        select(DocumentLink.id).where(
            DocumentLink.tree_id == ctx.tree_id,
            DocumentLink.document_id == doc.id,
            DocumentLink.target_type == target_type,
            DocumentLink.target_id == target_id,
        )
    )
    if exists is None:
        ctx.db.add(
            DocumentLink(
                tree_id=ctx.tree_id,
                document_id=doc.id,
                target_type=target_type,
                target_id=target_id,
                note="linked when an extracted value was confirmed",
                created_by=ctx.user_id,
            )
        )
        ctx.db.flush()


# ---------------------------------------------------------------- birth certificate
def _birth_event_from_doc(ctx: TreeContext, person_id: uuid.UUID, doc: Document) -> Event | None:
    return ctx.db.scalar(
        select(Event)
        .join(
            EventParticipant,
            (EventParticipant.event_id == Event.id) & (EventParticipant.tree_id == Event.tree_id),
        )
        .where(
            Event.tree_id == ctx.tree_id,
            Event.type == EventType.BIRTH,
            Event.prov_source_document_id == doc.id,
            EventParticipant.person_id == person_id,
            EventParticipant.role == ParticipantRole.PRINCIPAL,
        )
        .order_by(Event.created_at)
        .limit(1)
    )


def _apply_birth_event(
    ctx: TreeContext,
    p: ExtractionProposal,
    doc: Document,
    person_id: uuid.UUID,
    value: Any,
    prov: dict[str, Any],
) -> Applied:
    from app.modules.genealogy import service as genealogy
    from app.modules.genealogy.schemas import EventIn, EventUpdate, ParticipantIn

    attr = BIRTH_EVENT_FIELDS[p.field]
    existing = _birth_event_from_doc(ctx, person_id, doc)
    if existing is not None:
        current = getattr(existing, attr)
        if current is not None:
            if _same(current, value):
                return Applied("event", existing.id)
            raise _conflict(F.FIELD_SPECS[p.field].label.lower())
        genealogy.update_event(ctx, existing.id, EventUpdate.model_validate({attr: value}))
        event = existing
    else:
        body = EventIn.model_validate(
            {
                "type": EventType.BIRTH,
                "participants": [ParticipantIn(person_id=person_id, role=ParticipantRole.PRINCIPAL)],
                attr: value,
                "evidence_status": EvidenceStatus.SOURCED,
                "confidence": _confidence(p.confidence),
            }
        )
        # is_preferred is deliberately not given: create_event then keeps an existing preferred
        # birth preferred and stores this one as a competing claim
        event = genealogy.create_event(ctx, body, **prov)
    _cite(ctx, _source(ctx, doc), CitationTarget.EVENT, event.id, p)
    return Applied("event", event.id)


def _apply_name(
    ctx: TreeContext,
    p: ExtractionProposal,
    doc: Document,
    person_id: uuid.UUID,
    value: Any,
    prov: dict[str, Any],
) -> Applied:
    from app.modules.genealogy import service as genealogy
    from app.modules.genealogy.schemas import NameIn

    n = genealogy.add_name(
        ctx,
        person_id,
        NameIn(
            type=NameType.BIRTH,
            full_name_as_recorded=value,
            is_preferred=False,
            evidence_status=EvidenceStatus.SOURCED,
            confidence=_confidence(p.confidence),
        ),
    )
    for k, v in prov.items():
        setattr(n, k, v)
    _cite(ctx, _source(ctx, doc), CitationTarget.NAME_RECORD, n.id, p)
    return Applied("name_record", n.id)


def _apply_sex(ctx: TreeContext, person_id: uuid.UUID, value: Any) -> Applied:
    from app.modules.genealogy import service as genealogy
    from app.modules.genealogy.schemas import PersonUpdate

    person = lookup.get_person(ctx, person_id)
    if person.sex_at_birth is not None:
        if person.sex_at_birth.value == value:
            return Applied("person", person.id)
        raise _conflict("sex at birth")
    genealogy.update_person(ctx, person.id, PersonUpdate(sex_at_birth=value))
    return Applied("person", person.id)


def _apply_parent_name(
    ctx: TreeContext,
    p: ExtractionProposal,
    doc: Document,
    person_id: uuid.UUID,
    value: Any,
    prov: dict[str, Any],
) -> Applied:
    from app.modules.heritage import service as heritage
    from app.modules.heritage.schemas import AssertionIn

    role = "father" if p.field == "father_name" else "mother"
    a = heritage.create_assertion(
        ctx,
        AssertionSubject.PERSON,
        person_id,
        AssertionIn(
            attribute=HeritageAttribute.RECORDED_PARENT_NAME,
            value_text=value,
            value_json={"role": role, "as_recorded_in": "birth_certificate"},
            evidence_status=EvidenceStatus.SOURCED,
            confidence=_confidence(p.confidence),
        ),
        **prov,
    )
    _cite(ctx, _source(ctx, doc), CitationTarget.ASSERTION, a.id, p)
    return Applied("assertion", a.id)


def _apply_source_field(ctx: TreeContext, p: ExtractionProposal, doc: Document, value: Any) -> Applied:
    ctx.require(Permission.SOURCE_WRITE)
    source = _source(ctx, doc)
    attr = SOURCE_FIELDS[p.field]
    current = getattr(source, attr)
    if current is not None and current != "":
        if _same(current, value):
            return Applied("source", source.id)
        raise _conflict(F.FIELD_SPECS[p.field].label.lower())
    setattr(source, attr, value)
    source.updated_by = ctx.user_id
    audit.log(ctx, "source.changed", target_type="source", target_id=source.id, details={"fields": [attr]})
    return Applied("source", source.id)


# ---------------------------------------------------------------- kundli
def _apply_kundli(
    ctx: TreeContext,
    p: ExtractionProposal,
    doc: Document,
    person_id: uuid.UUID,
    value: Any,
    prov: dict[str, Any],
) -> Applied:
    from app.modules.astrology import service as astrology
    from app.modules.astrology.schemas import AstrologyIn

    attr = KUNDLI_FIELDS[p.field]
    ctx.require(Permission.ASTROLOGY_WRITE, person_id=person_id)
    prof = ctx.db.scalar(
        select(AstrologyProfile)
        .where(
            AstrologyProfile.tree_id == ctx.tree_id,
            AstrologyProfile.person_id == person_id,
            AstrologyProfile.document_id == doc.id,
            AstrologyProfile.provenance_kind == AstrologyProvenance.UPLOADED_CHART,
        )
        .order_by(AstrologyProfile.created_at)
        .limit(1)
    )
    if prof is None:
        prof = astrology.create_profile(
            ctx,
            person_id,
            AstrologyIn.model_validate(
                {
                    "provenance_kind": AstrologyProvenance.UPLOADED_CHART,
                    "document_id": doc.id,
                    "evidence_status": EvidenceStatus.SOURCED,
                    "confidence": _confidence(p.confidence),
                    attr: value,
                }
            ),
            **prov,
        )
    else:
        current = getattr(prof, attr)
        if current is not None:
            if _same(current, value):
                return Applied("astrology_profile", prof.id)
            raise _conflict(F.FIELD_SPECS[p.field].label.lower())
        # validate through the API schema (vocabularies, pada range) before writing
        AstrologyIn.model_validate({attr: value})
        setattr(prof, attr, value)
        prof.updated_by = ctx.user_id
        audit.log(
            ctx,
            "astrology.profile_changed",
            target_type="person",
            target_id=person_id,
            details={"profile_id": str(prof.id), "fields": [attr]},
        )
    _cite(ctx, _source(ctx, doc), CitationTarget.ASTROLOGY_PROFILE, prof.id, p)
    return Applied("astrology_profile", prof.id)


# ---------------------------------------------------------------- land records
def _property(ctx: TreeContext, p: ExtractionProposal, doc: Document, target: uuid.UUID | None) -> Property:
    from app.modules.property.service import can_view_property

    pid = target or p.subject_property_id or linked_subjects(ctx.db, doc)[1]
    if pid is None:
        raise Unprocessable(
            "Choose the property this record is about (target_property_id)", code="target_property_required"
        )
    if not ctx.has(Permission.PROPERTY_WRITE):
        raise Forbidden("Applying land-record values needs property write permission")
    prop = ctx.db.scalar(select(Property).where(Property.tree_id == ctx.tree_id, Property.id == pid))
    if prop is None or not can_view_property(ctx, prop):
        raise NotFound("Property not found")
    _ensure_link(ctx, doc, DocumentLinkTarget.PROPERTY, prop.id)
    return prop


def _parcel(
    ctx: TreeContext, prop: Property, parcel_id: uuid.UUID | None, prov: dict[str, Any]
) -> LandParcel:
    if parcel_id is not None:
        parcel = ctx.db.scalar(
            select(LandParcel).where(
                LandParcel.tree_id == ctx.tree_id,
                LandParcel.id == parcel_id,
                LandParcel.property_id == prop.id,
            )
        )
        if parcel is None:
            raise NotFound("Parcel not found")
        return parcel
    parcels = list(
        ctx.db.scalars(
            select(LandParcel).where(LandParcel.tree_id == ctx.tree_id, LandParcel.property_id == prop.id)
        )
    )
    if len(parcels) == 1:
        return parcels[0]
    if len(parcels) > 1:
        raise Unprocessable(
            "This property has several parcels; choose one (target_parcel_id)", code="target_parcel_required"
        )
    parcel = LandParcel(
        tree_id=ctx.tree_id, property_id=prop.id, created_by=ctx.user_id, extra_identifiers={}, **prov
    )
    ctx.db.add(parcel)
    ctx.db.flush()
    audit.log(
        ctx,
        "property.parcel_added",
        target_type="property",
        target_id=prop.id,
        details={"parcel_id": str(parcel.id)},
    )
    return parcel


def _apply_land(
    ctx: TreeContext,
    p: ExtractionProposal,
    doc: Document,
    value: Any,
    prov: dict[str, Any],
    property_id: uuid.UUID | None,
    parcel_id: uuid.UUID | None,
) -> Applied:
    prop = _property(ctx, p, doc, property_id)
    parcel = _parcel(ctx, prop, parcel_id, prov)
    fld = p.field
    if fld in PARCEL_COLUMNS:
        if not isinstance(value, str) or len(value) > PARCEL_COLUMNS[fld]:
            raise Unprocessable(
                f"{F.FIELD_SPECS[fld].label} is too long; edit it to at most {PARCEL_COLUMNS[fld]} characters"
            )
        current = getattr(parcel, fld)
        if current:
            if not _same(current, value):
                raise _conflict(F.FIELD_SPECS[fld].label.lower())
        else:
            setattr(parcel, fld, value)
    elif fld == "area":
        if parcel.area is not None:
            same = float(parcel.area) == float(value["value"]) and (parcel.area_unit or None) == value.get(
                "unit"
            )
            if not same:
                raise _conflict("area")
        else:
            parcel.area = value["value"]
            parcel.area_unit = value.get("unit")
    else:
        extra = dict(parcel.extra_identifiers or {})
        if fld in PARCEL_EXTRA_LISTS:
            key = PARCEL_EXTRA_LISTS[fld]
            items = list(extra.get(key) or [])
            if not any(_same(i, value) for i in items):
                items.append(value)
            extra[key] = items
        elif fld in PARCEL_EXTRA_SCALARS:
            if fld in extra and not _same(extra[fld], value):
                raise _conflict(F.FIELD_SPECS[fld].label.lower())
            extra[fld] = value
        else:
            raise Unprocessable(f"Field {fld} cannot be applied to a land parcel")
        parcel.extra_identifiers = extra
    parcel.updated_by = ctx.user_id
    audit.log(
        ctx,
        "property.parcel_changed",
        target_type="property",
        target_id=prop.id,
        details={"parcel_id": str(parcel.id), "fields": [fld], "origin": "extraction"},
    )
    _cite(ctx, _source(ctx, doc), CitationTarget.LAND_PARCEL, parcel.id, p)
    return Applied("land_parcel", parcel.id)


# ---------------------------------------------------------------- dispatcher
def apply_proposal(
    ctx: TreeContext,
    p: ExtractionProposal,
    doc: Document,
    value: Any,
    *,
    now: dt.datetime,
    target_person_id: uuid.UUID | None,
    target_property_id: uuid.UUID | None,
    target_parcel_id: uuid.UUID | None,
) -> Applied:
    prov = _provenance(ctx, p, doc, now)
    fld = p.field
    if fld in SOURCE_FIELDS:
        return _apply_source_field(ctx, p, doc, value)
    if fld in KUNDLI_FIELDS:
        return _apply_kundli(ctx, p, doc, _person_id(ctx, p, doc, target_person_id), value, prov)
    if fld in BIRTH_EVENT_FIELDS:
        return _apply_birth_event(ctx, p, doc, _person_id(ctx, p, doc, target_person_id), value, prov)
    if fld == "name":
        return _apply_name(ctx, p, doc, _person_id(ctx, p, doc, target_person_id), value, prov)
    if fld == "sex":
        return _apply_sex(ctx, _person_id(ctx, p, doc, target_person_id), value)
    if fld in ("father_name", "mother_name"):
        return _apply_parent_name(ctx, p, doc, _person_id(ctx, p, doc, target_person_id), value, prov)
    if fld in PARCEL_COLUMNS or fld == "area" or fld in PARCEL_EXTRA_LISTS or fld in PARCEL_EXTRA_SCALARS:
        return _apply_land(ctx, p, doc, value, prov, target_property_id, target_parcel_id)
    raise Unprocessable(f"Proposals for '{fld}' cannot be applied automatically; record the value manually")
