from __future__ import annotations

import datetime as dt
import hashlib
import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import or_, select

from app.authz.context import TreeContext
from app.authz.family_addresses import person_address_source_allows
from app.authz.permissions import Permission
from app.authz.privacy import FieldGroup, can_view_field
from app.core import audit
from app.core.dates import GenealogicalDate, date_to_json
from app.core.encrypted_json import decrypt_json as _dec
from app.core.encrypted_json import encrypt_json as _enc
from app.core.errors import Conflict, Forbidden, Unprocessable
from app.core.ids import uuid7
from app.models import (
    Citation,
    FamilyAddress,
    FamilyAddressVersion,
    Person,
    PersonAddress,
    PersonContactMethod,
    PersonDetailRevision,
)
from app.models.enums import AddressStatus, CitationTarget, ContactKind
from app.modules.genealogy import lookup
from app.modules.profile_details.schemas import (
    AddressIn,
    AddressOut,
    AddressUpdate,
    ContactIn,
    ContactOut,
    ContactUpdate,
    MoveAddressIn,
)


def _payload_aad(record_type: str, record_id: uuid.UUID) -> str:
    return f"person-{record_type}:{record_id}"


def _revision_aad(revision_id: uuid.UUID, side: str) -> str:
    return f"person-detail-revision:{revision_id}:{side}"


def _subject(ctx: TreeContext, person_id: uuid.UUID, group: str, *, write: bool = False):  # type: ignore[no-untyped-def]
    subject = lookup.get_person_subject(ctx, person_id)
    if not can_view_field(ctx, subject, group):
        raise Forbidden("This private profile field is not available to you")
    if write:
        ctx.require(Permission.PERSON_WRITE, person_id=person_id)
    return subject


def _address_payload(body: AddressIn | AddressUpdate) -> dict:
    return {key: getattr(body, key) for key in _address_payload_keys()}


def _address_payload_keys() -> tuple[str, ...]:
    return (
        "building",
        "street",
        "landmark",
        "notes",
        "as_recorded",
        "postal_code",
        "gram_panchayat",
        "post_office",
    )


def address_snapshot(row: PersonAddress) -> dict:
    return {
        "id": str(row.id),
        "person_id": str(row.person_id),
        "purpose": row.purpose.value,
        "status": row.status.value,
        "is_primary_current": row.is_primary_current,
        "place_id": str(row.place_id) if row.place_id else None,
        "locality": row.locality,
        "sub_district": row.sub_district,
        "district": row.district,
        "state": row.state,
        "country_code": row.country_code,
        "valid_from": row.valid_from,
        "valid_until": row.valid_until,
        **_dec(row.payload_enc, _payload_aad("address", row.id)),
    }


def _contact_value(row: PersonContactMethod) -> str:
    return _dec(row.value_enc, _payload_aad("contact", row.id))["value"]


def _contact_snapshot(row: PersonContactMethod) -> dict:
    return {
        "id": str(row.id),
        "person_id": str(row.person_id),
        "kind": row.kind.value,
        "value": _contact_value(row),
        "purpose": row.purpose,
        "language": row.language,
        "is_preferred": row.is_preferred,
        "copied_from_contact_id": (str(row.copied_from_contact_id) if row.copied_from_contact_id else None),
        "copied_from_revision": row.copied_from_revision,
    }


def _reuse_metadata(ctx: TreeContext, row: PersonAddress) -> dict:
    version_id = row.linked_family_address_version_id or row.source_family_address_version_id
    version = (
        ctx.db.scalar(
            select(FamilyAddressVersion).where(
                FamilyAddressVersion.tree_id == ctx.tree_id,
                FamilyAddressVersion.id == version_id,
            )
        )
        if version_id
        else None
    )
    family = (
        ctx.db.scalar(
            select(FamilyAddress).where(
                FamilyAddress.tree_id == ctx.tree_id,
                FamilyAddress.id == version.family_address_id,
            )
        )
        if version
        else None
    )
    update = (
        family.current_version
        if row.linked_family_address_version_id
        and family
        and version
        and family.current_version > version.version
        else None
    )
    return {
        "reuse_mode": row.reuse_mode,
        "family_address_id": family.id if family else None,
        "family_address_version": version.version if version else None,
        "family_update_available": update,
        "ancestral_assertion_id": row.ancestral_assertion_id,
    }


def project_address(row: PersonAddress, ctx: TreeContext | None = None) -> AddressOut:
    payload = _dec(row.payload_enc, _payload_aad("address", row.id))
    reuse = {
        "reuse_mode": row.reuse_mode,
        "family_address_id": None,
        "family_address_version": None,
        "family_update_available": None,
        "ancestral_assertion_id": row.ancestral_assertion_id,
    }
    if ctx is not None:
        reuse = _reuse_metadata(ctx, row)
    return AddressOut(
        id=row.id,
        person_id=row.person_id,
        purpose=row.purpose,
        status=row.status,
        is_primary_current=row.is_primary_current,
        place_id=row.place_id,
        locality=row.locality,
        sub_district=row.sub_district,
        district=row.district,
        state=row.state,
        country_code=row.country_code,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        revision=row.revision,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
        **reuse,
        **payload,
    )


def _source_revisions(ctx: TreeContext, rows: list[PersonContactMethod]) -> dict[uuid.UUID, int]:
    source_ids = {row.copied_from_contact_id for row in rows if row.copied_from_contact_id is not None}
    if not source_ids:
        return {}
    return dict(
        ctx.db.execute(
            select(PersonContactMethod.id, PersonContactMethod.revision).where(
                PersonContactMethod.tree_id == ctx.tree_id,
                PersonContactMethod.id.in_(source_ids),
                PersonContactMethod.withdrawn_at.is_(None),
            )
        ).all()
    )


def project_contacts(ctx: TreeContext, rows: list[PersonContactMethod]) -> list[ContactOut]:
    source_revisions = _source_revisions(ctx, rows)
    return [
        ContactOut(
            id=row.id,
            person_id=row.person_id,
            kind=row.kind,
            hint=row.value_hint,
            purpose=row.purpose,
            language=row.language,
            is_preferred=row.is_preferred,
            copied_from_contact_id=row.copied_from_contact_id,
            copy_outdated=(
                row.copied_from_contact_id is not None
                and source_revisions.get(row.copied_from_contact_id) != row.copied_from_revision
            ),
            revision=row.revision,
            source=row.source,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def project_contact(ctx: TreeContext, row: PersonContactMethod) -> ContactOut:
    return project_contacts(ctx, [row])[0]


def _require_address_identity(snapshot: dict) -> None:
    fields = (
        "place_id",
        "as_recorded",
        "building",
        "street",
        "locality",
        "sub_district",
        "district",
        "state",
        "postal_code",
        "gram_panchayat",
        "post_office",
    )
    if not any(snapshot.get(field) and str(snapshot[field]).strip() for field in fields):
        raise Unprocessable(
            "enter at least one place or postal address detail", code="address_detail_required"
        )


def _history(
    ctx: TreeContext,
    kind: str,
    row_id: uuid.UUID,
    person_id: uuid.UUID,
    revision: int,
    operation: str,
    before: dict | None,
    after: dict | None,
    reason: str | None = None,
) -> None:
    rid = uuid7()
    ctx.db.add(
        PersonDetailRevision(
            id=rid,
            tree_id=ctx.tree_id,
            person_id=person_id,
            record_type=kind,
            record_id=row_id,
            revision=revision,
            operation=operation,
            reason_enc=_enc({"reason": reason}, _revision_aad(rid, "reason")) if reason else None,
            before_enc=_enc(before, _revision_aad(rid, "before")) if before is not None else None,
            after_enc=_enc(after, _revision_aad(rid, "after")) if after is not None else None,
            created_by=ctx.user_id,
            updated_by=ctx.user_id,
        )
    )


def _dates(
    valid_from: GenealogicalDate | None, valid_until: GenealogicalDate | None
) -> tuple[dict | None, dict | None]:
    if valid_from and valid_until:
        low = valid_from.sort_range()[0]
        high = valid_until.sort_range()[1]
        if low is not None and high is not None and high < low:
            raise Unprocessable("valid_until is before valid_from", code="invalid_period")
    return date_to_json(valid_from), date_to_json(valid_until)


def _get_address(
    ctx: TreeContext, person_id: uuid.UUID, address_id: uuid.UUID, *, lock: bool = False
) -> PersonAddress:
    stmt = select(PersonAddress).where(
        PersonAddress.tree_id == ctx.tree_id,
        PersonAddress.person_id == person_id,
        PersonAddress.id == address_id,
        PersonAddress.withdrawn_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    row = ctx.db.scalar(stmt)
    if row is None:
        from app.core.errors import NotFound

        raise NotFound("Address not found")
    return row


def get_reusable_address(
    ctx: TreeContext, person_id: uuid.UUID, address_id: uuid.UUID, *, lock: bool = False
) -> PersonAddress:
    """Public reuse seam: subject authorization plus source-ceiling enforcement."""
    _subject(ctx, person_id, FieldGroup.ADDRESS)
    row = _get_address(ctx, person_id, address_id, lock=lock)
    if not person_address_source_allows(ctx, row):
        from app.core.errors import NotFound

        raise NotFound("Address not found")
    return row


def adopt_family_snapshot(
    ctx: TreeContext,
    person_id: uuid.UUID,
    address_id: uuid.UUID,
    *,
    expected_revision: int,
    snapshot: dict,
    linked_version_id: uuid.UUID,
    root_version_id: uuid.UUID,
) -> PersonAddress:
    """Replace one linked snapshot while preserving profile-detail history invariants."""
    _subject(ctx, person_id, FieldGroup.ADDRESS, write=True)
    _lock_person(ctx, person_id)
    row = _get_address(ctx, person_id, address_id, lock=True)
    if row.revision != expected_revision:
        raise Conflict("Address changed since it was loaded", code="stale_revision")
    if row.linked_family_address_version_id is None:
        raise Unprocessable("Only a linked family address can adopt a version", code="not_linked")
    before = address_snapshot(row)
    for field in ("place_id", "locality", "sub_district", "district", "state", "country_code"):
        setattr(row, field, snapshot.get(field))
    row.payload_enc = _enc(
        {key: snapshot.get(key) for key in _address_payload_keys()},
        _payload_aad("address", row.id),
    )
    row.linked_family_address_version_id = linked_version_id
    row.root_source_family_address_version_id = root_version_id
    row.revision += 1
    row.updated_by = ctx.user_id
    _history(
        ctx,
        "address",
        row.id,
        person_id,
        row.revision,
        "family_adopted",
        before,
        address_snapshot(row),
    )
    ctx.db.flush()
    return row


def purge_reused_address_derivatives(
    ctx: TreeContext,
    *,
    source_address_ids: set[uuid.UUID] | None = None,
    source_family_version_ids: set[uuid.UUID] | None = None,
    ancestral_assertion_ids: set[uuid.UUID] | None = None,
) -> set[uuid.UUID]:
    """Irreversibly blank every downstream profile copy and leave a fail-closed tombstone."""
    source_address_ids = set(source_address_ids or ())
    source_family_version_ids = set(source_family_version_ids or ())
    ancestral_assertion_ids = set(ancestral_assertion_ids or ())
    affected: dict[uuid.UUID, PersonAddress] = {}
    frontier = source_address_ids

    # The first pass finds direct family/assertion derivatives as well as person copies.
    while True:
        conditions = []
        if frontier:
            conditions.append(PersonAddress.copied_from_person_address_id.in_(frontier))
        if source_family_version_ids:
            conditions.extend(
                (
                    PersonAddress.linked_family_address_version_id.in_(source_family_version_ids),
                    PersonAddress.source_family_address_version_id.in_(source_family_version_ids),
                    PersonAddress.root_source_family_address_version_id.in_(source_family_version_ids),
                )
            )
        if ancestral_assertion_ids:
            conditions.append(PersonAddress.ancestral_assertion_id.in_(ancestral_assertion_ids))
        if not conditions:
            break
        rows = ctx.db.scalars(
            select(PersonAddress).where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.id.not_in(affected),
                or_(*conditions),
            )
        ).all()
        new_rows = [row for row in rows if row.id not in affected]
        if not new_rows:
            break
        affected.update({row.id: row for row in new_rows})
        frontier = {row.id for row in new_rows}
        # Family/assertion roots are only needed on the initial pass; later passes follow copies.
        source_family_version_ids = set()
        ancestral_assertion_ids = set()

    if not affected:
        return set()
    now = dt.datetime.now(dt.UTC)
    ids = set(affected)
    ctx.db.execute(
        sa_delete(PersonDetailRevision).where(
            PersonDetailRevision.tree_id == ctx.tree_id,
            PersonDetailRevision.record_type == "address",
            PersonDetailRevision.record_id.in_(ids),
        )
    )
    ctx.db.execute(
        sa_delete(Citation).where(
            Citation.tree_id == ctx.tree_id,
            Citation.target_type == CitationTarget.ADDRESS,
            Citation.target_id.in_(ids),
        )
    )
    blank = dict.fromkeys(_address_payload_keys())
    for row in affected.values():
        row.place_id = None
        row.locality = None
        row.sub_district = None
        row.district = None
        row.state = None
        row.country_code = None
        row.payload_enc = _enc(blank, _payload_aad("address", row.id))
        row.valid_from = None
        row.valid_until = None
        row.is_primary_current = False
        row.source_revoked_at = now
        row.withdrawn_at = now
        row.revision += 1
        row.updated_by = ctx.user_id
    ctx.db.flush()
    return ids


def _lock_person(ctx: TreeContext, person_id: uuid.UUID) -> None:
    """Serialize detail writes even when no primary or idempotency row exists yet."""
    ctx.db.scalar(
        select(Person.id).where(Person.tree_id == ctx.tree_id, Person.id == person_id).with_for_update()
    )


def list_addresses(
    ctx: TreeContext, person_id: uuid.UUID, *, offset: int = 0, limit: int = 51
) -> list[PersonAddress]:
    _subject(ctx, person_id, FieldGroup.ADDRESS)
    rows = list(
        ctx.db.scalars(
            select(PersonAddress)
            .where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.person_id == person_id,
                PersonAddress.withdrawn_at.is_(None),
            )
            .order_by(PersonAddress.is_primary_current.desc(), PersonAddress.created_at, PersonAddress.id)
        )
    )
    visible = [row for row in rows if person_address_source_allows(ctx, row)]
    return visible[offset : offset + limit]


def create_address(
    ctx: TreeContext, person_id: uuid.UUID, body: AddressIn, *, source: str = "manual", legacy: bool = False
) -> PersonAddress:
    _subject(ctx, person_id, FieldGroup.ADDRESS, write=True)
    _lock_person(ctx, person_id)
    if body.idempotency_key:
        existing = ctx.db.scalar(
            select(PersonAddress).where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.person_id == person_id,
                PersonAddress.idempotency_key == body.idempotency_key,
            )
        )
        if existing:
            return existing
    if body.place_id:
        lookup.get_place(ctx, body.place_id)
    valid_from, valid_until = _dates(body.valid_from, body.valid_until)
    row_id = uuid7()
    if body.is_primary_current:
        for old in ctx.db.scalars(
            select(PersonAddress)
            .where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.person_id == person_id,
                PersonAddress.is_primary_current.is_(True),
                PersonAddress.withdrawn_at.is_(None),
            )
            .with_for_update()
        ):
            before = address_snapshot(old)
            old.is_primary_current = False
            old.revision += 1
            old.updated_by = ctx.user_id
            _history(
                ctx,
                "address",
                old.id,
                person_id,
                old.revision,
                "primary_reassigned",
                before,
                address_snapshot(old),
            )
    row = PersonAddress(
        id=row_id,
        tree_id=ctx.tree_id,
        person_id=person_id,
        purpose=body.purpose,
        status=body.status,
        is_primary_current=body.is_primary_current,
        place_id=body.place_id,
        locality=body.locality,
        sub_district=body.sub_district,
        district=body.district,
        state=body.state,
        country_code=body.country_code,
        payload_enc=_enc(_address_payload(body), _payload_aad("address", row_id)),
        valid_from=valid_from,
        valid_until=valid_until,
        idempotency_key=body.idempotency_key,
        source=source,
        legacy_imported=legacy,
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    ctx.db.add(row)
    ctx.db.flush()
    _history(ctx, "address", row.id, person_id, 1, "created", None, address_snapshot(row))
    audit.log(
        ctx,
        "person_address.created",
        target_type="person_address",
        target_id=row.id,
        details={"person_id": str(person_id), "purpose": body.purpose.value},
    )
    return row


def update_address(
    ctx: TreeContext, person_id: uuid.UUID, address_id: uuid.UUID, body: AddressUpdate
) -> PersonAddress:
    _subject(ctx, person_id, FieldGroup.ADDRESS, write=True)
    _lock_person(ctx, person_id)
    row = _get_address(ctx, person_id, address_id, lock=True)
    if row.linked_family_address_version_id is not None:
        raise Unprocessable(
            "A linked address is immutable; copy it or adopt a shared version",
            code="linked_address_immutable",
        )
    if row.revision != body.revision:
        raise Conflict(
            "Address changed since it was loaded",
            code="stale_revision",
            details={"current_revision": row.revision},
        )
    before = address_snapshot(row)
    fields = body.model_dump(
        exclude_unset=True,
        exclude={
            "revision",
            "reason",
            "building",
            "street",
            "landmark",
            "notes",
            "as_recorded",
            "postal_code",
            "gram_panchayat",
            "post_office",
        },
    )
    if fields.get("place_id"):
        lookup.get_place(ctx, fields["place_id"])
    for key, value in fields.items():
        if key in {"valid_from", "valid_until"}:
            setattr(row, key, date_to_json(value))
        else:
            setattr(row, key, value)
    payload = _dec(row.payload_enc, _payload_aad("address", row.id))
    for key in (
        "building",
        "street",
        "landmark",
        "notes",
        "as_recorded",
        "postal_code",
        "gram_panchayat",
        "post_office",
    ):
        if key in body.model_fields_set:
            payload[key] = getattr(body, key)
    row.payload_enc = _enc(payload, _payload_aad("address", row.id))
    vf = GenealogicalDate.model_validate(row.valid_from) if row.valid_from else None
    vu = GenealogicalDate.model_validate(row.valid_until) if row.valid_until else None
    _dates(vf, vu)
    _require_address_identity(address_snapshot(row))
    if row.is_primary_current and row.status != AddressStatus.CURRENT:
        raise Unprocessable("a primary address must be current")
    if row.is_primary_current:
        for old in ctx.db.scalars(
            select(PersonAddress)
            .where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.person_id == person_id,
                PersonAddress.id != row.id,
                PersonAddress.is_primary_current.is_(True),
                PersonAddress.withdrawn_at.is_(None),
            )
            .with_for_update()
        ):
            old_before = address_snapshot(old)
            old.is_primary_current = False
            old.revision += 1
            old.updated_by = ctx.user_id
            _history(
                ctx,
                "address",
                old.id,
                person_id,
                old.revision,
                "primary_reassigned",
                old_before,
                address_snapshot(old),
            )
    row.revision += 1
    row.updated_by = ctx.user_id
    _history(
        ctx,
        "address",
        row.id,
        person_id,
        row.revision,
        "updated",
        before,
        address_snapshot(row),
        body.reason,
    )
    audit.log(
        ctx,
        "person_address.changed",
        target_type="person_address",
        target_id=row.id,
        details={"person_id": str(person_id), "fields": sorted(body.model_fields_set - {"reason"})},
    )
    return row


def move_address(
    ctx: TreeContext, person_id: uuid.UUID, address_id: uuid.UUID, body: MoveAddressIn
) -> tuple[PersonAddress, PersonAddress]:
    _subject(ctx, person_id, FieldGroup.ADDRESS, write=True)
    _lock_person(ctx, person_id)
    move_key = hashlib.sha256(f"move:{address_id}:{body.idempotency_key}".encode()).hexdigest()
    existing = ctx.db.scalar(
        select(PersonAddress).where(
            PersonAddress.tree_id == ctx.tree_id,
            PersonAddress.person_id == person_id,
            PersonAddress.idempotency_key == move_key,
        )
    )
    old = _get_address(ctx, person_id, address_id, lock=True)
    if old.linked_family_address_version_id is not None:
        raise Unprocessable(
            "A linked address is immutable; copy it before recording a move",
            code="linked_address_immutable",
        )
    if existing:
        return old, existing
    if old.revision != body.revision:
        raise Conflict(
            "Address changed since it was loaded",
            code="stale_revision",
            details={"current_revision": old.revision},
        )
    before = address_snapshot(old)
    old.status = AddressStatus.FORMER
    old.is_primary_current = False
    old_from = GenealogicalDate.model_validate(old.valid_from) if old.valid_from else None
    _, old_until = _dates(old_from, body.valid_until)
    old.valid_until = old_until
    old.revision += 1
    old.updated_by = ctx.user_id
    _history(
        ctx,
        "address",
        old.id,
        person_id,
        old.revision,
        "moved_from",
        before,
        address_snapshot(old),
        body.reason,
    )
    new_body = body.new_address.model_copy(
        update={"status": AddressStatus.CURRENT, "idempotency_key": move_key}
    )
    new = create_address(ctx, person_id, new_body)
    audit.log(
        ctx,
        "person_address.moved",
        target_type="person_address",
        target_id=old.id,
        details={"person_id": str(person_id), "new_address_id": str(new.id)},
    )
    return old, new


def withdraw_address(
    ctx: TreeContext, person_id: uuid.UUID, address_id: uuid.UUID, revision: int, reason: str | None
) -> None:
    row = require_address_withdrawal(ctx, person_id, address_id, revision)
    before = address_snapshot(row)
    row.withdrawn_at = dt.datetime.now(dt.UTC)
    row.is_primary_current = False
    row.revision += 1
    _history(ctx, "address", row.id, person_id, row.revision, "withdrawn", before, None, reason)
    audit.log(
        ctx,
        "person_address.withdrawn",
        target_type="person_address",
        target_id=row.id,
        details={"person_id": str(person_id)},
    )


def require_address_withdrawal(
    ctx: TreeContext, person_id: uuid.UUID, address_id: uuid.UUID, revision: int
) -> PersonAddress:
    """Authorize and lock an address before cross-module derivative revocation."""
    _subject(ctx, person_id, FieldGroup.ADDRESS, write=True)
    _lock_person(ctx, person_id)
    row = _get_address(ctx, person_id, address_id, lock=True)
    if row.revision != revision:
        raise Conflict("Address changed since it was loaded", code="stale_revision")
    return row


def address_history(
    ctx: TreeContext,
    person_id: uuid.UUID,
    address_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int = 51,
) -> list[dict]:
    _subject(ctx, person_id, FieldGroup.ADDRESS)
    rows = ctx.db.scalars(
        select(PersonDetailRevision)
        .where(
            PersonDetailRevision.tree_id == ctx.tree_id,
            PersonDetailRevision.person_id == person_id,
            PersonDetailRevision.record_type == "address",
            PersonDetailRevision.record_id == address_id,
        )
        .order_by(PersonDetailRevision.revision)
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "revision": r.revision,
            "operation": r.operation,
            "reason": (_dec(r.reason_enc, _revision_aad(r.id, "reason"))["reason"] if r.reason_enc else None),
            "before": _dec(r.before_enc, _revision_aad(r.id, "before")) if r.before_enc else None,
            "after": _dec(r.after_enc, _revision_aad(r.id, "after")) if r.after_enc else None,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def _hint(kind: ContactKind, value: str) -> str:
    if kind == ContactKind.EMAIL:
        local, domain = value.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if kind in {ContactKind.MOBILE, ContactKind.WHATSAPP}:
        return f"{value[:3]}••••••{value[-2:]}"
    if value.startswith("@"):
        return f"@{value[1:2]}***"
    if kind == ContactKind.LEGACY_NOTE:
        return "Legacy contact note"
    return f"{value[:12]}…"


def list_contacts(
    ctx: TreeContext, person_id: uuid.UUID, *, offset: int = 0, limit: int = 51
) -> list[PersonContactMethod]:
    _subject(ctx, person_id, FieldGroup.CONTACT)
    return list(
        ctx.db.scalars(
            select(PersonContactMethod)
            .where(
                PersonContactMethod.tree_id == ctx.tree_id,
                PersonContactMethod.person_id == person_id,
                PersonContactMethod.withdrawn_at.is_(None),
            )
            .order_by(
                PersonContactMethod.kind,
                PersonContactMethod.is_preferred.desc(),
                PersonContactMethod.created_at,
                PersonContactMethod.id,
            )
            .offset(offset)
            .limit(limit)
        )
    )


def create_contact(
    ctx: TreeContext, person_id: uuid.UUID, body: ContactIn, *, source: str = "manual", legacy: bool = False
) -> PersonContactMethod:
    _subject(ctx, person_id, FieldGroup.CONTACT, write=True)
    _lock_person(ctx, person_id)
    if body.idempotency_key:
        existing = ctx.db.scalar(
            select(PersonContactMethod).where(
                PersonContactMethod.tree_id == ctx.tree_id,
                PersonContactMethod.person_id == person_id,
                PersonContactMethod.idempotency_key == body.idempotency_key,
            )
        )
        if existing:
            return existing
    value = body.value
    if body.copied_from_contact_id is not None:
        source_contact = _get_contact(ctx, person_id, body.copied_from_contact_id, lock=True)
        if source_contact.kind != ContactKind.MOBILE:
            raise Unprocessable("WhatsApp can only copy a mobile contact", code="invalid_copy_source")
        if source_contact.revision != body.copied_from_revision:
            raise Conflict("Mobile contact changed since it was selected", code="stale_revision")
        value = _contact_value(source_contact)
    if body.is_preferred:
        for old in ctx.db.scalars(
            select(PersonContactMethod)
            .where(
                PersonContactMethod.tree_id == ctx.tree_id,
                PersonContactMethod.person_id == person_id,
                PersonContactMethod.kind == body.kind,
                PersonContactMethod.is_preferred.is_(True),
                PersonContactMethod.withdrawn_at.is_(None),
            )
            .with_for_update()
        ):
            before = _contact_snapshot(old)
            old.is_preferred = False
            old.revision += 1
            old.updated_by = ctx.user_id
            _history(
                ctx,
                "contact",
                old.id,
                person_id,
                old.revision,
                "preferred_reassigned",
                before,
                _contact_snapshot(old),
            )
    rid = uuid7()
    row = PersonContactMethod(
        id=rid,
        tree_id=ctx.tree_id,
        person_id=person_id,
        kind=body.kind,
        value_enc=_enc({"value": value}, _payload_aad("contact", rid)),
        value_hint=_hint(body.kind, value),
        purpose=body.purpose,
        language=body.language,
        is_preferred=body.is_preferred,
        copied_from_contact_id=body.copied_from_contact_id,
        copied_from_revision=body.copied_from_revision,
        idempotency_key=body.idempotency_key,
        source=source,
        legacy_imported=legacy,
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    ctx.db.add(row)
    ctx.db.flush()
    _history(ctx, "contact", row.id, person_id, 1, "created", None, _contact_snapshot(row))
    audit.log(
        ctx,
        "person_contact.created",
        target_type="person_contact",
        target_id=row.id,
        details={"person_id": str(person_id), "kind": body.kind.value},
    )
    return row


def _get_contact(
    ctx: TreeContext, person_id: uuid.UUID, contact_id: uuid.UUID, *, lock: bool = False
) -> PersonContactMethod:
    stmt = select(PersonContactMethod).where(
        PersonContactMethod.tree_id == ctx.tree_id,
        PersonContactMethod.person_id == person_id,
        PersonContactMethod.id == contact_id,
        PersonContactMethod.withdrawn_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    row = ctx.db.scalar(stmt)
    if row is None:
        from app.core.errors import NotFound

        raise NotFound("Contact method not found")
    return row


def _profile_url(kind: ContactKind, value: str) -> str | None:
    if kind == ContactKind.TELEGRAM:
        return value if value.startswith("https://t.me/") else f"https://t.me/{value.removeprefix('@')}"
    if kind == ContactKind.INSTAGRAM:
        if value.startswith("https://"):
            return value
        return f"https://www.instagram.com/{value.removeprefix('@')}/"
    return None


def reveal_contact(ctx: TreeContext, person_id: uuid.UUID, contact_id: uuid.UUID) -> tuple[str, str | None]:
    _subject(ctx, person_id, FieldGroup.CONTACT)
    row = _get_contact(ctx, person_id, contact_id)
    audit.log(
        ctx,
        "person_contact.revealed",
        target_type="person_contact",
        target_id=row.id,
        details={"person_id": str(person_id), "kind": row.kind.value},
    )
    value = _contact_value(row)
    return value, _profile_url(row.kind, value)


def update_contact(
    ctx: TreeContext, person_id: uuid.UUID, contact_id: uuid.UUID, body: ContactUpdate
) -> PersonContactMethod:
    from app.modules.profile_details.schemas import validate_contact

    _subject(ctx, person_id, FieldGroup.CONTACT, write=True)
    _lock_person(ctx, person_id)
    row = _get_contact(ctx, person_id, contact_id, lock=True)
    if row.revision != body.revision:
        raise Conflict(
            "Contact changed since it was loaded",
            code="stale_revision",
            details={"current_revision": row.revision},
        )
    before = _contact_snapshot(row)
    copy_fields = {"copied_from_contact_id", "copied_from_revision"}
    copy_changed = bool(copy_fields & body.model_fields_set)
    if copy_changed and body.copied_from_contact_id is not None:
        if row.kind != ContactKind.WHATSAPP:
            raise Unprocessable("only WhatsApp can be copied from a mobile contact")
        source_contact = _get_contact(ctx, person_id, body.copied_from_contact_id, lock=True)
        if source_contact.kind != ContactKind.MOBILE:
            raise Unprocessable("WhatsApp can only copy a mobile contact", code="invalid_copy_source")
        if source_contact.revision != body.copied_from_revision:
            raise Conflict("Mobile contact changed since it was selected", code="stale_revision")
        copied_value = _contact_value(source_contact)
        row.value_enc = _enc({"value": copied_value}, _payload_aad("contact", row.id))
        row.value_hint = _hint(row.kind, copied_value)
        row.copied_from_contact_id = body.copied_from_contact_id
        row.copied_from_revision = body.copied_from_revision
    elif copy_changed:
        row.copied_from_contact_id = None
        row.copied_from_revision = None
    copying_from_mobile = copy_changed and body.copied_from_contact_id is not None
    if "value" in body.model_fields_set and body.value is not None and not copying_from_mobile:
        try:
            validate_contact(row.kind, body.value)
        except ValueError as exc:
            raise Unprocessable(str(exc)) from exc
        row.value_enc = _enc({"value": body.value}, _payload_aad("contact", row.id))
        row.value_hint = _hint(row.kind, body.value)
        row.copied_from_contact_id = None
        row.copied_from_revision = None
    for key in ("purpose", "language", "is_preferred"):
        if key in body.model_fields_set:
            setattr(row, key, getattr(body, key))
    if row.is_preferred:
        for old in ctx.db.scalars(
            select(PersonContactMethod)
            .where(
                PersonContactMethod.tree_id == ctx.tree_id,
                PersonContactMethod.person_id == person_id,
                PersonContactMethod.kind == row.kind,
                PersonContactMethod.id != row.id,
                PersonContactMethod.is_preferred.is_(True),
                PersonContactMethod.withdrawn_at.is_(None),
            )
            .with_for_update()
        ):
            old_before = _contact_snapshot(old)
            old.is_preferred = False
            old.revision += 1
            old.updated_by = ctx.user_id
            _history(
                ctx,
                "contact",
                old.id,
                person_id,
                old.revision,
                "preferred_reassigned",
                old_before,
                _contact_snapshot(old),
            )
    row.revision += 1
    row.updated_by = ctx.user_id
    _history(
        ctx,
        "contact",
        row.id,
        person_id,
        row.revision,
        "updated",
        before,
        _contact_snapshot(row),
        body.reason,
    )
    audit.log(
        ctx,
        "person_contact.changed",
        target_type="person_contact",
        target_id=row.id,
        details={"person_id": str(person_id), "fields": sorted(body.model_fields_set - {"reason"})},
    )
    return row


def withdraw_contact(
    ctx: TreeContext, person_id: uuid.UUID, contact_id: uuid.UUID, revision: int, reason: str | None
) -> None:
    _subject(ctx, person_id, FieldGroup.CONTACT, write=True)
    _lock_person(ctx, person_id)
    row = _get_contact(ctx, person_id, contact_id, lock=True)
    if row.revision != revision:
        raise Conflict("Contact changed since it was loaded", code="stale_revision")
    before = _contact_snapshot(row)
    row.withdrawn_at = dt.datetime.now(dt.UTC)
    row.is_preferred = False
    row.revision += 1
    _history(ctx, "contact", row.id, person_id, row.revision, "withdrawn", before, None, reason)
    audit.log(
        ctx,
        "person_contact.withdrawn",
        target_type="person_contact",
        target_id=row.id,
        details={"person_id": str(person_id)},
    )


def contact_history(
    ctx: TreeContext,
    person_id: uuid.UUID,
    contact_id: uuid.UUID,
    *,
    offset: int = 0,
    limit: int = 51,
) -> list[dict]:
    _subject(ctx, person_id, FieldGroup.CONTACT)
    rows = ctx.db.scalars(
        select(PersonDetailRevision)
        .where(
            PersonDetailRevision.tree_id == ctx.tree_id,
            PersonDetailRevision.person_id == person_id,
            PersonDetailRevision.record_type == "contact",
            PersonDetailRevision.record_id == contact_id,
        )
        .order_by(PersonDetailRevision.revision)
        .offset(offset)
        .limit(limit)
    ).all()

    def masked_snapshot(value: str | None, row_id: uuid.UUID, side: str) -> dict | None:
        if not value:
            return None
        snapshot = _dec(value, _revision_aad(row_id, side))
        if snapshot.get("value"):
            snapshot["value"] = _hint(ContactKind(snapshot["kind"]), snapshot["value"])
        return snapshot

    return [
        {
            "revision": row.revision,
            "operation": row.operation,
            "reason": (
                _dec(row.reason_enc, _revision_aad(row.id, "reason"))["reason"] if row.reason_enc else None
            ),
            "before": masked_snapshot(row.before_enc, row.id, "before"),
            "after": masked_snapshot(row.after_enc, row.id, "after"),
            "created_at": row.created_at,
        }
        for row in rows
    ]


def set_legacy_address(ctx: TreeContext, person_id: uuid.UUID, value: str | None) -> None:
    _subject(ctx, person_id, FieldGroup.ADDRESS, write=True)
    _lock_person(ctx, person_id)
    row = ctx.db.scalar(
        select(PersonAddress)
        .where(
            PersonAddress.tree_id == ctx.tree_id,
            PersonAddress.person_id == person_id,
            PersonAddress.legacy_imported.is_(True),
            PersonAddress.withdrawn_at.is_(None),
        )
        .with_for_update()
    )
    if row and value is None:
        withdraw_address(ctx, person_id, row.id, row.revision, "Legacy profile field cleared")
    elif row:
        update_address(
            ctx,
            person_id,
            row.id,
            AddressUpdate(
                revision=row.revision,
                as_recorded=value,
                reason="Updated through legacy profile field",
            ),
        )
    elif value is not None:
        from app.models.enums import AddressPurpose

        create_address(
            ctx,
            person_id,
            AddressIn(
                purpose=AddressPurpose.UNKNOWN,
                status=AddressStatus.UNKNOWN,
                is_primary_current=False,
                as_recorded=value,
            ),
            source="legacy_profile",
            legacy=True,
        )


def active_legacy_address_id(ctx: TreeContext, person_id: uuid.UUID) -> uuid.UUID | None:
    """Public lifecycle seam for callers that must revoke derivatives before legacy withdrawal."""
    return ctx.db.scalar(
        select(PersonAddress.id).where(
            PersonAddress.tree_id == ctx.tree_id,
            PersonAddress.person_id == person_id,
            PersonAddress.legacy_imported.is_(True),
            PersonAddress.withdrawn_at.is_(None),
        )
    )


def set_legacy_contact(ctx: TreeContext, person_id: uuid.UUID, value: str | None) -> None:
    _subject(ctx, person_id, FieldGroup.CONTACT, write=True)
    _lock_person(ctx, person_id)
    row = ctx.db.scalar(
        select(PersonContactMethod)
        .where(
            PersonContactMethod.tree_id == ctx.tree_id,
            PersonContactMethod.person_id == person_id,
            PersonContactMethod.legacy_imported.is_(True),
            PersonContactMethod.withdrawn_at.is_(None),
        )
        .with_for_update()
    )
    if row and value is None:
        withdraw_contact(ctx, person_id, row.id, row.revision, "Legacy profile field cleared")
    elif row:
        update_contact(
            ctx,
            person_id,
            row.id,
            ContactUpdate(
                revision=row.revision,
                value=value,
                reason="Updated through legacy profile field",
            ),
        )
    elif value is not None:
        create_contact(
            ctx,
            person_id,
            ContactIn(kind=ContactKind.LEGACY_NOTE, value=value),
            source="legacy_profile",
            legacy=True,
        )


def legacy_values(ctx: TreeContext, person_id: uuid.UUID) -> tuple[str | None, str | None]:
    address = ctx.db.scalar(
        select(PersonAddress).where(
            PersonAddress.tree_id == ctx.tree_id,
            PersonAddress.person_id == person_id,
            PersonAddress.legacy_imported.is_(True),
            PersonAddress.withdrawn_at.is_(None),
        )
    )
    contact = ctx.db.scalar(
        select(PersonContactMethod).where(
            PersonContactMethod.tree_id == ctx.tree_id,
            PersonContactMethod.person_id == person_id,
            PersonContactMethod.legacy_imported.is_(True),
            PersonContactMethod.withdrawn_at.is_(None),
        )
    )
    address_value = None
    if address:
        address_value = _dec(address.payload_enc, _payload_aad("address", address.id)).get("as_recorded")
    return address_value, _contact_value(contact) if contact else None


def legacy_presence(ctx: TreeContext, person_id: uuid.UUID) -> tuple[bool, bool]:
    address = ctx.db.scalar(
        select(PersonAddress.id).where(
            PersonAddress.tree_id == ctx.tree_id,
            PersonAddress.person_id == person_id,
            PersonAddress.legacy_imported.is_(True),
            PersonAddress.withdrawn_at.is_(None),
        )
    )
    contact = ctx.db.scalar(
        select(PersonContactMethod.id).where(
            PersonContactMethod.tree_id == ctx.tree_id,
            PersonContactMethod.person_id == person_id,
            PersonContactMethod.legacy_imported.is_(True),
            PersonContactMethod.withdrawn_at.is_(None),
        )
    )
    return address is not None, contact is not None
