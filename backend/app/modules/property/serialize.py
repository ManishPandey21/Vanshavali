"""Privacy-aware serialisation of property objects (ADR-0006, ADR-0010).

Person holders go through the genealogy ``Serializer`` summaries; a holder the caller may not see
is returned as ``{"hidden": true}`` with no id or name. Linked documents are metadata only
(never bytes or storage keys) and only when the caller can see the document.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from fractions import Fraction
from typing import Any

from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.privacy import is_private_record_level
from app.core.errors import NotFound
from app.models import (
    Citation,
    Document,
    DocumentLink,
    EventParticipant,
    FamilyBranch,
    LandParcel,
    Place,
    Property,
    PropertyEvent,
    PropertyEventParcel,
    PropertyInterest,
)
from app.models.enums import (
    OWNERSHIP_INTERESTS,
    CitationTarget,
    DocumentLinkTarget,
    HolderType,
    InterestStatus,
    ParticipantRole,
    PropertyEventType,
)
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import PersonSummary, ProvenanceOut
from app.modules.genealogy.serialize import Serializer, citation_counts, date_display
from app.modules.property import service
from app.modules.property.schemas import (
    DocumentRef,
    HolderOut,
    HoldersAtOut,
    InterestOut,
    LineageChain,
    LineageOut,
    ParcelGroupOut,
    ParcelOut,
    ParcelRef,
    PropertyCounts,
    PropertyDetailOut,
    PropertyEventOut,
    PropertyOut,
    RelatedEventOut,
    TimelineOut,
    TransferOut,
)
from app.modules.property.shares import active_at, fraction_str, share_of
from app.modules.property.units import to_sq_m

_TRANSFER_OUT_TYPES = frozenset(
    {PropertyEventType.RELINQUISHMENT, PropertyEventType.SALE, PropertyEventType.GIFT}
)
_RECORDED_STATUSES = frozenset(
    {InterestStatus.DOCUMENTED, InterestStatus.TRANSFERRED, InterestStatus.RELINQUISHED}
)


def parcel_label(p: LandParcel) -> str:
    ident = None
    for prefix, value in (
        ("Khasra/Gata", p.khasra_or_gata_number),
        ("Survey", p.survey_number),
        ("Plot", p.plot_number),
        ("Patta", p.patta_number),
        ("Khata", p.khata_number),
        ("Khatauni", p.khatauni_number),
        ("ULPIN", p.ulpin),
    ):
        if value:
            ident = f"{prefix} {value}"
            break
    if ident and p.subdivision_number:
        ident = f"{ident}/{p.subdivision_number}"
    ident = ident or f"Parcel {str(p.id)[:8]}"
    return f"{ident} ({p.village})" if p.village else ident


def parcel_sort_key(p: LandParcel) -> tuple[Any, ...]:
    """Creation order; parcels created together (a subdivision) fall back to a natural label order."""
    natural = tuple(int(x) if x.isdigit() else x for x in re.split(r"(\d+)", parcel_label(p)))
    return (p.created_at, natural, str(p.id))


def parcel_ref(p: LandParcel) -> ParcelRef:
    return ParcelRef(id=p.id, label=parcel_label(p), parent_parcel_id=p.parent_parcel_id)


def has_overlapping_claims(interests: Iterable[PropertyInterest]) -> bool:
    """True when active ownership claims of any status exceed the whole (e.g. a dispute)."""
    wide = Fraction(0)
    per_parcel: dict[uuid.UUID, Fraction] = defaultdict(Fraction)
    for i in interests:
        if i.interest_type not in OWNERSHIP_INTERESTS:
            continue
        if i.parcel_id is None:
            wide += share_of(i)
        else:
            per_parcel[i.parcel_id] += share_of(i)
    return wide > 1 or any(wide + v > 1 for v in per_parcel.values())


def _recorded_total(interests: Iterable[PropertyInterest]) -> Fraction:
    return sum(
        (
            share_of(i)
            for i in interests
            if i.parcel_id is None
            and i.interest_type in OWNERSHIP_INTERESTS
            and i.status in _RECORDED_STATUSES
        ),
        Fraction(0),
    )


class PropertySerializer:
    def __init__(self, ctx: TreeContext) -> None:
        self.ctx = ctx
        self.gs = Serializer(ctx)
        self._people: dict[uuid.UUID, PersonSummary | None] = {}
        self._branches: dict[uuid.UUID, str | None] = {}

    # ------------------------------------------------------------ holders
    def person_summaries(self, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, PersonSummary | None]:
        missing = {i for i in ids if i is not None and i not in self._people}
        if missing:
            subjects = lookup.visible_subjects(self.ctx, missing)
            summaries = self.gs.summaries(subjects)
            for pid in missing:
                self._people[pid] = summaries.get(pid)
        return self._people

    def _prime(self, interests: Iterable[PropertyInterest]) -> None:
        interests = list(interests)
        self.person_summaries(i.holder_person_id for i in interests)
        missing = {i.holder_branch_id for i in interests if i.holder_branch_id} - set(self._branches)
        if missing:
            names = dict(
                self.ctx.db.execute(
                    select(FamilyBranch.id, FamilyBranch.name).where(
                        FamilyBranch.tree_id == self.ctx.tree_id, FamilyBranch.id.in_(missing)
                    )
                ).all()
            )
            for bid in missing:
                self._branches[bid] = names.get(bid)

    def holder_out(self, i: PropertyInterest) -> HolderOut:
        if i.holder_type == HolderType.PERSON and i.holder_person_id:
            summary = self.person_summaries([i.holder_person_id]).get(i.holder_person_id)
            if summary is None:
                return HolderOut(type=i.holder_type, hidden=True)
            return HolderOut(
                type=i.holder_type,
                person_id=summary.id,
                display_name=summary.display_name,
                name=i.holder_name,
                person=summary,
            )
        if i.holder_type == HolderType.FAMILY_BRANCH and i.holder_branch_id:
            self._prime([i])
            bname = self._branches.get(i.holder_branch_id)
            return HolderOut(
                type=i.holder_type,
                branch_id=i.holder_branch_id,
                name=i.holder_name,
                display_name=bname or i.holder_name,
            )
        return HolderOut(
            type=i.holder_type,
            name=i.holder_name,
            display_name=i.holder_name or ("Unknown holder" if i.holder_type == HolderType.UNKNOWN else None),
        )

    # ------------------------------------------------------------ interests
    def interest_out(self, i: PropertyInterest, cites: dict[uuid.UUID, int] | None = None) -> InterestOut:
        share = share_of(i)
        return InterestOut(
            id=i.id,
            property_id=i.property_id,
            parcel_id=i.parcel_id,
            holder=self.holder_out(i),
            interest_type=i.interest_type,
            share_numerator=i.share_numerator,
            share_denominator=i.share_denominator,
            share=fraction_str(share),
            share_percent=round(float(share * 100), 4),
            valid_from=i.valid_from,
            valid_from_display=date_display(i.valid_from),
            valid_to=i.valid_to,
            valid_to_display=date_display(i.valid_to),
            status=i.status,
            is_current=service.is_current(i),
            counts_toward_whole=i.interest_type in OWNERSHIP_INTERESTS
            and i.status == InterestStatus.DOCUMENTED,
            evidence_status=i.evidence_status,
            confidence=i.confidence,
            created_by_event_id=i.created_by_event_id,
            ended_by_event_id=i.ended_by_event_id,
            notes=i.notes,
            citation_count=(cites or {}).get(i.id, 0),
            provenance=ProvenanceOut.of(i),
        )

    def interests_out(self, interests: list[PropertyInterest]) -> list[InterestOut]:
        self._prime(interests)
        cites = citation_counts(self.ctx, CitationTarget.PROPERTY_INTEREST, {i.id for i in interests})
        return [self.interest_out(i, cites) for i in interests]

    # ------------------------------------------------------------ parcels
    def parcel_out(self, p: LandParcel, child_count: int | None = None) -> ParcelOut:
        if child_count is None:
            child_count = int(
                self.ctx.db.scalar(
                    select(func.count())
                    .select_from(LandParcel)
                    .where(LandParcel.tree_id == self.ctx.tree_id, LandParcel.parent_parcel_id == p.id)
                )
                or 0
            )
        sq_m, note = to_sq_m(p.area, p.area_unit)  # type: ignore[arg-type]
        return ParcelOut(
            id=p.id,
            property_id=p.property_id,
            parent_parcel_id=p.parent_parcel_id,
            label=parcel_label(p),
            place_id=p.place_id,
            state_or_ut=p.state_or_ut,
            district=p.district,
            tehsil_taluk=p.tehsil_taluk,
            village=p.village,
            revenue_village_code=p.revenue_village_code,
            survey_number=p.survey_number,
            khasra_or_gata_number=p.khasra_or_gata_number,
            khata_number=p.khata_number,
            khatauni_number=p.khatauni_number,
            patta_number=p.patta_number,
            plot_number=p.plot_number,
            subdivision_number=p.subdivision_number,
            ulpin=p.ulpin,
            area=p.area,  # type: ignore[arg-type]
            area_unit=p.area_unit,
            area_sq_m=sq_m,
            area_conversion_note=note,
            land_use=p.land_use,
            latitude=float(p.latitude) if p.latitude is not None else None,
            longitude=float(p.longitude) if p.longitude is not None else None,
            cadastral_map_reference=p.cadastral_map_reference,
            state_portal_reference=p.state_portal_reference,
            extra_identifiers=dict(p.extra_identifiers or {}),
            notes=p.notes,
            child_count=child_count,
            provenance=ProvenanceOut.of(p),
            created_at=p.created_at,
        )

    def parcels_of(self, prop: Property) -> list[LandParcel]:
        rows = self.ctx.db.scalars(
            select(LandParcel).where(
                LandParcel.tree_id == self.ctx.tree_id, LandParcel.property_id == prop.id
            )
        )
        return sorted(rows, key=parcel_sort_key)

    def parcels_out(self, parcels: list[LandParcel]) -> list[ParcelOut]:
        children: dict[uuid.UUID, int] = defaultdict(int)
        for p in parcels:
            if p.parent_parcel_id:
                children[p.parent_parcel_id] += 1
        return [self.parcel_out(p, children.get(p.id, 0)) for p in parcels]

    # ------------------------------------------------------------ properties
    def property_out(self, p: Property, parcel_count: int | None = None) -> PropertyOut:
        ctx = self.ctx
        if parcel_count is None:
            parcel_count = int(
                ctx.db.scalar(
                    select(func.count())
                    .select_from(LandParcel)
                    .where(LandParcel.tree_id == ctx.tree_id, LandParcel.property_id == p.id)
                )
                or 0
            )
        place_name = (
            ctx.db.scalar(
                select(Place.canonical_name).where(Place.tree_id == ctx.tree_id, Place.id == p.place_id)
            )
            if p.place_id
            else None
        )
        return PropertyOut(
            id=p.id,
            property_type=p.property_type,
            classification=p.classification,
            display_name=p.display_name,
            description=p.description,
            place_id=p.place_id,
            place_name=place_name,
            address_text=p.address_text,
            current_status=p.current_status,
            privacy_level=p.privacy_level,
            parcel_count=parcel_count,
            can_edit=service.can_edit_property(ctx, p),
            created_at=p.created_at,
            updated_at=p.updated_at,
        )

    def properties_out(self, props: list[Property]) -> list[PropertyOut]:
        if not props:
            return []
        counts = dict(
            self.ctx.db.execute(
                select(LandParcel.property_id, func.count())
                .where(
                    LandParcel.tree_id == self.ctx.tree_id, LandParcel.property_id.in_([p.id for p in props])
                )
                .group_by(LandParcel.property_id)
            ).all()
        )
        return [self.property_out(p, int(counts.get(p.id, 0))) for p in props]

    # ------------------------------------------------------------ documents
    def documents_for(
        self, targets: list[tuple[DocumentLinkTarget, uuid.UUID]]
    ) -> tuple[dict[uuid.UUID, list[DocumentRef]], dict[uuid.UUID, int]]:
        """Visible linked documents per target id, and the count of hidden ones per target."""
        visible: dict[uuid.UUID, list[DocumentRef]] = defaultdict(list)
        hidden: dict[uuid.UUID, int] = defaultdict(int)
        if not targets:
            return visible, hidden
        by_type: dict[DocumentLinkTarget, list[uuid.UUID]] = defaultdict(list)
        for t, tid in targets:
            by_type[t].append(tid)
        for ttype, ids in by_type.items():
            rows = self.ctx.db.execute(
                select(DocumentLink, Document)
                .join(
                    Document,
                    (Document.id == DocumentLink.document_id) & (Document.tree_id == DocumentLink.tree_id),
                )
                .where(
                    DocumentLink.tree_id == self.ctx.tree_id,
                    DocumentLink.target_type == ttype,
                    DocumentLink.target_id.in_(ids),
                )
                .order_by(DocumentLink.created_at)
            ).all()
            for link, doc in rows:
                if doc.deleted_at is not None:
                    continue
                if not service.can_view_document(self.ctx, doc):
                    # ADR-0027 §1: someone else's private record is not even counted
                    if not is_private_record_level(doc.privacy_level):
                        hidden[link.target_id] += 1
                    continue
                visible[link.target_id].append(
                    DocumentRef(
                        id=doc.id,
                        title=doc.title,
                        category=doc.category,
                        privacy_level=doc.privacy_level,
                        linked_to=link.target_type,
                        linked_id=link.target_id,
                        note=link.note,
                    )
                )
        return visible, hidden

    # ------------------------------------------------------------ events
    def related_event_out(self, event_id: uuid.UUID) -> RelatedEventOut:
        try:
            e = service.check_related_event(self.ctx, event_id)
        except NotFound:
            return RelatedEventOut(id=event_id, hidden=True)
        principal_id = self.ctx.db.scalar(
            select(EventParticipant.person_id)
            .where(
                EventParticipant.tree_id == self.ctx.tree_id,
                EventParticipant.event_id == e.id,
                EventParticipant.role == ParticipantRole.PRINCIPAL,
            )
            .limit(1)
        )
        principal = self.person_summaries([principal_id]).get(principal_id) if principal_id else None
        return RelatedEventOut(id=e.id, type=e.type, date_display=date_display(e.date), principal=principal)

    def events_out(
        self, prop: Property, events: list[PropertyEvent], interests: list[PropertyInterest] | None = None
    ) -> dict[uuid.UUID, PropertyEventOut]:
        ctx = self.ctx
        if not events:
            return {}
        ids = [e.id for e in events]
        if interests is None:
            interests = service.property_interests(ctx, prop.id)
        interest_outs = {o.id: o for o in self.interests_out(interests)}
        created: dict[uuid.UUID, list[InterestOut]] = defaultdict(list)
        ended: dict[uuid.UUID, list[InterestOut]] = defaultdict(list)
        for i in interests:
            if i.created_by_event_id:
                created[i.created_by_event_id].append(interest_outs[i.id])
            if i.ended_by_event_id:
                ended[i.ended_by_event_id].append(interest_outs[i.id])
        parcel_rows = ctx.db.execute(
            select(PropertyEventParcel.property_event_id, LandParcel)
            .join(
                LandParcel,
                (LandParcel.id == PropertyEventParcel.parcel_id)
                & (LandParcel.tree_id == PropertyEventParcel.tree_id),
            )
            .where(PropertyEventParcel.tree_id == ctx.tree_id, PropertyEventParcel.property_event_id.in_(ids))
        ).all()
        parcels: dict[uuid.UUID, list[ParcelRef]] = defaultdict(list)
        for eid, parcel in sorted(parcel_rows, key=lambda r: parcel_sort_key(r[1])):
            parcels[eid].append(parcel_ref(parcel))
        docs, hidden_docs = self.documents_for([(DocumentLinkTarget.PROPERTY_EVENT, i) for i in ids])
        cites = citation_counts(ctx, CitationTarget.PROPERTY_EVENT, set(ids))
        related: dict[uuid.UUID, RelatedEventOut] = {}
        out: dict[uuid.UUID, PropertyEventOut] = {}
        for e in events:
            rel = None
            if e.related_event_id:
                if e.related_event_id not in related:
                    related[e.related_event_id] = self.related_event_out(e.related_event_id)
                rel = related[e.related_event_id]
            out[e.id] = PropertyEventOut(
                id=e.id,
                property_id=e.property_id,
                type=e.type,
                date=e.date,
                date_display=date_display(e.date),
                date_sort_from=e.date_sort_from,
                description=e.description,
                registration_number=e.registration_number,
                registration_date=e.registration_date,
                mutation_number=e.mutation_number,
                consideration=e.consideration,
                related_event=rel,
                parcels=parcels.get(e.id, []),
                interests_ended=ended.get(e.id, []),
                interests_created=created.get(e.id, []),
                documents=docs.get(e.id, []),
                hidden_document_count=hidden_docs.get(e.id, 0),
                citation_count=cites.get(e.id, 0),
                evidence_status=e.evidence_status,
                confidence=e.confidence,
                provenance=ProvenanceOut.of(e),
                created_at=e.created_at,
            )
        return out

    def events_of(self, prop: Property) -> list[PropertyEvent]:
        return list(
            self.ctx.db.scalars(
                select(PropertyEvent)
                .where(PropertyEvent.tree_id == self.ctx.tree_id, PropertyEvent.property_id == prop.id)
                .order_by(
                    PropertyEvent.date_sort_from.asc().nulls_last(),
                    PropertyEvent.created_at,
                    PropertyEvent.id,
                )
            )
        )

    def event_out(self, prop: Property, ev: PropertyEvent) -> PropertyEventOut:
        return self.events_out(prop, [ev])[ev.id]

    # ------------------------------------------------------------ composite views
    def detail(self, prop: Property) -> PropertyDetailOut:
        ctx = self.ctx
        parcels = self.parcels_of(prop)
        interests = service.property_interests(ctx, prop.id)
        current = [i for i in interests if service.is_current(i)]
        events = self.events_of(prop)
        targets = [(DocumentLinkTarget.PROPERTY, prop.id)]
        targets += [(DocumentLinkTarget.LAND_PARCEL, p.id) for p in parcels]
        targets += [(DocumentLinkTarget.PROPERTY_EVENT, e.id) for e in events]
        docs, _hidden = self.documents_for(targets)
        n_docs = len({d.id for lst in docs.values() for d in lst})
        n_cites = int(
            ctx.db.scalar(
                select(func.count())
                .select_from(Citation)
                .where(
                    Citation.tree_id == ctx.tree_id,
                    Citation.target_id.in_(
                        [
                            prop.id,
                            *(p.id for p in parcels),
                            *(e.id for e in events),
                            *(i.id for i in interests),
                        ]
                    ),
                )
            )
            or 0
        )
        base = self.property_out(prop, len(parcels))
        documented = sum(
            (
                share_of(i)
                for i in current
                if i.parcel_id is None
                and i.interest_type in OWNERSHIP_INTERESTS
                and i.status == InterestStatus.DOCUMENTED
            ),
            Fraction(0),
        )
        return PropertyDetailOut(
            **base.model_dump(),
            parcels=self.parcels_out(parcels),
            current_interests=self.interests_out(current),
            documented_share_total=fraction_str(documented),
            has_overlapping_claims=has_overlapping_claims(current),
            counts=PropertyCounts(
                parcels=len(parcels),
                events=len(events),
                interests=len(interests),
                current_interests=len(current),
                documents=n_docs,
                citations=n_cites,
            ),
        )

    def holders_at(self, interests: list[PropertyInterest], at: dt.date) -> HoldersAtOut:
        active = [
            i
            for i in interests
            if active_at(i, at) and not (i.status in service.ENDED_STATUSES and i.valid_to_sort is None)
        ]
        return HoldersAtOut(
            at=at,
            interests=self.interests_out(active),
            documented_share_total=fraction_str(_recorded_total(active)),
            has_overlapping_claims=has_overlapping_claims(
                [i for i in active if i.status != InterestStatus.UNKNOWN]
            ),
        )

    def timeline(self, prop: Property, at: dt.date | None = None) -> TimelineOut:
        interests = service.property_interests(self.ctx, prop.id)
        events = self.events_of(prop)
        outs = self.events_out(prop, events, interests)
        parcels = self.parcels_of(prop)
        targets = [(DocumentLinkTarget.PROPERTY, prop.id)]
        targets += [(DocumentLinkTarget.LAND_PARCEL, p.id) for p in parcels]
        docs, hidden = self.documents_for(targets)
        return TimelineOut(
            property=self.property_out(prop, len(parcels)),
            events=[outs[e.id] for e in events],
            current_interests=self.interests_out([i for i in interests if service.is_current(i)]),
            holders_at=self.holders_at(interests, at) if at else None,
            documents=[d for lst in docs.values() for d in lst],
            hidden_document_count=sum(hidden.values()),
        )

    def lineage(self, prop: Property) -> LineageOut:
        """Walk each current interest back through the events that created it (PRS §37)."""
        interests = service.property_interests(self.ctx, prop.id)
        events = self.events_of(prop)
        ev_by_id = {e.id: e for e in events}
        outs = self.events_out(prop, events, interests)
        io = {o.id: o for o in self.interests_out(interests)}
        ended_by: dict[uuid.UUID, list[PropertyInterest]] = defaultdict(list)
        for i in interests:
            if i.ended_by_event_id:
                ended_by[i.ended_by_event_id].append(i)

        def walk(start: PropertyInterest) -> tuple[list[PropertyEvent], list[PropertyInterest]]:
            steps: list[PropertyEvent] = []
            origins: list[PropertyInterest] = []
            seen_events: set[uuid.UUID] = set()
            seen_interests: set[uuid.UUID] = set()
            frontier = [start]
            while frontier:
                cur = frontier.pop()
                if cur.id in seen_interests:
                    continue
                seen_interests.add(cur.id)
                eid = cur.created_by_event_id
                if eid is None or eid not in ev_by_id:
                    origins.append(cur)
                    continue
                preds = ended_by.get(eid, [])
                if eid not in seen_events:
                    seen_events.add(eid)
                    steps.append(ev_by_id[eid])
                if not preds:
                    origins.append(cur)  # e.g. a purchase/acquisition with no earlier recorded holder
                frontier.extend(preds)
            steps.sort(key=lambda e: (e.date_sort_from or dt.date.max, e.created_at), reverse=True)
            origins.sort(key=lambda i: (i.valid_from_sort or dt.date.min, i.created_at))
            return steps, origins

        def holders(items: Iterable[PropertyInterest]) -> list[Any]:
            seen: set[tuple[Any, ...]] = set()
            out = []
            for i in items:
                h = io[i.id].holder
                key = (h.type, h.person_id, h.branch_id, h.name, h.hidden)
                if key not in seen:
                    seen.add(key)
                    out.append(h)
            return out

        current = [i for i in interests if service.is_current(i)]
        chains = []
        all_origins: dict[uuid.UUID, PropertyInterest] = {}
        for c in current:
            steps, origins = walk(c)
            for o in origins:
                all_origins[o.id] = o
            chains.append(
                LineageChain(
                    interest=io[c.id],
                    steps=[outs[e.id] for e in steps],
                    origin_interests=[io[o.id] for o in origins],
                    first_acquirers=holders(o for o in origins if o.interest_type in OWNERSHIP_INTERESTS),
                )
            )
        if not current:
            for i in interests:
                eid = i.created_by_event_id
                if eid is None or not ended_by.get(eid):
                    all_origins[i.id] = i
        origin_list = sorted(
            (o for o in all_origins.values() if o.interest_type in OWNERSHIP_INTERESTS),
            key=lambda i: (i.valid_from_sort or dt.date.min, i.created_at),
        )
        first_events = []
        seen_first: set[uuid.UUID] = set()
        for o in origin_list:
            if (
                o.created_by_event_id
                and o.created_by_event_id in outs
                and o.created_by_event_id not in seen_first
            ):
                seen_first.add(o.created_by_event_id)
                first_events.append(outs[o.created_by_event_id])
        transfers = []
        for e in events:
            ended = ended_by.get(e.id, [])
            if e.type in _TRANSFER_OUT_TYPES or any(i.status == InterestStatus.RELINQUISHED for i in ended):
                eo = outs[e.id]
                transfers.append(
                    TransferOut(
                        event=eo,
                        from_holders=holders(ended),
                        to_holders=[o.holder for o in eo.interests_created],
                    )
                )
        parcels = self.parcels_of(prop)
        by_id = {p.id: p for p in parcels}
        groups: dict[uuid.UUID, list[ParcelRef]] = defaultdict(list)
        for p in parcels:
            if p.parent_parcel_id and p.parent_parcel_id in by_id:
                groups[p.parent_parcel_id].append(parcel_ref(p))
        return LineageOut(
            property=self.property_out(prop, len(parcels)),
            chains=chains,
            first_acquirers=holders(origin_list),
            first_acquisition_events=first_events,
            partitions=[outs[e.id] for e in events if e.type == PropertyEventType.PARTITION],
            transfers_out=transfers,
            parcel_groups=[
                ParcelGroupOut(parent=parcel_ref(by_id[pid]), children=kids) for pid, kids in groups.items()
            ],
        )
