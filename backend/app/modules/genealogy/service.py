"""Genealogy mutations: persons, names, events, places, relationships (ADR-0003)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import Subject
from app.core import audit
from app.core.dates import GenealogicalDate, date_to_json
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.textnorm import detect_script, phonetic_key, search_key
from app.models import (
    BranchMembership,
    Event,
    EventParticipant,
    FamilyBranch,
    NameRecord,
    Person,
    Place,
    ProfileClaimInvite,
    Relationship,
)
from app.models.enums import (
    CATEGORY_EVENT_TYPE,
    DEFAULT_LINEAGE,
    PARENT_TYPES,
    SYMMETRIC_TYPES,
    EventType,
    EvidenceStatus,
    GeoLevel,
    LifeEventCategory,
    LocationPrecision,
    ParticipantRole,
    PrivacyLevel,
    ProfileStatus,
    ProvenanceOrigin,
    RelationshipType,
)
from app.modules.genealogy import lookup
from app.modules.genealogy import provisional as provisional_people
from app.modules.genealogy.schemas import (
    EventIn,
    EventUpdate,
    NameIn,
    NameUpdate,
    PersonCreate,
    PersonUpdate,
    PlaceIn,
    PlaceUpdate,
    PrivacyUpdate,
    RelationshipIn,
    RelationshipUpdate,
    RelativeIn,
    VitalIn,
)
from app.modules.genealogy.serialize import name_display
from app.modules.geo import service as geo_service
from app.modules.review import policy as review_policy


# ---------------------------------------------------------------- places
def _place_search(p: Place) -> str:
    names = (
        [p.canonical_name]
        + [n.get("name", "") for n in (p.local_names or [])]
        + [n.get("name", "") for n in (p.historical_names or [])]
    )
    return search_key(*names)


def _check_place(ctx: TreeContext, place_id: uuid.UUID | None) -> None:
    if place_id is not None:
        lookup.get_place(ctx, place_id)


def create_place(ctx: TreeContext, body: PlaceIn) -> Place:
    if not (
        ctx.has(Permission.PERSON_WRITE)
        or ctx.has(Permission.PROPERTY_WRITE)
        or ctx.has(Permission.SOURCE_WRITE)
    ):
        raise Forbidden()
    _check_place(ctx, body.parent_place_id)
    data = body.model_dump(mode="json")
    if data.get("location_precision") is None:
        # coordinates without a stated precision are treated as approximate, never as exact
        data["location_precision"] = (
            LocationPrecision.APPROXIMATE.value
            if body.latitude is not None
            else LocationPrecision.UNKNOWN.value
        )
    data["lgd_snapshot_id"] = (
        geo_service.link_snapshot(ctx.db, body.lgd_level, body.lgd_code) if body.lgd_level else None
    )
    place = Place(tree_id=ctx.tree_id, created_by=ctx.user_id, **data)
    place.parent_place_id = body.parent_place_id
    place.search_text = _place_search(place)
    ctx.db.add(place)
    ctx.db.flush()
    audit.log(ctx, "place.created", target_type="place", target_id=place.id)
    return place


def _apply_lgd_link(ctx: TreeContext, place: Place, changes: dict[str, Any]) -> None:
    """ADR-0019 §4: a code picked from the cascade is checked and stamped with the active snapshot.

    Re-sending the same pick keeps the snapshot it was linked under (so a later LGD change keeps
    its note); ``lgd_accept_current`` re-links on purpose. A code typed without ``lgd_level`` is
    free text and unlinks.
    """
    accept = bool(changes.pop("lgd_accept_current", False))
    if "lgd_code" not in changes and "lgd_level" not in changes and not accept:
        return
    code = changes.get("lgd_code", place.lgd_code)
    level = changes.get("lgd_level", place.lgd_level if "lgd_code" not in changes else None)
    if not level:
        changes["lgd_level"] = None
        changes["lgd_snapshot_id"] = None
        return
    level = GeoLevel(level)
    same = level == place.lgd_level and code == place.lgd_code and place.lgd_snapshot_id
    if same and not accept:
        return
    changes["lgd_level"] = level
    changes["lgd_snapshot_id"] = geo_service.link_snapshot(ctx.db, level, code)


def update_place(ctx: TreeContext, place_id: uuid.UUID, body: PlaceUpdate) -> Place:
    # SEC-8: canonical place records are edited by genealogy/property writers only (not researchers)
    if not (ctx.has(Permission.PERSON_WRITE) or ctx.has(Permission.PROPERTY_WRITE)):
        raise Forbidden()
    place = lookup.get_place(ctx, place_id)
    changes = body.model_dump(mode="json", exclude_unset=True)
    for nn in ("location_precision", "geo_confidence"):
        if nn in changes and changes[nn] is None:
            del changes[nn]  # not nullable
    if ("latitude" in changes) != ("longitude" in changes) or (
        "latitude" in changes and (changes["latitude"] is None) != (changes["longitude"] is None)
    ):
        raise Unprocessable("latitude and longitude must be changed together")
    if "coordinate_privacy" in changes and not ctx.has(Permission.PRIVACY_MANAGE):
        raise Forbidden("Only tree admins can change who sees exact coordinates")
        pid = body.parent_place_id
        if pid == place.id:
            raise Unprocessable("A place cannot be its own parent")
        _check_place(ctx, pid)
        # prevent hierarchy cycles
        cur = pid
        seen = 0
        while cur is not None and seen < 50:
            if cur == place.id:
                raise Unprocessable("Place hierarchy would contain a cycle")
            cur = ctx.db.scalar(
                select(Place.parent_place_id).where(Place.tree_id == ctx.tree_id, Place.id == cur)
            )
            seen += 1
        changes["parent_place_id"] = pid
    _apply_lgd_link(ctx, place, changes)
    # never overwrite a historical name: canonical renames are appended to history automatically
    if "canonical_name" in changes and changes["canonical_name"] != place.canonical_name:
        hist = list(changes.get("historical_names", place.historical_names) or [])
        if not any(h.get("name") == place.canonical_name for h in hist):
            hist.append({"name": place.canonical_name, "note": "previous canonical name"})
        changes["historical_names"] = hist
    for k, v in changes.items():
        setattr(place, k, v)
    place.updated_by = ctx.user_id
    place.search_text = _place_search(place)
    audit.log(
        ctx, "place.changed", target_type="place", target_id=place.id, details={"fields": sorted(changes)}
    )
    return place


def place_hierarchy(ctx: TreeContext, place: Place) -> list[str]:
    chain: list[str] = []
    cur = place.parent_place_id
    guard = 0
    while cur is not None and guard < 20:
        row = ctx.db.execute(
            select(Place.canonical_name, Place.parent_place_id).where(
                Place.tree_id == ctx.tree_id, Place.id == cur
            )
        ).first()
        if row is None:
            break
        chain.append(row[0])
        cur = row[1]
        guard += 1
    return chain


def find_or_create_place_by_name(ctx: TreeContext, name: str) -> Place:
    key = search_key(name)
    existing = ctx.db.scalar(select(Place).where(Place.tree_id == ctx.tree_id, Place.search_text == key))
    if existing:
        return existing
    return create_place(ctx, PlaceIn(canonical_name=name.strip()))


# ---------------------------------------------------------------- names
def _apply_name_keys(n: NameRecord) -> None:
    parts = [
        n.given_name,
        n.middle_names,
        n.surname,
        n.full_name_as_recorded,
        n.romanized_value,
        n.patronymic,
        n.matronymic,
        n.family_house_name,
    ]
    n.search_text = search_key(*parts)
    n.search_phonetic = " ".join(sorted(set(phonetic_key(" ".join(p for p in parts if p)).split())))
    if not n.script:
        n.script = detect_script(" ".join(p for p in parts if p))


def _new_name(ctx: TreeContext, person_id: uuid.UUID, body: NameIn) -> NameRecord:
    data = body.model_dump(mode="json", exclude={"date_range", "suggestion"})
    n = NameRecord(tree_id=ctx.tree_id, person_id=person_id, created_by=ctx.user_id, **data)
    n.date_range = {k: date_to_json(v) for k, v in (body.date_range or {}).items()} or None
    if body.suggestion is not None:
        # accepted from a transliteration suggestion (ADR-0025 §5): calculated, then confirmed by
        # this user. The engine id is the server's, never the client's.
        from app.modules.translit import engine as translit

        n.prov_origin = ProvenanceOrigin.CALCULATION
        n.prov_algorithm = f"{translit.ENGINE} {translit.VERSION} ({body.suggestion.method})"[:120]
        n.prov_confirmed_by = ctx.user_id
        n.prov_confirmed_at = dt.datetime.now(dt.UTC)
    _apply_name_keys(n)
    return n


def _set_preferred_name(ctx: TreeContext, person: Person, name: NameRecord) -> None:
    for other in ctx.db.scalars(
        select(NameRecord).where(
            NameRecord.tree_id == ctx.tree_id,
            NameRecord.person_id == person.id,
            NameRecord.id != name.id,
            NameRecord.is_preferred.is_(True),
        )
    ):
        other.is_preferred = False
    name.is_preferred = True
    person.preferred_display_name = name_display(name)[:300] or person.preferred_display_name


def add_name(ctx: TreeContext, person_id: uuid.UUID, body: NameIn) -> NameRecord:
    person = lookup.get_person(ctx, person_id)
    ctx.require(Permission.PERSON_WRITE, person_id=person.id)
    n = _new_name(ctx, person.id, body)
    ctx.db.add(n)
    ctx.db.flush()
    has_preferred = ctx.db.scalar(
        select(NameRecord.id).where(
            NameRecord.tree_id == ctx.tree_id,
            NameRecord.person_id == person.id,
            NameRecord.id != n.id,
            NameRecord.is_preferred.is_(True),
        )
    )
    if body.is_preferred or has_preferred is None:
        _set_preferred_name(ctx, person, n)
    # A name completes the profile's details but verifies nothing: ``is_provisional`` records how the
    # person was created and stays set (ADR-0020 §4).
    provisional_people.forget(ctx)
    audit.log(ctx, "person.name_added", target_type="person", target_id=person.id)
    return n


def update_name(ctx: TreeContext, person_id: uuid.UUID, name_id: uuid.UUID, body: NameUpdate) -> NameRecord:
    person = lookup.get_person(ctx, person_id)
    ctx.require(Permission.PERSON_WRITE, person_id=person.id)
    n = lookup.get_name(ctx, name_id)
    if n.person_id != person.id:
        raise NotFound("Name not found")
    review_policy.require_direct(ctx, "all", [person.id], [n])
    changes = body.model_dump(mode="json", exclude_unset=True)
    preferred = changes.pop("is_preferred", None)
    for k, v in changes.items():
        setattr(n, k, v)
    n.updated_by = ctx.user_id
    _apply_name_keys(n)
    if preferred:
        _set_preferred_name(ctx, person, n)
    elif n.is_preferred:
        person.preferred_display_name = name_display(n)[:300] or person.preferred_display_name
    audit.log(ctx, "person.name_changed", target_type="person", target_id=person.id)
    return n


def delete_name(ctx: TreeContext, person_id: uuid.UUID, name_id: uuid.UUID) -> None:
    person = lookup.get_person(ctx, person_id)
    ctx.require(Permission.PERSON_WRITE, person_id=person.id)
    n = lookup.get_name(ctx, name_id)
    if n.person_id != person.id:
        raise NotFound("Name not found")
    review_policy.require_direct(ctx, "all", [person.id], [n])
    remaining = ctx.db.scalar(
        select(func.count())
        .select_from(NameRecord)
        .where(NameRecord.tree_id == ctx.tree_id, NameRecord.person_id == person.id)
    )
    if (remaining or 0) <= 1:
        raise Conflict("A person must keep at least one name", code="last_name")
    was_preferred = n.is_preferred
    ctx.db.delete(n)
    ctx.db.flush()
    if was_preferred:
        nxt = ctx.db.scalar(
            select(NameRecord)
            .where(NameRecord.tree_id == ctx.tree_id, NameRecord.person_id == person.id)
            .order_by(NameRecord.created_at)
        )
        if nxt:
            _set_preferred_name(ctx, person, nxt)
    audit.log(ctx, "person.name_removed", target_type="person", target_id=person.id)


# ---------------------------------------------------------------- events
def _event_sort(e: Event, d: GenealogicalDate | None) -> None:
    lo, hi = d.sort_range() if d else (None, None)
    e.date_sort_from, e.date_sort_to = lo, hi


def _apply_event_core(ctx: TreeContext, e: Event, body: Any, fields: set[str]) -> None:
    for f in fields:
        v = getattr(body, f)
        if f == "date":
            e.date = date_to_json(v)
            _event_sort(e, v)
        elif f == "time":
            e.time = v.model_dump(mode="json", exclude_none=True) if v is not None else None
        elif f in ("place_id", "origin_place_id"):
            _check_place(ctx, v)
            setattr(e, f, v)
        else:
            setattr(e, f, v)


_CORE_FIELDS = {
    "date",
    "time",
    "timezone_id",
    "utc_offset_minutes",
    "place_id",
    "place_as_recorded",
    "latitude",
    "longitude",
    "location_precision",
    "description",
    "evidence_status",
    "confidence",
}


def _has_preferred(
    ctx: TreeContext, person_id: uuid.UUID, etype: EventType, exclude: uuid.UUID | None = None
) -> bool:
    q = (
        select(Event.id)
        .join(
            EventParticipant,
            (EventParticipant.event_id == Event.id) & (EventParticipant.tree_id == Event.tree_id),
        )
        .where(
            Event.tree_id == ctx.tree_id,
            Event.type == etype,
            Event.is_preferred.is_(True),
            EventParticipant.person_id == person_id,
            EventParticipant.role == ParticipantRole.PRINCIPAL,
        )
    )
    if exclude:
        q = q.where(Event.id != exclude)
    return ctx.db.scalar(q.limit(1)) is not None


def _unset_other_preferred(ctx: TreeContext, person_id: uuid.UUID, etype: EventType, keep: uuid.UUID) -> None:
    ids = ctx.db.scalars(
        select(Event.id)
        .join(
            EventParticipant,
            (EventParticipant.event_id == Event.id) & (EventParticipant.tree_id == Event.tree_id),
        )
        .where(
            Event.tree_id == ctx.tree_id,
            Event.type == etype,
            Event.id != keep,
            EventParticipant.person_id == person_id,
            EventParticipant.role == ParticipantRole.PRINCIPAL,
        )
    ).all()
    for ev in ctx.db.scalars(select(Event).where(Event.tree_id == ctx.tree_id, Event.id.in_(ids))):
        ev.is_preferred = False


SINGLE_PREFERRED = {EventType.BIRTH, EventType.DEATH}


def create_vital(
    ctx: TreeContext, person: Person, etype: EventType, body: VitalIn, **provenance: Any
) -> Event:
    e = Event(tree_id=ctx.tree_id, type=etype, created_by=ctx.user_id, **provenance)
    _apply_event_core(ctx, e, body, _CORE_FIELDS)
    e.is_preferred = not _has_preferred(ctx, person.id, etype)
    ctx.db.add(e)
    ctx.db.flush()
    ctx.db.add(
        EventParticipant(
            tree_id=ctx.tree_id,
            event_id=e.id,
            person_id=person.id,
            role=ParticipantRole.PRINCIPAL,
            created_by=ctx.user_id,
        )
    )
    ctx.db.flush()
    return e


def create_event(ctx: TreeContext, body: EventIn, **provenance: Any) -> Event:
    etype = body.type or CATEGORY_EVENT_TYPE[body.category or LifeEventCategory.CUSTOM]
    principals = [p for p in body.participants if p.role == ParticipantRole.PRINCIPAL]
    if not principals:
        raise Unprocessable("An event needs at least one principal participant")
    for p in body.participants:
        lookup.get_person(ctx, p.person_id)
        ctx.require(Permission.PERSON_WRITE, person_id=p.person_id)
    if etype in SINGLE_PREFERRED and len(principals) != 1:
        raise Unprocessable(f"A {etype.value} event has exactly one principal")
    e = Event(
        tree_id=ctx.tree_id,
        type=etype,
        subtype=body.subtype,
        title=body.title,
        category=body.category,
        significance=body.significance,
        created_by=ctx.user_id,
        origin_place_as_recorded=body.origin_place_as_recorded,
        reason=body.reason,
        privacy_level=body.privacy_level,
        **provenance,
    )
    _apply_event_core(ctx, e, body, _CORE_FIELDS | {"origin_place_id"})
    e.is_preferred = body.is_preferred
    if etype in SINGLE_PREFERRED:
        pid = principals[0].person_id
        if "is_preferred" not in body.model_fields_set and _has_preferred(ctx, pid, etype):
            e.is_preferred = False  # competing claim: kept, not preferred (ADR-0003)
    ctx.db.add(e)
    ctx.db.flush()
    seen = set()
    for p in body.participants:
        key = (p.person_id, p.role)
        if key in seen:
            continue
        seen.add(key)
        ctx.db.add(
            EventParticipant(
                tree_id=ctx.tree_id,
                event_id=e.id,
                person_id=p.person_id,
                role=p.role,
                role_detail=p.role_detail,
                created_by=ctx.user_id,
            )
        )
    ctx.db.flush()
    if etype in SINGLE_PREFERRED and e.is_preferred:
        _unset_other_preferred(ctx, principals[0].person_id, etype, e.id)
    audit.log(ctx, "event.created", target_type="event", target_id=e.id, details={"type": etype.value})
    return e


def _event_principal(ctx: TreeContext, e: Event) -> uuid.UUID | None:
    return ctx.db.scalar(
        select(EventParticipant.person_id)
        .where(
            EventParticipant.tree_id == ctx.tree_id,
            EventParticipant.event_id == e.id,
            EventParticipant.role == ParticipantRole.PRINCIPAL,
        )
        .limit(1)
    )


def get_event_checked(ctx: TreeContext, event_id: uuid.UUID) -> tuple[Event, uuid.UUID | None]:
    e = lookup.get_event(ctx, event_id)
    principal = _event_principal(ctx, e)
    subject = None
    if principal is not None:
        subject = lookup.get_person_subject(ctx, principal)  # 404 if the principal is not visible
    if e.privacy_level is not None:
        from app.authz.privacy import level_allows

        if not level_allows(ctx, e.privacy_level, subject=subject):
            raise NotFound("Event not found")  # the event's own visibility (ADR-0015)
    return e, principal


def update_event(ctx: TreeContext, event_id: uuid.UUID, body: EventUpdate) -> Event:
    e, principal = get_event_checked(ctx, event_id)
    ctx.require(Permission.PERSON_WRITE, person_id=principal)
    review_policy.require_direct(ctx, "all", [principal], [e])
    fields = set(body.model_fields_set)
    core = fields & (_CORE_FIELDS | {"origin_place_id"})
    _apply_event_core(ctx, e, body, core)
    for f in fields - core - {"is_preferred"}:
        value = getattr(body, f)
        if value is None and f == "significance":
            continue  # not nullable
        setattr(e, f, value)
    if body.is_preferred is not None:
        e.is_preferred = body.is_preferred
        if body.is_preferred and principal and e.type in SINGLE_PREFERRED:
            _unset_other_preferred(ctx, principal, e.type, e.id)
    e.updated_by = ctx.user_id
    audit.log(ctx, "event.changed", target_type="event", target_id=e.id, details={"fields": sorted(fields)})
    if "privacy_level" in fields:
        from app.modules.sharing.core import enforce_event_ceiling

        ctx.db.flush()
        enforce_event_ceiling(ctx, e.id)  # album photos narrow with their event (ADR-0027 §5.3)
    return e


def delete_event(ctx: TreeContext, event_id: uuid.UUID) -> None:
    e, principal = get_event_checked(ctx, event_id)
    ctx.require(Permission.PERSON_WRITE, person_id=principal)
    review_policy.require_direct(ctx, "all", [principal], [e])
    ctx.db.execute(
        sa_delete(EventParticipant).where(
            EventParticipant.tree_id == ctx.tree_id, EventParticipant.event_id == e.id
        )
    )
    ctx.db.delete(e)
    audit.log(ctx, "event.deleted", target_type="event", target_id=e.id, details={"type": e.type.value})


# ---------------------------------------------------------------- persons
def create_person(ctx: TreeContext, body: PersonCreate, *, provisional: bool = False) -> Person:
    """Create a person. ``provisional`` (Smart Add "unknown for now", ADR-0020 §4): no name, CUSTOM
    privacy (tree admins + a view grant for the creator) and the permanent ``is_provisional`` origin."""
    ctx.require(Permission.PERSON_WRITE)
    from app.modules.consent.attestation import require_attestation

    require_attestation(ctx)  # ADR-0011
    person = Person(
        tree_id=ctx.tree_id,
        profile_status=body.profile_status,
        preferred_display_name=(body.preferred_display_name or "").strip() or "Unnamed",
        sex_at_birth=body.sex_at_birth,
        gender_identity=body.gender_identity,
        primary_language=body.primary_language,
        scripts_used=body.scripts_used,
        privacy_level=PrivacyLevel.CUSTOM
        if provisional
        else (body.privacy_level or ctx.tree.default_person_privacy),
        occupation=body.occupation,
        notes=body.notes,
        contact_info=body.contact_info,
        residential_address=body.residential_address,
        is_provisional=provisional,
        created_by=ctx.user_id,
    )
    ctx.db.add(person)
    ctx.db.flush()
    review_policy.remember_new_person(ctx, person.id)  # links to a new person are additions (§1)
    names = [] if provisional else [_new_name(ctx, person.id, n) for n in body.names]
    for n in names:
        ctx.db.add(n)
    ctx.db.flush()
    if names:
        preferred = next((n for n in names if n.is_preferred), names[0])
        preferred.is_preferred = True
        if not body.preferred_display_name:
            person.preferred_display_name = name_display(preferred)[:300] or "Unnamed"
    if not person.scripts_used:
        person.scripts_used = sorted({n.script for n in names if n.script})
    if body.birth:
        create_vital(ctx, person, EventType.BIRTH, body.birth)
    if body.death:
        create_vital(ctx, person, EventType.DEATH, body.death)
        if person.profile_status == ProfileStatus.UNKNOWN:
            person.profile_status = ProfileStatus.DECEASED
    branch_ids = set(body.branch_ids)
    if ctx.branch_scope is not None:
        branch_ids.add(ctx.branch_scope)
    for bid in branch_ids:
        lookup.get_in_tree(ctx, FamilyBranch, bid, "Branch")
        ctx.db.add(
            BranchMembership(tree_id=ctx.tree_id, branch_id=bid, person_id=person.id, created_by=ctx.user_id)
        )
    ctx.db.flush()
    if ctx.branch_scope is not None and ctx._branch_people is not None:
        ctx._branch_people.add(person.id)
    if provisional:
        provisional_people.share_with_creator(ctx, person)
    audit.log(ctx, "person.created", target_type="person", target_id=person.id)
    return person


def update_person(ctx: TreeContext, person_id: uuid.UUID, body: PersonUpdate) -> Person:
    person = lookup.get_person(ctx, person_id)
    ctx.require(Permission.PERSON_WRITE, person_id=person.id)
    review_policy.require_direct(ctx, "all", [person.id], [person])
    changes = body.model_dump(exclude_unset=True)
    if "profile_status" in changes and changes["profile_status"] != person.profile_status:
        audit.log(
            ctx,
            "person.living_status_changed",
            target_type="person",
            target_id=person.id,
            details={"from": person.profile_status.value, "to": str(changes["profile_status"])},
        )
    sensitive = {"contact_info", "residential_address", "gender_identity"} & set(changes)
    for k, v in changes.items():
        setattr(person, k, v)
    person.updated_by = ctx.user_id
    audit.log(
        ctx,
        "person.changed",
        target_type="person",
        target_id=person.id,
        details={"fields": sorted(changes), "sensitive_fields": sorted(sensitive)},
    )
    return person


def set_privacy(ctx: TreeContext, subject: Subject, body: PrivacyUpdate) -> Person:
    person = subject.person
    is_self = ctx.user is not None and person.claimed_by_user_id == ctx.user.id
    if not (ctx.has(Permission.PRIVACY_MANAGE) or is_self):
        raise Forbidden("Only tree admins or the claimed profile owner can change privacy settings")
    from app.authz.privacy import FieldGroup

    if body.privacy_level is not None:
        person.privacy_level = body.privacy_level
        ctx.db.flush()
        from app.modules.sharing.core import enforce_person_ceiling

        enforce_person_ceiling(ctx, person.id)  # records tagging them narrow at once (ADR-0027 §5)
    if body.field_privacy is not None:
        fp = dict(person.field_privacy or {})
        for group, level in body.field_privacy.items():
            if group not in FieldGroup.ALL:
                raise Unprocessable(
                    f"Unknown field group '{group}'", details={"allowed": list(FieldGroup.ALL)}
                )
            if level is None:
                fp.pop(group, None)
            else:
                fp[group] = level.value
        person.field_privacy = fp
    audit.log(
        ctx,
        "person.privacy_changed",
        target_type="person",
        target_id=person.id,
        details={
            "privacy_level": person.privacy_level.value,
            "field_groups": sorted((body.field_privacy or {}).keys()),
        },
    )
    return person


def delete_person(ctx: TreeContext, person_id: uuid.UUID) -> None:
    person = lookup.get_person(ctx, person_id)
    ctx.require(Permission.PERSON_WRITE, person_id=person.id)
    review_policy.require_direct(ctx, "all", [person.id], [person])
    person.deleted_at = dt.datetime.now(dt.UTC)
    person.updated_by = ctx.user_id
    audit.log(ctx, "person.deleted", target_type="person", target_id=person.id)


def restore_person(ctx: TreeContext, person_id: uuid.UUID) -> Person:
    ctx.require(Permission.TREE_MANAGE)
    person = lookup.get_in_tree(ctx, Person, person_id, "Person")
    person.deleted_at = None
    audit.log(ctx, "person.restored", target_type="person", target_id=person.id)
    return person


# ---------------------------------------------------------------- relationships
def _normalise_pair(t: RelationshipType, a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    if t in SYMMETRIC_TYPES and str(a) > str(b):
        return b, a
    return a, b


def is_ancestor(ctx: TreeContext, ancestor: uuid.UUID, of: uuid.UUID, max_depth: int = 200) -> bool:
    """True if ``ancestor`` is reachable upward (any parent type) from ``of``."""
    sql = text(
        """
        WITH RECURSIVE up(pid, depth) AS (
            SELECT person_a_id, 1 FROM relationship
             WHERE tree_id = :tree AND person_b_id = :start AND type = ANY(:ptypes)
            UNION
            SELECT r.person_a_id, up.depth + 1 FROM relationship r JOIN up ON r.person_b_id = up.pid
             WHERE r.tree_id = :tree AND r.type = ANY(:ptypes) AND up.depth < :maxd
        )
        SELECT 1 FROM up WHERE pid = :target LIMIT 1
        """
    )
    return (
        ctx.db.execute(
            sql,
            {
                "tree": ctx.tree_id,
                "start": of,
                "target": ancestor,
                "ptypes": [t.value for t in PARENT_TYPES],
                "maxd": max_depth,
            },
        ).first()
        is not None
    )


def _require_rel_write(ctx: TreeContext, a: uuid.UUID, b: uuid.UUID) -> None:
    ctx.require(Permission.RELATIONSHIP_WRITE)
    if ctx.branch_scope is not None:
        scope = ctx.branch_people()
        if a not in scope and b not in scope:
            raise Forbidden("At least one person must be inside the family branch you manage")


def _validate_union(ctx: TreeContext, union_id: uuid.UUID, parent_id: uuid.UUID) -> Relationship:
    union = lookup.get_relationship(ctx, union_id)
    from app.models.enums import UNION_TYPES

    if union.type not in UNION_TYPES:
        raise Unprocessable("union_id must reference a spouse/partner relationship")
    if parent_id not in (union.person_a_id, union.person_b_id):
        raise Unprocessable("The parent must be one of the partners in the referenced union")
    return union


def create_relationship(ctx: TreeContext, body: RelationshipIn, **provenance: Any) -> Relationship:
    a, b = body.person_a_id, body.person_b_id
    if a == b:
        raise Unprocessable("A person cannot be related to themselves")
    lookup.get_person(ctx, a)
    lookup.get_person(ctx, b)
    _require_rel_write(ctx, a, b)
    if not (review_policy.is_new_person(ctx, a) or review_policy.is_new_person(ctx, b)):
        # linking two people who were already in the tree is a change, not an addition (§1)
        review_policy.require_direct(ctx, "structure", [a, b], [])
    t = body.type
    if t in PARENT_TYPES:
        if is_ancestor(ctx, b, a) or a == b:
            raise Unprocessable("This would make a person their own ancestor", code="relationship_cycle")
        if body.union_id is not None:
            _validate_union(ctx, body.union_id, a)
        if t == RelationshipType.BIOLOGICAL_PARENT:
            existing = (
                ctx.db.scalar(
                    select(func.count())
                    .select_from(Relationship)
                    .where(
                        Relationship.tree_id == ctx.tree_id,
                        Relationship.person_b_id == b,
                        Relationship.type == RelationshipType.BIOLOGICAL_PARENT,
                        Relationship.evidence_status.notin_(
                            [EvidenceStatus.DISPROVEN, EvidenceStatus.SUPERSEDED, EvidenceStatus.DISPUTED]
                        ),
                    )
                )
                or 0
            )
            if existing >= 2 and body.evidence_status not in (EvidenceStatus.DISPUTED,):
                raise Conflict(
                    "This person already has two biological parents; record the new claim as DISPUTED "
                    "or mark an existing one as disproven/superseded",
                    code="too_many_biological_parents",
                )
    elif body.union_id is not None:
        raise Unprocessable("union_id only applies to parent relationships")
    a, b = _normalise_pair(t, a, b)
    rel = Relationship(
        tree_id=ctx.tree_id,
        person_a_id=a,
        person_b_id=b,
        type=t,
        subtype=body.subtype,
        lineage=body.lineage or DEFAULT_LINEAGE.get(t),
        union_id=body.union_id,
        start_date=date_to_json(body.start_date),
        end_date=date_to_json(body.end_date),
        union_order=body.union_order,
        legal_status=body.legal_status,
        notes=body.notes,
        evidence_status=body.evidence_status,
        confidence=body.confidence,
        created_by=ctx.user_id,
        **provenance,
    )
    ctx.db.add(rel)
    try:
        with ctx.db.begin_nested():
            ctx.db.flush()
    except IntegrityError:
        raise Conflict("This relationship already exists", code="duplicate_relationship")
    provisional_people.forget(ctx)
    audit.log(
        ctx, "relationship.added", target_type="relationship", target_id=rel.id, details={"type": t.value}
    )
    return rel


def update_relationship(ctx: TreeContext, rel_id: uuid.UUID, body: RelationshipUpdate) -> Relationship:
    rel = lookup.get_relationship(ctx, rel_id)
    lookup.get_person(ctx, rel.person_a_id)
    lookup.get_person(ctx, rel.person_b_id)
    _require_rel_write(ctx, rel.person_a_id, rel.person_b_id)
    review_policy.require_direct(ctx, "structure", [rel.person_a_id, rel.person_b_id], [rel])
    fields = body.model_fields_set
    if "type" in fields and body.type is not None and body.type != rel.type:
        old_parent = rel.type in PARENT_TYPES
        new_parent = body.type in PARENT_TYPES
        if old_parent != new_parent:
            raise Unprocessable(
                "Cannot convert between parent and non-parent relationship types; create a new one"
            )
        rel.type = body.type
        if "lineage" not in fields:
            rel.lineage = DEFAULT_LINEAGE.get(body.type)
    if body.clear_union:
        rel.union_id = None
    elif "union_id" in fields and body.union_id is not None:
        if rel.type not in PARENT_TYPES:
            raise Unprocessable("union_id only applies to parent relationships")
        _validate_union(ctx, body.union_id, rel.person_a_id)
        rel.union_id = body.union_id
    for f in fields - {"type", "union_id", "clear_union"}:
        v = getattr(body, f)
        if f in ("start_date", "end_date"):
            v = date_to_json(v)
        setattr(rel, f, v)
    rel.updated_by = ctx.user_id
    provisional_people.forget(ctx)
    audit.log(
        ctx,
        "relationship.changed",
        target_type="relationship",
        target_id=rel.id,
        details={"fields": sorted(fields)},
    )
    return rel


def delete_relationship(ctx: TreeContext, rel_id: uuid.UUID) -> None:
    rel = lookup.get_relationship(ctx, rel_id)
    lookup.get_person(ctx, rel.person_a_id)
    lookup.get_person(ctx, rel.person_b_id)
    _require_rel_write(ctx, rel.person_a_id, rel.person_b_id)
    review_policy.require_direct(ctx, "structure", [rel.person_a_id, rel.person_b_id], [rel])
    # detach children linked to this union rather than deleting their parentage
    for child_edge in ctx.db.scalars(
        select(Relationship).where(Relationship.tree_id == ctx.tree_id, Relationship.union_id == rel.id)
    ):
        child_edge.union_id = None
    ctx.db.delete(rel)
    provisional_people.forget(ctx)
    audit.log(
        ctx,
        "relationship.removed",
        target_type="relationship",
        target_id=rel.id,
        details={"type": rel.type.value},
    )


def add_relative(
    ctx: TreeContext, anchor_id: uuid.UUID, body: RelativeIn
) -> tuple[Person, list[Relationship]]:
    anchor = lookup.get_person(ctx, anchor_id)
    if body.new_person is not None:
        other = create_person(ctx, body.new_person)
    elif body.existing_person_id is not None:
        other = lookup.get_person(ctx, body.existing_person_id)
    else:
        raise Unprocessable("provide exactly one of existing_person_id or new_person")
    rels: list[Relationship] = []
    common = {"start_date": body.start_date, "subtype": body.subtype}
    if body.relation == "parent":
        t = body.relationship_type or RelationshipType.BIOLOGICAL_PARENT
        if t not in PARENT_TYPES:
            raise Unprocessable("relationship_type must be a parent type")
        rels.append(
            create_relationship(
                ctx, RelationshipIn(person_a_id=other.id, person_b_id=anchor.id, type=t, **common)
            )
        )
    elif body.relation == "spouse":
        t = body.relationship_type or RelationshipType.SPOUSE
        from app.models.enums import UNION_TYPES

        if t not in UNION_TYPES:
            raise Unprocessable("relationship_type must be a spouse/partner type")
        existing_unions = (
            ctx.db.scalar(
                select(func.count())
                .select_from(Relationship)
                .where(
                    Relationship.tree_id == ctx.tree_id,
                    Relationship.type.in_(list(UNION_TYPES)),
                    or_(Relationship.person_a_id == anchor.id, Relationship.person_b_id == anchor.id),
                )
            )
            or 0
        )
        rels.append(
            create_relationship(
                ctx,
                RelationshipIn(
                    person_a_id=anchor.id,
                    person_b_id=other.id,
                    type=t,
                    union_order=existing_unions + 1,
                    **common,
                ),
            )
        )
    elif body.relation == "child":
        t = body.relationship_type or RelationshipType.BIOLOGICAL_PARENT
        if t not in PARENT_TYPES:
            raise Unprocessable("relationship_type must be a parent type")
        other_parent = body.other_parent_id
        if body.union_id is not None:
            union = _validate_union(ctx, body.union_id, anchor.id)
            partner = union.person_b_id if union.person_a_id == anchor.id else union.person_a_id
            if other_parent is not None and other_parent != partner:
                raise Unprocessable("other_parent_id does not match the union partner")
            other_parent = partner
        rels.append(
            create_relationship(
                ctx,
                RelationshipIn(person_a_id=anchor.id, person_b_id=other.id, type=t, union_id=body.union_id),
            )
        )
        if other_parent is not None:
            lookup.get_person(ctx, other_parent)
            rels.append(
                create_relationship(
                    ctx,
                    RelationshipIn(
                        person_a_id=other_parent, person_b_id=other.id, type=t, union_id=body.union_id
                    ),
                )
            )
    else:  # sibling
        rels.append(
            create_relationship(
                ctx,
                RelationshipIn(
                    person_a_id=anchor.id, person_b_id=other.id, type=RelationshipType.SIBLING, **common
                ),
            )
        )
    return other, rels


def unions_of(ctx: TreeContext, person_id: uuid.UUID) -> list[Relationship]:
    from app.models.enums import UNION_TYPES

    return list(
        ctx.db.scalars(
            select(Relationship)
            .where(
                Relationship.tree_id == ctx.tree_id,
                Relationship.type.in_(list(UNION_TYPES)),
                or_(Relationship.person_a_id == person_id, Relationship.person_b_id == person_id),
            )
            .order_by(Relationship.union_order.nulls_last(), Relationship.created_at)
        )
    )


def relationships_of(ctx: TreeContext, person_id: uuid.UUID) -> list[Relationship]:
    return list(
        ctx.db.scalars(
            select(Relationship).where(
                Relationship.tree_id == ctx.tree_id,
                or_(Relationship.person_a_id == person_id, Relationship.person_b_id == person_id),
            )
        )
    )


def erase_person(ctx: TreeContext, person_id: uuid.UUID, reason: str) -> Person:
    """Erase, without copying the erased values into revision history, and remove that history.

    The erasure is flushed while the revision hook is off, then every revision row that belongs to
    the person (their own record, names, claims, vitals and relationships) is deleted (ADR-0021 §3).
    """
    from app.models import RecordRevision
    from app.modules.review import revisions

    ev_ids = set(
        ctx.db.scalars(
            select(EventParticipant.event_id).where(
                EventParticipant.tree_id == ctx.tree_id, EventParticipant.person_id == person_id
            )
        )
    )
    record_ids = set(ev_ids)
    record_ids |= set(
        ctx.db.scalars(
            select(NameRecord.id).where(NameRecord.tree_id == ctx.tree_id, NameRecord.person_id == person_id)
        )
    )
    record_ids |= set(
        ctx.db.scalars(
            select(Relationship.id).where(
                Relationship.tree_id == ctx.tree_id,
                or_(Relationship.person_a_id == person_id, Relationship.person_b_id == person_id),
            )
        )
    )
    from app.models import Assertion
    from app.modules.review import service as review_service

    record_ids |= set(
        ctx.db.scalars(
            select(Assertion.id).where(Assertion.tree_id == ctx.tree_id, Assertion.person_id == person_id)
        )
    )
    with revisions.suppressed(ctx.db):
        person = _erase_person(ctx, person_id, reason)
        ctx.db.flush()
    review_service.on_person_erased(ctx, person_id, record_ids)
    conds = [RecordRevision.person_id == person_id, RecordRevision.person_b_id == person_id]
    if ev_ids:
        conds.append(RecordRevision.record_id.in_(ev_ids))
    ctx.db.execute(sa_delete(RecordRevision).where(RecordRevision.tree_id == ctx.tree_id, or_(*conds)))
    return person


def _erase_person(ctx: TreeContext, person_id: uuid.UUID, reason: str) -> Person:
    """Privacy erasure (PRS §54): remove personal data but keep a placeholder so the tree's shape holds.

    Names, events, heritage/astrology claims, notes and contact data are deleted; relationships are
    kept (they describe *other* people's ancestry) but the person is shown as "Erased person".
    Irreversible by design — audited.
    """
    from app.models import Assertion, AstrologyProfile, Citation
    from app.models.enums import CitationTarget

    ctx.require(Permission.TREE_MANAGE)
    person = lookup.get_in_tree(ctx, Person, person_id, "Person")
    db = ctx.db
    ev_ids = list(
        db.scalars(
            select(EventParticipant.event_id).where(
                EventParticipant.tree_id == ctx.tree_id,
                EventParticipant.person_id == person.id,
                EventParticipant.role == ParticipantRole.PRINCIPAL,
            )
        )
    )
    db.execute(
        sa_delete(EventParticipant).where(
            EventParticipant.tree_id == ctx.tree_id, EventParticipant.person_id == person.id
        )
    )
    if ev_ids:
        db.execute(
            sa_delete(Citation).where(
                Citation.tree_id == ctx.tree_id,
                Citation.target_type == CitationTarget.EVENT,
                Citation.target_id.in_(ev_ids),
            )
        )
        db.execute(
            sa_delete(EventParticipant).where(
                EventParticipant.tree_id == ctx.tree_id, EventParticipant.event_id.in_(ev_ids)
            )
        )
        db.execute(sa_delete(Event).where(Event.tree_id == ctx.tree_id, Event.id.in_(ev_ids)))
    for model in (Assertion, AstrologyProfile):
        db.execute(sa_delete(model).where(model.tree_id == ctx.tree_id, model.person_id == person.id))  # type: ignore[attr-defined]
    db.execute(
        sa_delete(Citation).where(
            Citation.tree_id == ctx.tree_id,
            Citation.target_type == CitationTarget.PERSON,
            Citation.target_id == person.id,
        )
    )
    # SEC-11: every other person-referencing store that can hold personal data
    from app.models import (
        DocumentLink,
        ExtractionProposal,
        GedcomExtension,
        Relationship,
        TraditionLink,
        TreeMembership,
    )
    from app.models.enums import DocumentLinkTarget, TraditionLinkTarget

    db.execute(
        sa_delete(GedcomExtension).where(
            GedcomExtension.tree_id == ctx.tree_id, GedcomExtension.person_id == person.id
        )
    )
    db.execute(
        sa_delete(ExtractionProposal).where(
            ExtractionProposal.tree_id == ctx.tree_id, ExtractionProposal.subject_person_id == person.id
        )
    )
    db.execute(
        sa_delete(DocumentLink).where(
            DocumentLink.tree_id == ctx.tree_id,
            DocumentLink.target_type == DocumentLinkTarget.PERSON,
            DocumentLink.target_id == person.id,
        )
    )
    # a tradition keeps its text; only its link to the erased person goes (ADR-0026 §7)
    db.execute(
        sa_delete(TraditionLink).where(
            TraditionLink.tree_id == ctx.tree_id,
            TraditionLink.target_type == TraditionLinkTarget.PERSON,
            TraditionLink.target_id == person.id,
        )
    )
    for rel in db.scalars(
        select(Relationship).where(
            Relationship.tree_id == ctx.tree_id,
            (Relationship.person_a_id == person.id) | (Relationship.person_b_id == person.id),
        )
    ):
        rel.notes = None
        rel.legal_status = None
        rel.start_date = None
        rel.end_date = None
    for m in db.scalars(
        select(TreeMembership).where(
            TreeMembership.tree_id == ctx.tree_id, TreeMembership.linked_person_id == person.id
        )
    ):
        m.linked_person_id = None
    person.claimed_by_user_id = None
    # Outstanding claim invites would still show the erased name to whoever holds the link.
    for inv in db.scalars(
        select(ProfileClaimInvite).where(
            ProfileClaimInvite.tree_id == ctx.tree_id,
            ProfileClaimInvite.person_id == person.id,
            ProfileClaimInvite.revoked_at.is_(None),
        )
    ):
        inv.revoked_at = dt.datetime.now(dt.UTC)
    db.execute(
        sa_delete(NameRecord).where(NameRecord.tree_id == ctx.tree_id, NameRecord.person_id == person.id)
    )
    db.add(
        NameRecord(
            tree_id=ctx.tree_id,
            person_id=person.id,
            full_name_as_recorded="Erased person",
            is_preferred=True,
            search_text="",
            search_phonetic="",
            created_by=ctx.user_id,
        )
    )
    person.preferred_display_name = "Erased person"
    person.sex_at_birth = None
    person.gender_identity = None
    person.notes = None
    person.contact_info = None
    person.residential_address = None
    person.occupation = None
    person.scripts_used = []
    person.privacy_level = PrivacyLevel.PRIVATE_TREE_ADMINS
    person.field_privacy = {}
    db.flush()
    from app.modules.sharing.core import enforce_person_ceiling

    enforce_person_ceiling(ctx, person.id)
    audit.log(
        ctx, "person.erased", target_type="person", target_id=person.id, details={"reason": reason[:200]}
    )
    return person
