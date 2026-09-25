"""Birth-detail conflict review (PRS §11.2, §58 Kundli AC: "retain both and alert").

Every birth claim for a person — each birth event (certificate, family record, …) and each
astrology profile's chart birth date/time/place — is listed with its provenance, evidence status
and sources. Disagreements are reported; nothing is merged or overwritten.

Comparison only uses what the viewer may see: fields redacted for the viewer (full birth date,
birth time, birth-place detail) are compared at the redacted precision or not at all, so a
conflict never reveals a hidden value.
"""

from __future__ import annotations

import datetime as dt
import uuid
from itertools import combinations
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import FieldGroup, can_view_field
from app.core.dates import GenealogicalDate, TimePrecision
from app.core.textnorm import search_key
from app.models import Citation, Source
from app.models.enums import CitationTarget, EventType, ParticipantRole
from app.modules.astrology.schemas import (
    BirthClaim,
    BirthConflict,
    BirthConflictsOut,
    ClaimSource,
    ConflictValue,
)
from app.modules.astrology.service import visible_profiles
from app.modules.evidence.service import can_view_source
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import ProvenanceOut
from app.modules.genealogy.serialize import Serializer

PRECISE_TIMES = {TimePrecision.EXACT.value, TimePrecision.DOCUMENT_RECORDED.value}
PRECISE_TOLERANCE_MIN = 15
LOOSE_TOLERANCE_MIN = 60


def _sources(
    ctx: TreeContext, target: CitationTarget, ids: set[uuid.UUID]
) -> dict[uuid.UUID, list[ClaimSource]]:
    out: dict[uuid.UUID, list[ClaimSource]] = {}
    if not ids:
        return out
    rows = ctx.db.execute(
        select(Citation.target_id, Source)
        .join(Source, (Source.id == Citation.source_id) & (Source.tree_id == Citation.tree_id))
        .where(Citation.tree_id == ctx.tree_id, Citation.target_type == target, Citation.target_id.in_(ids))
    ).all()
    for tid, s in rows:
        if can_view_source(ctx, s):
            lst = out.setdefault(tid, [])
            if all(x.source_id != s.id for x in lst):
                lst.append(
                    ClaimSource(
                        source_id=s.id,
                        title=s.title,
                        source_type=s.source_type.value,
                        document_id=s.document_id,
                    )
                )
    return out


def _time_minutes(t: dict[str, Any] | None) -> int | None:
    if not t or not t.get("value"):
        return None
    try:
        v = dt.time.fromisoformat(str(t["value"]))
    except ValueError:
        return None
    return v.hour * 60 + v.minute


def _time_display(t: dict[str, Any] | None) -> str | None:
    if not t or not t.get("value"):
        return None
    base = str(t["value"])[:5]
    precision = t.get("precision")
    return base if precision == TimePrecision.EXACT.value else f"{base} ({precision})"


def _dates_compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    lo1, hi1 = GenealogicalDate.model_validate(a).sort_range()
    lo2, hi2 = GenealogicalDate.model_validate(b).sort_range()
    if (lo1 is None and hi1 is None) or (lo2 is None and hi2 is None):
        return True  # unknown dates contradict nothing
    return (hi1 is None or lo2 is None or lo2 <= hi1) and (hi2 is None or lo1 is None or lo1 <= hi2)


def _times_compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ma, mb = _time_minutes(a), _time_minutes(b)
    if ma is None or mb is None:
        return True
    diff = abs(ma - mb)
    diff = min(diff, 24 * 60 - diff)
    precise = a.get("precision") in PRECISE_TIMES and b.get("precision") in PRECISE_TIMES
    return diff <= (PRECISE_TOLERANCE_MIN if precise else LOOSE_TOLERANCE_MIN)


def _places_compatible(a: str, b: str) -> bool:
    ka, kb = search_key(a), search_key(b)
    if not ka or not kb:
        return True
    return ka == kb or ka in kb or kb in ka


def _conflict(
    field: str, claims: list[BirthClaim], getter: Any, compatible: Any, show: Any
) -> BirthConflict | None:
    having = [c for c in claims if getter(c)]
    if len(having) < 2:
        return None
    if all(compatible(getter(x), getter(y)) for x, y in combinations(having, 2)):
        return None
    return BirthConflict(
        field=field,
        message=f"{len(having)} birth claims disagree on the {field} of birth; review the sources "
        "and choose a preferred claim (all claims are kept)",
        values=[ConflictValue(claim_type=c.claim_type, claim_id=c.id, value=show(c)) for c in having],
    )


def birth_conflicts(ctx: TreeContext, person_id: uuid.UUID) -> BirthConflictsOut:
    subject = lookup.get_person_subject(ctx, person_id)
    withheld: set[str] = set()

    events = [
        e
        for e in Serializer(ctx)
        .events_for([subject.id], {subject.id: subject}, {EventType.BIRTH})
        .get(subject.id, [])
        if any(p.person_id == subject.id and p.role == ParticipantRole.PRINCIPAL for p in e.participants)
    ]
    event_sources = _sources(ctx, CitationTarget.EVENT, {e.id for e in events})
    claims: list[BirthClaim] = []
    for e in events:
        withheld |= set(e.redacted_fields)
        claims.append(
            BirthClaim(
                claim_type="event",
                id=e.id,
                is_preferred=e.is_preferred,
                date=e.date,
                date_display=e.date_display,
                time=e.time,
                time_display=_time_display(e.time),
                place=e.place_name or e.place_as_recorded,
                evidence_status=e.evidence_status,
                confidence=e.confidence,
                provenance=e.provenance or ProvenanceOut(origin="manual"),  # type: ignore[arg-type]
                sources=event_sources.get(e.id, []),
            )
        )

    if not can_view_field(ctx, subject, FieldGroup.ASTROLOGY):
        withheld.add(FieldGroup.ASTROLOGY)
    profiles = visible_profiles(ctx, subject)
    full_date = can_view_field(ctx, subject, FieldGroup.BIRTH_DATE_FULL)
    see_time = can_view_field(ctx, subject, FieldGroup.BIRTH_TIME)
    see_place = can_view_field(ctx, subject, FieldGroup.BIRTH_PLACE_DETAIL)
    prof_sources = _sources(ctx, CitationTarget.ASTROLOGY_PROFILE, {p.id for p in profiles})
    for p in profiles:
        date = p.chart_birth_date
        if date and not full_date:
            date = (
                GenealogicalDate.model_validate(date).year_only().model_dump(mode="json", exclude_none=True)
            )
            withheld.add(FieldGroup.BIRTH_DATE_FULL)
        time = p.chart_birth_time if see_time else None
        if p.chart_birth_time and not see_time:
            withheld.add(FieldGroup.BIRTH_TIME)
        place = p.chart_birth_place if see_place else None
        if p.chart_birth_place and not see_place:
            withheld.add(FieldGroup.BIRTH_PLACE_DETAIL)
        claims.append(
            BirthClaim(
                claim_type="astrology_profile",
                id=p.id,
                is_preferred=p.is_preferred,
                date=date,
                date_display=GenealogicalDate.model_validate(date).display() if date else None,
                time=time,
                time_display=_time_display(time),
                place=place,
                evidence_status=p.evidence_status,
                confidence=p.confidence,
                provenance=ProvenanceOut.of(p),
                provenance_kind=p.provenance_kind,
                sources=prof_sources.get(p.id, []),
            )
        )

    conflicts = [
        c
        for c in (
            _conflict("date", claims, lambda c: c.date, _dates_compatible, lambda c: c.date_display or ""),
            _conflict(
                "time",
                claims,
                lambda c: c.time if _time_minutes(c.time) is not None else None,
                _times_compatible,
                lambda c: c.time_display or "",
            ),
            _conflict("place", claims, lambda c: c.place, _places_compatible, lambda c: c.place or ""),
        )
        if c is not None
    ]
    return BirthConflictsOut(
        person_id=subject.id,
        claims=claims,
        conflicts=conflicts,
        has_conflicts=bool(conflicts),
        withheld_fields=sorted(withheld),
    )
