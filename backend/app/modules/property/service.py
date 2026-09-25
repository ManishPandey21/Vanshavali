"""Ancestral property: properties, parcels, interests and events (PRS §17, §37; ADR-0010).

Authorisation (ADR-0006):

* **Read** needs ``property.read`` *and* ``level_allows`` on the property's privacy level (with the
  property's explicit grant). An explicit ``access_grant`` on the property also lets members without
  ``property.read`` (viewers, researchers) see it — that is the only way they ever see property.
* Holders of ``property.write`` (owner, family admin, property custodian) are the tree's designated
  property managers, so they see every property except ``PRIVATE_SELF`` (tree owner only) and
  ``CUSTOM`` (admins + explicit grants). Without this a custodian could not see the properties they
  are asked to maintain (the default level is ``PRIVATE_TREE_ADMINS``).
* ``FAMILY_BRANCH`` has no subject person for a property, so it resolves like
  ``PRIVATE_TREE_ADMINS`` plus grants.
* Not visible → 404. Visible but no ``property.write`` → 403.

Deletion policy: a property (or parcel) can be deleted only while it has no recorded history —
no interests, events, linked documents or citations (409 ``property_has_history`` otherwise).
History is ended through events or ``/end``, never erased.

This module records what documents and families say. It never computes statutory succession
shares and never treats an interest as legally verified title.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable, Sequence
from decimal import Decimal
from fractions import Fraction
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import level_allows
from app.core import audit
from app.core.dates import GenealogicalDate, date_to_json
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models import (
    Citation,
    Document,
    DocumentLink,
    Event,
    FamilyBranch,
    LandParcel,
    Property,
    PropertyEvent,
    PropertyEventParcel,
    PropertyInterest,
)
from app.models.enums import (
    OWNERSHIP_INTERESTS,
    CitationTarget,
    DocumentCategory,
    DocumentLinkTarget,
    GrantPermission,
    GrantResource,
    HolderType,
    InterestStatus,
    InterestType,
    PrivacyLevel,
    PropertyEventType,
)
from app.modules.genealogy import lookup
from app.modules.property.schemas import (
    EventInterestIn,
    HolderIn,
    InterestEndIn,
    InterestIn,
    InterestUpdate,
    ParcelFields,
    ParcelIn,
    ParcelUpdate,
    PartitionIn,
    PropertyEventIn,
    PropertyEventUpdate,
    PropertyIn,
    PropertyUpdate,
    SubdivideIn,
)
from app.modules.property.shares import find_violations, fraction_str, share_of

ENDED_STATUSES = frozenset({InterestStatus.TRANSFERRED, InterestStatus.RELINQUISHED})

# Document categories a property custodian may see in the vault (ADR-0006 §5).
PROPERTY_DOCUMENT_CATEGORIES = frozenset(
    {
        DocumentCategory.RECORD_OF_RIGHTS,
        DocumentCategory.KHATAUNI,
        DocumentCategory.JAMABANDI,
        DocumentCategory.KHASRA,
        DocumentCategory.RTC,
        DocumentCategory.PATTA,
        DocumentCategory.MUTATION_RECORD,
        DocumentCategory.CADASTRAL_MAP,
        DocumentCategory.TITLE_DEED,
        DocumentCategory.SALE_DEED,
        DocumentCategory.GIFT_DEED,
        DocumentCategory.PARTITION_DEED,
        DocumentCategory.FAMILY_SETTLEMENT,
        DocumentCategory.RELINQUISHMENT_DEED,
        DocumentCategory.WILL,
        DocumentCategory.PROBATE,
        DocumentCategory.SUCCESSION_CERTIFICATE,
        DocumentCategory.REVENUE_ORDER,
        DocumentCategory.COURT_ORDER,
        DocumentCategory.TAX_RECEIPT,
        DocumentCategory.MUNICIPAL_RECORD,
        DocumentCategory.ENCUMBRANCE,
        DocumentCategory.POSSESSION_RECORD,
    }
)

# Fields a subdivided child parcel inherits from its parent unless given explicitly.
_INHERITED_PARCEL_FIELDS = (
    "place_id",
    "state_or_ut",
    "district",
    "tehsil_taluk",
    "village",
    "revenue_village_code",
    "survey_number",
    "khata_number",
    "khatauni_number",
    "land_use",
)

_MAX_PARCEL_DEPTH = 100


# ================================================================ access
def can_view_property(ctx: TreeContext, p: Property) -> bool:
    if ctx.public or not ctx.is_member:
        return False
    level = PrivacyLevel(p.privacy_level)
    grant = (GrantResource.PROPERTY, p.id)
    if ctx.has(Permission.PROPERTY_WRITE) and level not in (PrivacyLevel.PRIVATE_SELF, PrivacyLevel.CUSTOM):
        return True
    if not level_allows(ctx, level, grant=grant):
        return False
    return ctx.has(Permission.PROPERTY_READ) or ctx.has_grant(
        GrantResource.PROPERTY, p.id, GrantPermission.VIEW
    )


def can_edit_property(ctx: TreeContext, p: Property) -> bool:
    return ctx.has(Permission.PROPERTY_WRITE) and can_view_property(ctx, p)


def get_property(ctx: TreeContext, property_id: uuid.UUID) -> Property:
    p = ctx.db.scalar(select(Property).where(Property.tree_id == ctx.tree_id, Property.id == property_id))
    if p is None or not can_view_property(ctx, p):
        raise NotFound("Property not found")
    return p


def get_property_for_write(ctx: TreeContext, property_id: uuid.UUID) -> Property:
    p = get_property(ctx, property_id)
    if not ctx.has(Permission.PROPERTY_WRITE):
        raise Forbidden()
    return p


def visible_properties(ctx: TreeContext, props: Iterable[Property]) -> list[Property]:
    return [p for p in props if can_view_property(ctx, p)]


def can_view_document(ctx: TreeContext, doc: Document) -> bool:
    """Metadata visibility for a linked document — delegates to the canonical documents rule
    (ADR-0006 §5). Bytes are never served from the property module."""
    from app.modules.documents.access import can_view_document as _canonical

    return doc.deleted_at is None and _canonical(ctx, doc)


# ================================================================ small helpers
def _date(d: GenealogicalDate | None) -> tuple[dict[str, Any] | None, dt.date | None]:
    return date_to_json(d), (d.sort_key() if d is not None else None)


def get_parcel(ctx: TreeContext, prop: Property, parcel_id: uuid.UUID) -> LandParcel:
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


def get_interest(ctx: TreeContext, prop: Property, interest_id: uuid.UUID) -> PropertyInterest:
    i = ctx.db.scalar(
        select(PropertyInterest).where(
            PropertyInterest.tree_id == ctx.tree_id,
            PropertyInterest.id == interest_id,
            PropertyInterest.property_id == prop.id,
        )
    )
    if i is None:
        raise NotFound("Interest not found")
    return i


def get_event(ctx: TreeContext, prop: Property, event_id: uuid.UUID) -> PropertyEvent:
    e = ctx.db.scalar(
        select(PropertyEvent).where(
            PropertyEvent.tree_id == ctx.tree_id,
            PropertyEvent.id == event_id,
            PropertyEvent.property_id == prop.id,
        )
    )
    if e is None:
        raise NotFound("Property event not found")
    return e


def property_interests(ctx: TreeContext, prop_id: uuid.UUID) -> list[PropertyInterest]:
    return list(
        ctx.db.scalars(
            select(PropertyInterest)
            .where(PropertyInterest.tree_id == ctx.tree_id, PropertyInterest.property_id == prop_id)
            .order_by(PropertyInterest.valid_from_sort.asc().nulls_first(), PropertyInterest.created_at)
        )
    )


def is_current(i: PropertyInterest, today: dt.date | None = None) -> bool:
    today = today or dt.date.today()
    if i.status in ENDED_STATUSES or i.ended_by_event_id is not None:
        return False
    if i.valid_to_sort is not None and i.valid_to_sort <= today:
        return False
    return not (i.valid_from_sort is not None and i.valid_from_sort > today)


def check_holder(ctx: TreeContext, h: HolderIn) -> None:
    """The holder must exist in this tree and be visible to the caller (404 otherwise)."""
    if h.holder_type == HolderType.PERSON and h.holder_person_id is not None:
        lookup.get_person(ctx, h.holder_person_id)
    elif h.holder_type == HolderType.FAMILY_BRANCH and h.holder_branch_id is not None:
        lookup.get_in_tree(ctx, FamilyBranch, h.holder_branch_id, "Branch")


def check_related_event(ctx: TreeContext, event_id: uuid.UUID) -> Event:
    """A genealogy life event (e.g. a death behind a succession): in-tree and visible, else 404."""
    from app.modules.genealogy.service import get_event_checked

    e, principal = get_event_checked(ctx, event_id)
    subject = lookup.get_person_subject(ctx, principal) if principal is not None else None
    if e.privacy_level is not None and not level_allows(ctx, e.privacy_level, subject=subject):
        raise NotFound("Event not found")
    return e


def check_documents(ctx: TreeContext, document_ids: Sequence[uuid.UUID]) -> list[Document]:
    docs = []
    for did in dict.fromkeys(document_ids):
        doc = lookup.get_in_tree(ctx, Document, did, "Document")
        if not can_view_document(ctx, doc):
            raise NotFound("Document not found")
        docs.append(doc)
    return docs


def _link_documents(
    ctx: TreeContext, docs: Sequence[Document], target_type: DocumentLinkTarget, target_id: uuid.UUID
) -> int:
    if not docs:
        return 0
    existing = set(
        ctx.db.scalars(
            select(DocumentLink.document_id).where(
                DocumentLink.tree_id == ctx.tree_id,
                DocumentLink.target_type == target_type,
                DocumentLink.target_id == target_id,
            )
        )
    )
    n = 0
    for d in docs:
        if d.id in existing:
            continue
        ctx.db.add(
            DocumentLink(
                tree_id=ctx.tree_id,
                document_id=d.id,
                target_type=target_type,
                target_id=target_id,
                created_by=ctx.user_id,
            )
        )
        n += 1
    return n


def enforce_share_invariant(ctx: TreeContext, prop: Property) -> None:
    """Documented owner/co_owner shares must never exceed the whole (ADR-0010). 422 otherwise."""
    ctx.db.flush()
    violations = find_violations(property_interests(ctx, prop.id))
    if violations:
        first = violations[0]
        where = "the property" if first.scope == "property" else "a parcel"
        when = first.at.isoformat() if first.at else "an undated period"
        raise Unprocessable(
            f"Documented ownership shares of {where} would add up to {fraction_str(first.total)} "
            f"(more than the whole) at {when}. Record overlapping claims as asserted or disputed.",
            code="shares_exceed_whole",
            details={"violations": [v.as_dict() for v in violations]},
        )


def _count(ctx: TreeContext, stmt: Any) -> int:
    return int(ctx.db.scalar(stmt) or 0)


# ================================================================ properties
def create_property(ctx: TreeContext, body: PropertyIn) -> Property:
    ctx.require(Permission.PROPERTY_WRITE)
    if body.place_id:
        lookup.get_place(ctx, body.place_id)
    p = Property(tree_id=ctx.tree_id, created_by=ctx.user_id, **body.model_dump())
    if not can_view_property(ctx, p):
        raise Unprocessable(
            "You would not be able to see a property at this privacy level", code="privacy_would_hide"
        )
    ctx.db.add(p)
    ctx.db.flush()
    audit.log(
        ctx,
        "property.created",
        target_type="property",
        target_id=p.id,
        details={"property_type": p.property_type.value, "privacy_level": p.privacy_level.value},
    )
    return p


def update_property(ctx: TreeContext, property_id: uuid.UUID, body: PropertyUpdate) -> Property:
    p = get_property_for_write(ctx, property_id)
    fields = body.model_fields_set
    if "place_id" in fields and body.place_id:
        lookup.get_place(ctx, body.place_id)
    for f in fields:
        setattr(p, f, getattr(body, f))
    if "privacy_level" in fields and not can_view_property(ctx, p):
        raise Unprocessable(
            "You would not be able to see this property at that privacy level", code="privacy_would_hide"
        )
    p.updated_by = ctx.user_id
    audit.log(
        ctx, "property.changed", target_type="property", target_id=p.id, details={"fields": sorted(fields)}
    )
    return p


def _history_counts(ctx: TreeContext, prop: Property, parcel_ids: list[uuid.UUID]) -> dict[str, int]:
    t = ctx.tree_id
    event_ids = list(
        ctx.db.scalars(
            select(PropertyEvent.id).where(PropertyEvent.tree_id == t, PropertyEvent.property_id == prop.id)
        )
    )
    interests = _count(
        ctx,
        select(func.count())
        .select_from(PropertyInterest)
        .where(PropertyInterest.tree_id == t, PropertyInterest.property_id == prop.id),
    )
    link_targets = [prop.id, *parcel_ids, *event_ids]
    docs = _count(
        ctx,
        select(func.count())
        .select_from(DocumentLink)
        .where(DocumentLink.tree_id == t, DocumentLink.target_id.in_(link_targets)),
    )
    cites = _count(
        ctx,
        select(func.count())
        .select_from(Citation)
        .where(
            Citation.tree_id == t,
            Citation.target_type.in_([CitationTarget.PROPERTY, CitationTarget.LAND_PARCEL]),
            Citation.target_id.in_([prop.id, *parcel_ids]),
        ),
    )
    return {"events": len(event_ids), "interests": interests, "documents": docs, "citations": cites}


def delete_property(ctx: TreeContext, property_id: uuid.UUID) -> None:
    p = get_property_for_write(ctx, property_id)
    parcel_ids = list(
        ctx.db.scalars(
            select(LandParcel.id).where(LandParcel.tree_id == ctx.tree_id, LandParcel.property_id == p.id)
        )
    )
    counts = _history_counts(ctx, p, parcel_ids)
    if any(counts.values()):
        raise Conflict(
            "This property has recorded history (interests, events, documents or citations) and cannot "
            "be deleted. End interests through events instead.",
            code="property_has_history",
            details=counts,
        )
    ctx.db.execute(
        sa_delete(LandParcel).where(LandParcel.tree_id == ctx.tree_id, LandParcel.property_id == p.id)
    )
    ctx.db.delete(p)
    audit.log(ctx, "property.deleted", target_type="property", target_id=p.id)


# ================================================================ parcels
def _check_parent_parcel(
    ctx: TreeContext, prop: Property, parcel: LandParcel | None, parent_id: uuid.UUID | None
) -> None:
    if parent_id is None:
        return
    get_parcel(ctx, prop, parent_id)  # same property only
    cur: uuid.UUID | None = parent_id
    depth = 0
    while cur is not None and depth < _MAX_PARCEL_DEPTH:
        if parcel is not None and cur == parcel.id:
            raise Unprocessable("Parcel lineage would contain a cycle", code="parcel_cycle")
        cur = ctx.db.scalar(
            select(LandParcel.parent_parcel_id).where(LandParcel.tree_id == ctx.tree_id, LandParcel.id == cur)
        )
        depth += 1


def _parcel_values(body: ParcelFields, fields: Iterable[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields:
        v = getattr(body, f)
        if f == "area_unit":
            v = v.value if v is not None else None
        elif f == "extra_identifiers":
            v = dict(v or {})
        out[f] = v
    return out


def _new_parcel(
    ctx: TreeContext, prop: Property, body: ParcelFields, parent_id: uuid.UUID | None
) -> LandParcel:
    if body.place_id:
        lookup.get_place(ctx, body.place_id)
    values = _parcel_values(body, [f for f in type(body).model_fields if f != "parent_parcel_id"])
    parcel = LandParcel(
        tree_id=ctx.tree_id,
        property_id=prop.id,
        parent_parcel_id=parent_id,
        created_by=ctx.user_id,
        **values,
    )
    ctx.db.add(parcel)
    return parcel


def create_parcel(ctx: TreeContext, property_id: uuid.UUID, body: ParcelIn) -> LandParcel:
    prop = get_property_for_write(ctx, property_id)
    _check_parent_parcel(ctx, prop, None, body.parent_parcel_id)
    parcel = _new_parcel(ctx, prop, body, body.parent_parcel_id)
    ctx.db.flush()
    audit.log(
        ctx,
        "property.parcel_added",
        target_type="land_parcel",
        target_id=parcel.id,
        details={"property_id": str(prop.id)},
    )
    return parcel


def update_parcel(
    ctx: TreeContext, property_id: uuid.UUID, parcel_id: uuid.UUID, body: ParcelUpdate
) -> LandParcel:
    prop = get_property_for_write(ctx, property_id)
    parcel = get_parcel(ctx, prop, parcel_id)
    fields = set(body.model_fields_set)
    if "parent_parcel_id" in fields:
        if body.parent_parcel_id == parcel.id:
            raise Unprocessable("A parcel cannot be its own parent", code="parcel_cycle")
        _check_parent_parcel(ctx, prop, parcel, body.parent_parcel_id)
    if "place_id" in fields and body.place_id:
        lookup.get_place(ctx, body.place_id)
    values = _parcel_values(body, fields - {"parent_parcel_id"})
    for f, v in values.items():
        setattr(parcel, f, v)
    if "parent_parcel_id" in fields:
        parcel.parent_parcel_id = body.parent_parcel_id
    if parcel.area is not None and not parcel.area_unit:
        raise Unprocessable("area_unit is required when area is given")
    parcel.updated_by = ctx.user_id
    audit.log(
        ctx,
        "property.parcel_changed",
        target_type="land_parcel",
        target_id=parcel.id,
        details={"property_id": str(prop.id), "fields": sorted(fields)},
    )
    return parcel


def delete_parcel(ctx: TreeContext, property_id: uuid.UUID, parcel_id: uuid.UUID) -> None:
    prop = get_property_for_write(ctx, property_id)
    parcel = get_parcel(ctx, prop, parcel_id)
    t = ctx.tree_id
    counts = {
        "interests": _count(
            ctx,
            select(func.count())
            .select_from(PropertyInterest)
            .where(PropertyInterest.tree_id == t, PropertyInterest.parcel_id == parcel.id),
        ),
        "events": _count(
            ctx,
            select(func.count())
            .select_from(PropertyEventParcel)
            .where(PropertyEventParcel.tree_id == t, PropertyEventParcel.parcel_id == parcel.id),
        ),
        "child_parcels": _count(
            ctx,
            select(func.count())
            .select_from(LandParcel)
            .where(LandParcel.tree_id == t, LandParcel.parent_parcel_id == parcel.id),
        ),
        "documents": _count(
            ctx,
            select(func.count())
            .select_from(DocumentLink)
            .where(
                DocumentLink.tree_id == t,
                DocumentLink.target_type == DocumentLinkTarget.LAND_PARCEL,
                DocumentLink.target_id == parcel.id,
            ),
        ),
        "citations": _count(
            ctx,
            select(func.count())
            .select_from(Citation)
            .where(
                Citation.tree_id == t,
                Citation.target_type == CitationTarget.LAND_PARCEL,
                Citation.target_id == parcel.id,
            ),
        ),
    }
    if any(counts.values()):
        raise Conflict(
            "This parcel has recorded history or subdivisions and cannot be deleted",
            code="property_has_history",
            details=counts,
        )
    ctx.db.delete(parcel)
    audit.log(
        ctx,
        "property.parcel_deleted",
        target_type="land_parcel",
        target_id=parcel.id,
        details={"property_id": str(prop.id)},
    )


def subdivide_parcel(
    ctx: TreeContext, property_id: uuid.UUID, parcel_id: uuid.UUID, body: SubdivideIn
) -> tuple[LandParcel, list[LandParcel], PropertyEvent | None, list[str]]:
    """Create child parcels of ``parcel_id`` (``parent_parcel_id`` lineage) and, by default, a
    ``subdivision`` event linking parent and children. Interests are not moved automatically:
    who holds each child parcel is recorded separately (never inferred)."""
    prop = get_property_for_write(ctx, property_id)
    parent = get_parcel(ctx, prop, parcel_id)
    docs = check_documents(ctx, body.document_ids)
    if docs and not body.record_event:
        raise Unprocessable("Documents are linked to the subdivision event; set record_event=true")
    children: list[LandParcel] = []
    for child_in in body.children:
        child = _new_parcel(ctx, prop, child_in, parent.id)
        for f in _INHERITED_PARCEL_FIELDS:
            if f not in child_in.model_fields_set and getattr(child, f) is None:
                setattr(child, f, getattr(parent, f))
        children.append(child)
    ctx.db.flush()
    warnings: list[str] = []
    if parent.area is not None and parent.area_unit:
        same_unit = [c for c in children if c.area is not None and c.area_unit == parent.area_unit]
        total = sum((Decimal(c.area) for c in same_unit if c.area is not None), Decimal(0))
        if same_unit and total > Decimal(parent.area):
            warnings.append(
                "The recorded areas of the new parcels add up to more than the parent parcel's area "
                f"(in {parent.area_unit}). Check the records."
            )
    event: PropertyEvent | None = None
    if body.record_event:
        date_json, date_sort = _date(body.date)
        event = PropertyEvent(
            tree_id=ctx.tree_id,
            property_id=prop.id,
            type=PropertyEventType.SUBDIVISION,
            date=date_json,
            date_sort_from=date_sort,
            description=body.description,
            evidence_status=body.evidence_status,
            created_by=ctx.user_id,
        )
        ctx.db.add(event)
        ctx.db.flush()
        for pid in [parent.id, *(c.id for c in children)]:
            ctx.db.add(
                PropertyEventParcel(
                    tree_id=ctx.tree_id, property_event_id=event.id, parcel_id=pid, created_by=ctx.user_id
                )
            )
        _link_documents(ctx, docs, DocumentLinkTarget.PROPERTY_EVENT, event.id)
        ctx.db.flush()
    audit.log(
        ctx,
        "property.parcel_subdivided",
        target_type="land_parcel",
        target_id=parent.id,
        details={
            "property_id": str(prop.id),
            "children": len(children),
            "event_id": str(event.id) if event else None,
        },
    )
    return parent, children, event, warnings


# ================================================================ interests
def _new_interest(
    ctx: TreeContext,
    prop: Property,
    body: InterestIn,
    *,
    created_by_event: PropertyEvent | None = None,
    default_from: GenealogicalDate | None = None,
) -> PropertyInterest:
    check_holder(ctx, body)
    if body.parcel_id is not None:
        get_parcel(ctx, prop, body.parcel_id)
    valid_from = body.valid_from if "valid_from" in body.model_fields_set else default_from
    vf_json, vf_sort = _date(valid_from)
    vt_json, vt_sort = _date(body.valid_to)
    if vf_sort and vt_sort and vt_sort < vf_sort:
        raise Unprocessable("valid_to is before valid_from", code="invalid_period")
    i = PropertyInterest(
        tree_id=ctx.tree_id,
        property_id=prop.id,
        parcel_id=body.parcel_id,
        holder_type=body.holder_type,
        holder_person_id=body.holder_person_id,
        holder_branch_id=body.holder_branch_id,
        holder_name=(body.holder_name or "").strip() or None,
        interest_type=body.interest_type,
        share_numerator=body.share_numerator,
        share_denominator=body.share_denominator,
        valid_from=vf_json,
        valid_from_sort=vf_sort,
        valid_to=vt_json,
        valid_to_sort=vt_sort,
        status=body.status,
        evidence_status=body.evidence_status,
        confidence=body.confidence,
        notes=body.notes,
        created_by_event_id=created_by_event.id if created_by_event else None,
        created_by=ctx.user_id,
    )
    ctx.db.add(i)
    return i


def _audit_interest(ctx: TreeContext, prop: Property, i: PropertyInterest, change: str, **extra: Any) -> None:
    """PRS §34 "property ownership assertion changed". Field names only — never shares or names."""
    audit.log(
        ctx,
        "property.interest_changed",
        target_type="property_interest",
        target_id=i.id,
        details={"property_id": str(prop.id), "change": change, **extra},
    )


def create_interest(ctx: TreeContext, property_id: uuid.UUID, body: InterestIn) -> PropertyInterest:
    prop = get_property_for_write(ctx, property_id)
    i = _new_interest(ctx, prop, body)
    enforce_share_invariant(ctx, prop)
    _audit_interest(ctx, prop, i, "created", holder_type=i.holder_type.value, status=i.status.value)
    return i


def update_interest(
    ctx: TreeContext, property_id: uuid.UUID, interest_id: uuid.UUID, body: InterestUpdate
) -> PropertyInterest:
    prop = get_property_for_write(ctx, property_id)
    i = get_interest(ctx, prop, interest_id)
    fields = set(body.model_fields_set)
    if "parcel_id" in fields and body.parcel_id is not None:
        get_parcel(ctx, prop, body.parcel_id)
    for f in fields:
        v = getattr(body, f)
        if f in ("valid_from", "valid_to"):
            j, s = _date(v)
            setattr(i, f, j)
            setattr(i, f"{f}_sort", s)
        elif f == "holder_name":
            i.holder_name = (v or "").strip() or None
        else:
            setattr(i, f, v)
    if i.share_numerator > i.share_denominator:
        raise Unprocessable("A share cannot exceed the whole (numerator ≤ denominator)")
    if i.valid_from_sort and i.valid_to_sort and i.valid_to_sort < i.valid_from_sort:
        raise Unprocessable("valid_to is before valid_from", code="invalid_period")
    i.updated_by = ctx.user_id
    enforce_share_invariant(ctx, prop)
    _audit_interest(ctx, prop, i, "updated", fields=sorted(fields))
    return i


def end_interest(
    ctx: TreeContext, property_id: uuid.UUID, interest_id: uuid.UUID, body: InterestEndIn
) -> PropertyInterest:
    prop = get_property_for_write(ctx, property_id)
    i = get_interest(ctx, prop, interest_id)
    if i.valid_to is not None or i.ended_by_event_id is not None or i.status in ENDED_STATUSES:
        raise Conflict("This interest has already ended", code="interest_already_ended")
    j, s = _date(body.valid_to)
    if s is None:
        raise Unprocessable("An end date with at least a year is required", code="event_date_required")
    if i.valid_from_sort and s < i.valid_from_sort:
        raise Unprocessable("valid_to is before valid_from", code="invalid_period")
    i.valid_to, i.valid_to_sort = j, s
    i.status = InterestStatus(body.status)
    if body.notes is not None:
        i.notes = body.notes
    i.updated_by = ctx.user_id
    enforce_share_invariant(ctx, prop)
    _audit_interest(ctx, prop, i, "ended", status=i.status.value)
    return i


def delete_interest(ctx: TreeContext, property_id: uuid.UUID, interest_id: uuid.UUID) -> None:
    """Remove a mistaken entry. Interests created or ended by an event are history: 409."""
    prop = get_property_for_write(ctx, property_id)
    i = get_interest(ctx, prop, interest_id)
    cites = _count(
        ctx,
        select(func.count())
        .select_from(Citation)
        .where(
            Citation.tree_id == ctx.tree_id,
            Citation.target_type == CitationTarget.PROPERTY_INTEREST,
            Citation.target_id == i.id,
        ),
    )
    if i.created_by_event_id or i.ended_by_event_id or cites:
        raise Conflict(
            "This interest is part of the recorded history (events or citations); end it instead",
            code="property_has_history",
        )
    ctx.db.delete(i)
    _audit_interest(ctx, prop, i, "deleted")


# ================================================================ events
def _require_sortable_date(d: GenealogicalDate | None) -> None:
    if d is None or d.sort_key() is None:
        raise Unprocessable(
            "Events that end or create interests need a date (at least a year)",
            code="event_date_required",
        )


def _ended_status(event_type: PropertyEventType, override: str | None) -> InterestStatus:
    if override:
        return InterestStatus(override)
    if event_type == PropertyEventType.RELINQUISHMENT:
        return InterestStatus.RELINQUISHED
    return InterestStatus.TRANSFERRED


def record_event(ctx: TreeContext, property_id: uuid.UUID, body: PropertyEventIn) -> PropertyEvent:
    """One transaction: the event, its parcels, the interests it ends and the ones it creates,
    linked documents — then the documented-share invariant is enforced at every date."""
    prop = get_property_for_write(ctx, property_id)
    changes_interests = bool(body.ends_interest_ids or body.creates_interests)
    if changes_interests:
        _require_sortable_date(body.date)
    parcel_ids = list(dict.fromkeys(body.parcel_ids))
    for pid in parcel_ids:
        get_parcel(ctx, prop, pid)
    if body.related_event_id:
        check_related_event(ctx, body.related_event_id)
    docs = check_documents(ctx, body.document_ids)
    date_json, date_sort = _date(body.date)
    ev = PropertyEvent(
        tree_id=ctx.tree_id,
        property_id=prop.id,
        type=body.type,
        date=date_json,
        date_sort_from=date_sort,
        description=body.description,
        registration_number=body.registration_number,
        registration_date=date_to_json(body.registration_date),
        mutation_number=body.mutation_number,
        consideration=body.consideration,
        related_event_id=body.related_event_id,
        evidence_status=body.evidence_status,
        confidence=body.confidence,
        created_by=ctx.user_id,
    )
    ctx.db.add(ev)
    ctx.db.flush()

    ended: list[PropertyInterest] = []
    end_status = _ended_status(body.type, body.end_status)
    for iid in dict.fromkeys(body.ends_interest_ids):
        i = get_interest(ctx, prop, iid)
        if i.valid_to is not None or i.ended_by_event_id is not None or i.status in ENDED_STATUSES:
            raise Conflict(
                "An interest in ends_interest_ids has already ended",
                code="interest_already_ended",
                details={"interest_id": str(i.id)},
            )
        if i.valid_from_sort and date_sort and date_sort < i.valid_from_sort:
            raise Unprocessable(
                "The event is dated before an interest it ends began",
                code="invalid_period",
                details={"interest_id": str(i.id)},
            )
        i.valid_to, i.valid_to_sort = date_json, date_sort
        i.ended_by_event_id = ev.id
        i.status = end_status
        i.updated_by = ctx.user_id
        ended.append(i)
        if i.parcel_id and i.parcel_id not in parcel_ids:
            parcel_ids.append(i.parcel_id)

    created: list[PropertyInterest] = []
    for spec in body.creates_interests:
        i = _new_interest(ctx, prop, spec, created_by_event=ev, default_from=body.date)
        created.append(i)
        if spec.parcel_id and spec.parcel_id not in parcel_ids:
            parcel_ids.append(spec.parcel_id)

    for pid in parcel_ids:
        ctx.db.add(
            PropertyEventParcel(
                tree_id=ctx.tree_id, property_event_id=ev.id, parcel_id=pid, created_by=ctx.user_id
            )
        )
    n_docs = _link_documents(ctx, docs, DocumentLinkTarget.PROPERTY_EVENT, ev.id)
    enforce_share_invariant(ctx, prop)
    audit.log(
        ctx,
        "property.event_recorded",
        target_type="property_event",
        target_id=ev.id,
        details={
            "property_id": str(prop.id),
            "type": ev.type.value,
            "parcels": len(parcel_ids),
            "interests_ended": len(ended),
            "interests_created": len(created),
            "documents_linked": n_docs,
        },
    )
    if changes_interests:
        audit.log(
            ctx,
            "property.interest_changed",
            target_type="property",
            target_id=prop.id,
            details={
                "change": "event",
                "event_id": str(ev.id),
                "event_type": ev.type.value,
                "ended": [str(i.id) for i in ended],
                "created": [str(i.id) for i in created],
            },
        )
    return ev


def update_event(
    ctx: TreeContext, property_id: uuid.UUID, event_id: uuid.UUID, body: PropertyEventUpdate
) -> PropertyEvent:
    """Descriptive fields only. The date and the interests an event changed are history."""
    prop = get_property_for_write(ctx, property_id)
    ev = get_event(ctx, prop, event_id)
    fields = set(body.model_fields_set)
    if "related_event_id" in fields and body.related_event_id is not None:
        check_related_event(ctx, body.related_event_id)
    for f in fields:
        v = getattr(body, f)
        if f == "registration_date":
            v = date_to_json(v)
        setattr(ev, f, v)
    ev.updated_by = ctx.user_id
    audit.log(
        ctx,
        "property.event_changed",
        target_type="property_event",
        target_id=ev.id,
        details={"property_id": str(prop.id), "fields": sorted(fields)},
    )
    return ev


# ================================================================ partition
def _auto_partition_ends(
    ctx: TreeContext, prop: Property, at: dt.date, parcel_ids: list[uuid.UUID] | None
) -> list[PropertyInterest]:
    """Current owner/co_owner interests (documented or asserted) at ``at`` in the partition's scope:
    property-wide interests when no parcels are named, else interests on the named parcels."""
    from app.modules.property.shares import active_at

    out = []
    for i in property_interests(ctx, prop.id):
        if i.interest_type not in OWNERSHIP_INTERESTS:
            continue
        if i.status not in (InterestStatus.DOCUMENTED, InterestStatus.ASSERTED):
            continue
        if i.valid_to is not None or i.ended_by_event_id is not None or not active_at(i, at):
            continue
        if parcel_ids:
            if i.parcel_id in parcel_ids:
                out.append(i)
        elif i.parcel_id is None:
            out.append(i)
    return out


def record_partition(ctx: TreeContext, property_id: uuid.UUID, body: PartitionIn) -> PropertyEvent:
    """Record a partition as a ``partition`` event that ends the partitioned interests and creates
    the allocated ones, in one transaction.

    Balance rule (unless ``allow_partial=true``): allocations are grouped by scope. Property-wide
    allocations must add up exactly to the property-wide shares ended. Allocations on parcel P must
    add up exactly to the property-wide shares ended plus the shares on P that were ended (a
    property-wide holder also held P). Every parcel whose interests were ended must be allocated,
    and when a property-wide share ended and allocations are parcel-wise only, every parcel in the
    partition scope (``parcel_ids``, else all the property's parcels) must be allocated. A partial
    deed (some shares left unallocated or allocated elsewhere) needs ``allow_partial=true``.
    """
    prop = get_property_for_write(ctx, property_id)
    _require_sortable_date(body.date)
    at = body.date.sort_key()
    if at is None:
        raise Unprocessable("A partition needs a date with at least a year", code="event_date_required")
    scope_parcels = list(dict.fromkeys(body.parcel_ids or []))
    for pid in scope_parcels:
        get_parcel(ctx, prop, pid)
    for a in body.allocations:
        if a.parcel_id is not None:
            get_parcel(ctx, prop, a.parcel_id)
            if scope_parcels and a.parcel_id not in scope_parcels:
                raise Unprocessable(
                    "An allocation names a parcel outside the partition's parcel_ids",
                    code="allocation_out_of_scope",
                    details={"parcel_id": str(a.parcel_id)},
                )

    if body.ends_interest_ids is None:
        ends = _auto_partition_ends(ctx, prop, at, scope_parcels or None)
    else:
        ends = [get_interest(ctx, prop, iid) for iid in dict.fromkeys(body.ends_interest_ids)]

    owned = [i for i in ends if i.interest_type in OWNERSHIP_INTERESTS]
    ended_wide = sum((share_of(i) for i in owned if i.parcel_id is None), Fraction(0))
    ended_parcel: dict[uuid.UUID, Fraction] = {}
    for i in owned:
        if i.parcel_id is not None:
            ended_parcel[i.parcel_id] = ended_parcel.get(i.parcel_id, Fraction(0)) + share_of(i)
    alloc: dict[uuid.UUID | None, Fraction] = {}
    for a in body.allocations:
        alloc[a.parcel_id] = alloc.get(a.parcel_id, Fraction(0)) + Fraction(
            a.share_numerator, a.share_denominator
        )

    if not body.allow_partial:
        mismatches: list[dict[str, Any]] = []
        if not owned:
            raise Unprocessable(
                "No current ownership interests to partition; pass ends_interest_ids or allow_partial=true",
                code="allocation_mismatch",
            )
        for scope, total in alloc.items():
            expected = ended_wide if scope is None else ended_wide + ended_parcel.get(scope, Fraction(0))
            if total != expected:
                mismatches.append(
                    {
                        "parcel_id": str(scope) if scope else None,
                        "allocated": fraction_str(total),
                        "ended": fraction_str(expected),
                    }
                )
        for pid, total in ended_parcel.items():
            if pid not in alloc:
                mismatches.append({"parcel_id": str(pid), "allocated": "0/1", "ended": fraction_str(total)})
        if ended_wide > 0 and None not in alloc:
            required = scope_parcels or list(
                ctx.db.scalars(
                    select(LandParcel.id).where(
                        LandParcel.tree_id == ctx.tree_id, LandParcel.property_id == prop.id
                    )
                )
            )
            for pid in required:
                if pid not in alloc:
                    mismatches.append(
                        {"parcel_id": str(pid), "allocated": "0/1", "ended": fraction_str(ended_wide)}
                    )
        if ended_wide > 0 and None in alloc and any(k is not None for k in alloc):
            mismatches.append(
                {
                    "parcel_id": None,
                    "allocated": "mixed",
                    "ended": fraction_str(ended_wide),
                    "reason": "allocations mix property-wide and parcel-wise shares",
                }
            )
        if mismatches:
            raise Unprocessable(
                "Allocations do not add up to the shares being partitioned. Set allow_partial=true to "
                "record a partial partition.",
                code="allocation_mismatch",
                details={"mismatches": mismatches},
            )

    creates = []
    for a in body.allocations:
        share = Fraction(a.share_numerator, a.share_denominator)
        itype = a.interest_type or (InterestType.OWNER if share == 1 else InterestType.CO_OWNER)
        creates.append(
            EventInterestIn(
                holder_type=a.holder_type,
                holder_person_id=a.holder_person_id,
                holder_branch_id=a.holder_branch_id,
                holder_name=a.holder_name,
                share_numerator=a.share_numerator,
                share_denominator=a.share_denominator,
                parcel_id=a.parcel_id,
                interest_type=itype,
                status=body.status,
                evidence_status=body.evidence_status,
                confidence=body.confidence,
            )
        )
    ev = record_event(
        ctx,
        prop.id,
        PropertyEventIn(
            type=PropertyEventType.PARTITION,
            date=body.date,
            description=body.description,
            registration_number=body.registration_number,
            registration_date=body.registration_date,
            related_event_id=body.related_event_id,
            parcel_ids=scope_parcels,
            ends_interest_ids=[i.id for i in ends],
            creates_interests=creates,
            document_ids=body.document_ids,
            evidence_status=body.evidence_status,
            confidence=body.confidence,
        ),
    )
    audit.log(
        ctx,
        "property.partition_recorded",
        target_type="property_event",
        target_id=ev.id,
        details={
            "property_id": str(prop.id),
            "allocations": len(body.allocations),
            "interests_ended": len(ends),
            "allow_partial": body.allow_partial,
        },
    )
    return ev


# ================================================================ queries
def list_properties(
    ctx: TreeContext,
    property_type: Any = None,
    classification: Any = None,
    q: str | None = None,
) -> list[Property]:
    stmt = select(Property).where(Property.tree_id == ctx.tree_id)
    if property_type:
        stmt = stmt.where(Property.property_type == property_type)
    if classification:
        stmt = stmt.where(Property.classification == classification)
    if q:
        like = f"%{q.strip()}%"
        parcel_match = select(LandParcel.property_id).where(
            LandParcel.tree_id == ctx.tree_id, or_(*[c.ilike(like) for c in parcel_identifier_columns()])
        )
        stmt = stmt.where(or_(Property.display_name.ilike(like), Property.id.in_(parcel_match)))
    return visible_properties(ctx, ctx.db.scalars(stmt.order_by(Property.display_name, Property.id)))


def parcel_identifier_columns() -> list[Any]:
    return [
        LandParcel.survey_number,
        LandParcel.khasra_or_gata_number,
        LandParcel.khata_number,
        LandParcel.khatauni_number,
        LandParcel.patta_number,
        LandParcel.plot_number,
        LandParcel.subdivision_number,
        LandParcel.ulpin,
    ]
