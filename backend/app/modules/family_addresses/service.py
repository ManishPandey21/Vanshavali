from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.family_addresses import (
    family_address_audience_allows,
    version_ancestor_ids,
)
from app.authz.family_addresses import (
    family_address_version_allows as version_allows,
)
from app.authz.family_addresses import (
    person_address_source_allows as address_source_allows,
)
from app.authz.family_addresses import (
    require_family_address_controller as _require_controller,
)
from app.authz.permissions import Permission, permissions_for
from app.authz.privacy import FieldGroup, can_view_field
from app.core import audit
from app.core.encrypted_json import decrypt_json, encrypt_json
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.ids import uuid7
from app.models import (
    AccessGrant,
    Assertion,
    AuditEvent,
    FamilyAddress,
    FamilyAddressReleaseConsent,
    FamilyAddressVersion,
    FamilyAddressVersionAncestor,
    FamilyAddressVersionSource,
    Person,
    PersonAddress,
    TreeMembership,
    User,
)
from app.models.enums import (
    AddressReuseMode,
    GrantPermission,
    GrantResource,
    HeritageAttribute,
    RecordPrivacyLevel,
    Role,
)
from app.modules.family_addresses.schemas import (
    ActivateSharingIn,
    AddressReuseIn,
    AffectedAddressOut,
    FamilyAddressCreateIn,
    FamilyAddressGrantIn,
    FamilyAddressGrantOut,
    FamilyAddressOut,
    FamilyAddressSnapshot,
    FamilyAddressSourceOut,
    FamilyAddressVersionIn,
    ReleaseConsentIn,
    ReleaseConsentOut,
    ReleasePreviewOut,
    ReleaseReaderOut,
)
from app.modules.genealogy import lookup
from app.modules.heritage import service as heritage
from app.modules.profile_details.schemas import AddressIn, AddressOut, AdoptFamilyAddressVersionIn


def _aad(version_id: uuid.UUID) -> str:
    return f"family-address-version:{version_id}"


def _payload(snapshot: FamilyAddressSnapshot | dict) -> dict:
    data = snapshot if isinstance(snapshot, dict) else snapshot.model_dump(mode="json")
    return {
        key: data.get(key)
        for key in (
            "building",
            "street",
            "landmark",
            "notes",
            "as_recorded",
            "postal_code",
            "gram_panchayat",
            "post_office",
        )
    }


def _snapshot(version: FamilyAddressVersion) -> FamilyAddressSnapshot:
    return FamilyAddressSnapshot(
        place_id=version.place_id,
        locality=version.locality,
        sub_district=version.sub_district,
        district=version.district,
        state=version.state,
        country_code=version.country_code,
        **decrypt_json(version.payload_enc, _aad(version.id)),
    )


def _family(ctx: TreeContext, address_id: uuid.UUID, *, lock: bool = False) -> FamilyAddress:
    stmt = select(FamilyAddress).where(FamilyAddress.tree_id == ctx.tree_id, FamilyAddress.id == address_id)
    if lock:
        stmt = stmt.with_for_update()
    row = ctx.db.scalar(stmt)
    if row is None:
        raise NotFound("Family address not found")
    return row


def _version(
    ctx: TreeContext,
    family_address_id: uuid.UUID,
    version: int,
    *,
    lock: bool = False,
) -> FamilyAddressVersion:
    stmt = select(FamilyAddressVersion).where(
        FamilyAddressVersion.tree_id == ctx.tree_id,
        FamilyAddressVersion.family_address_id == family_address_id,
        FamilyAddressVersion.version == version,
    )
    if lock:
        stmt = stmt.with_for_update()
    row = ctx.db.scalar(stmt)
    if row is None:
        raise NotFound("Family address version not found")
    return row


def _version_by_id(ctx: TreeContext, version_id: uuid.UUID) -> FamilyAddressVersion | None:
    return ctx.db.scalar(
        select(FamilyAddressVersion).where(
            FamilyAddressVersion.tree_id == ctx.tree_id, FamilyAddressVersion.id == version_id
        )
    )


def _require_visible(ctx: TreeContext, row: FamilyAddress) -> FamilyAddressVersion:
    version = _version(ctx, row.id, row.current_version)
    if not version_allows(ctx, version):
        raise NotFound("Family address not found")
    return version


def _make_version(
    ctx: TreeContext,
    row: FamilyAddress,
    number: int,
    snapshot: FamilyAddressSnapshot,
    *,
    reason: str | None = None,
    source_person_id: uuid.UUID | None = None,
    source_person_address_id: uuid.UUID | None = None,
    source_ancestral_assertion_id: uuid.UUID | None = None,
    root_source_version_id: uuid.UUID | None = None,
    ancestor_version_ids: set[uuid.UUID] | None = None,
) -> FamilyAddressVersion:
    version_id = uuid7()
    version = FamilyAddressVersion(
        id=version_id,
        tree_id=ctx.tree_id,
        family_address_id=row.id,
        version=number,
        place_id=snapshot.place_id,
        locality=snapshot.locality,
        sub_district=snapshot.sub_district,
        district=snapshot.district,
        state=snapshot.state,
        country_code=snapshot.country_code,
        payload_enc=encrypt_json(_payload(snapshot), _aad(version_id)),
        source_ancestral_assertion_id=source_ancestral_assertion_id,
        root_source_version_id=root_source_version_id,
        reason_enc=(encrypt_json({"reason": reason}, f"{_aad(version_id)}:reason") if reason else None),
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    ctx.db.add(version)
    if source_person_id is not None and source_person_address_id is not None:
        ctx.db.add(
            FamilyAddressVersionSource(
                id=uuid7(),
                tree_id=ctx.tree_id,
                version_id=version.id,
                source_person_id=source_person_id,
                source_person_address_id=source_person_address_id,
                created_by=ctx.user_id,
                updated_by=ctx.user_id,
            )
        )
    for ancestor_id in ancestor_version_ids or set():
        ctx.db.add(
            FamilyAddressVersionAncestor(
                id=uuid7(),
                tree_id=ctx.tree_id,
                descendant_version_id=version.id,
                ancestor_version_id=ancestor_id,
                created_by=ctx.user_id,
                updated_by=ctx.user_id,
            )
        )
    return version


def project(ctx: TreeContext, row: FamilyAddress) -> FamilyAddressOut:
    version = _require_visible(ctx, row)
    property_id = row.property_id
    if property_id is not None:
        from app.modules.property.service import get_property

        try:
            get_property(ctx, property_id)
        except NotFound:
            property_id = None
    return FamilyAddressOut(
        id=row.id,
        label=row.label,
        privacy_level=row.privacy_level,
        audience_branch_id=row.audience_branch_id,
        branch_id=row.branch_id,
        household_id=row.household_id,
        property_id=property_id,
        place_id=row.place_id,
        ancestral_assertion_id=row.ancestral_assertion_id,
        current_version=row.current_version,
        revision=row.revision,
        sharing_released=row.sharing_released,
        snapshot=_snapshot(version),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def get(ctx: TreeContext, family_address_id: uuid.UUID) -> FamilyAddress:
    row = _family(ctx, family_address_id)
    _require_visible(ctx, row)
    return row


def _ancestral_snapshot(ctx: TreeContext, assertion_id: uuid.UUID) -> tuple[Assertion, FamilyAddressSnapshot]:
    assertion, _subject = heritage.get_assertion(ctx, assertion_id)
    if assertion.attribute != HeritageAttribute.ANCESTRAL_VILLAGE.value:
        raise Unprocessable(
            "Only the canonical ancestral-village assertion can be reused",
            code="not_ancestral_village",
        )
    place = lookup.get_place(ctx, assertion.place_id) if assertion.place_id else None
    return assertion, FamilyAddressSnapshot(
        place_id=assertion.place_id,
        as_recorded=assertion.value_text or (place.canonical_name if place else None),
        locality=place.locality if place else None,
        district=place.district if place else None,
        state=place.state if place else None,
    )


def create(ctx: TreeContext, body: FamilyAddressCreateIn) -> FamilyAddress:
    ctx.require(Permission.FAMILY_WRITE)
    if ctx.membership_id is None:
        raise Forbidden()
    if body.idempotency_key:
        existing = ctx.db.scalar(
            select(FamilyAddress).where(
                FamilyAddress.tree_id == ctx.tree_id,
                FamilyAddress.controller_membership_id == ctx.membership_id,
                FamilyAddress.idempotency_key == body.idempotency_key,
            )
        )
        if existing is not None:
            return existing
    for model, ref, name in (
        ("FamilyBranch", body.audience_branch_id, "Branch"),
        ("FamilyBranch", body.branch_id, "Branch"),
        ("Household", body.household_id, "Household"),
    ):
        if ref:
            from app import models

            lookup.get_in_tree(ctx, getattr(models, model), ref, name)
    if body.property_id:
        from app.modules.property.service import get_property

        get_property(ctx, body.property_id)

    source_person_address_id = None
    source_ancestral_assertion_id = None
    root_source_version_id = None
    ancestor_version_ids: set[uuid.UUID] = set()
    ancestral_assertion_id = body.ancestral_assertion_id
    if body.snapshot is not None:
        snapshot = body.snapshot
    elif body.ancestral_assertion_id is not None:
        assertion, snapshot = _ancestral_snapshot(ctx, body.ancestral_assertion_id)
        source_ancestral_assertion_id = assertion.id
    else:
        from app.modules.profile_details import service as details

        if body.source_person_id is None or body.source_person_address_id is None:
            raise Unprocessable("Source person and address are required", code="source_required")
        if ctx.membership is None or ctx.membership.linked_person_id != body.source_person_id:
            raise Forbidden("Use my address requires a linked profile")
        source = details.get_reusable_address(
            ctx, body.source_person_id, body.source_person_address_id, lock=True
        )
        snapshot = FamilyAddressSnapshot.model_validate(details.address_snapshot(source))
        source_person_address_id = source.id
        immediate_id = source.source_family_address_version_id or source.linked_family_address_version_id
        if immediate_id is not None:
            source_version = _version_by_id(ctx, immediate_id)
            if source_version is None:
                raise NotFound("Address source not found")
            ancestor_version_ids = {source_version.id} | version_ancestor_ids(ctx, source_version.id)
            root_source_version_id = source_version.root_source_version_id or source_version.id

    if snapshot.place_id:
        lookup.get_place(ctx, snapshot.place_id)
    row = FamilyAddress(
        id=uuid7(),
        tree_id=ctx.tree_id,
        label=body.label.strip(),
        controller_membership_id=ctx.membership_id,
        privacy_level=body.privacy_level,
        audience_branch_id=body.audience_branch_id,
        branch_id=body.branch_id,
        household_id=body.household_id,
        property_id=body.property_id,
        place_id=snapshot.place_id,
        ancestral_assertion_id=ancestral_assertion_id,
        current_version=1,
        revision=1,
        sharing_released=(
            body.source_person_id is None
            and root_source_version_id is None
            and source_ancestral_assertion_id is None
        ),
        idempotency_key=body.idempotency_key,
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    ctx.db.add(row)
    ctx.db.flush()
    _make_version(
        ctx,
        row,
        1,
        snapshot,
        source_person_id=body.source_person_id,
        source_person_address_id=source_person_address_id,
        source_ancestral_assertion_id=source_ancestral_assertion_id,
        root_source_version_id=root_source_version_id,
        ancestor_version_ids=ancestor_version_ids,
    )
    ctx.db.flush()
    audit.log(
        ctx,
        "family_address.created",
        target_type="family_address",
        target_id=row.id,
        details={"has_property_reference": body.property_id is not None},
    )
    return row


def list_family_addresses(ctx: TreeContext) -> list[FamilyAddress]:
    rows = ctx.db.scalars(
        select(FamilyAddress)
        .where(FamilyAddress.tree_id == ctx.tree_id, FamilyAddress.retired_at.is_(None))
        .order_by(FamilyAddress.label, FamilyAddress.id)
    ).all()
    return [row for row in rows if version_allows(ctx, _version(ctx, row.id, row.current_version))]


def create_version(
    ctx: TreeContext, family_address_id: uuid.UUID, body: FamilyAddressVersionIn
) -> FamilyAddress:
    row = _family(ctx, family_address_id, lock=True)
    _require_controller(ctx, row)
    if row.retired_at is not None:
        raise Conflict("A retired address cannot be corrected", code="address_retired")
    if row.revision != body.revision:
        raise Conflict("Family address changed since it was loaded", code="stale_revision")
    if body.snapshot.place_id:
        lookup.get_place(ctx, body.snapshot.place_id)
    current = _version(ctx, row.id, row.current_version)
    person_source = ctx.db.scalar(
        select(FamilyAddressVersionSource).where(
            FamilyAddressVersionSource.tree_id == ctx.tree_id,
            FamilyAddressVersionSource.version_id == current.id,
        )
    )
    row.current_version += 1
    row.revision += 1
    row.place_id = body.snapshot.place_id
    row.updated_by = ctx.user_id
    _make_version(
        ctx,
        row,
        row.current_version,
        body.snapshot,
        reason=body.reason,
        source_person_id=person_source.source_person_id if person_source else None,
        source_person_address_id=person_source.source_person_address_id if person_source else None,
        source_ancestral_assertion_id=current.source_ancestral_assertion_id,
        root_source_version_id=current.root_source_version_id,
        ancestor_version_ids=version_ancestor_ids(ctx, current.id),
    )
    ctx.db.flush()
    audit.log(
        ctx,
        "family_address.version_created",
        target_type="family_address",
        target_id=row.id,
        details={"version": row.current_version},
    )
    return row


def list_sources(ctx: TreeContext, *, query: str | None = None) -> list[FamilyAddressSourceOut]:
    items: list[FamilyAddressSourceOut] = []
    for row in list_family_addresses(ctx):
        version = _version(ctx, row.id, row.current_version)
        items.append(
            FamilyAddressSourceOut(
                source_kind="family_address",
                source_id=row.id,
                version=version.version,
                label=row.label,
                group="Branch" if row.branch_id else "Family",
                snapshot=_snapshot(version),
                link_allowed=True,
            )
        )
    assertions = ctx.db.scalars(
        select(Assertion).where(
            Assertion.tree_id == ctx.tree_id,
            Assertion.attribute == HeritageAttribute.ANCESTRAL_VILLAGE.value,
        )
    ).all()
    for assertion in assertions:
        try:
            _assertion, snapshot = _ancestral_snapshot(ctx, assertion.id)
        except NotFound:
            continue
        items.append(
            FamilyAddressSourceOut(
                source_kind="ancestral_assertion",
                source_id=assertion.id,
                label=assertion.value_text or "Ancestral village",
                group="Ancestral",
                snapshot=snapshot,
                link_allowed=False,
            )
        )
    if ctx.membership and ctx.membership.linked_person_id:
        from app.modules.profile_details import service as details

        try:
            mine = details.list_addresses(ctx, ctx.membership.linked_person_id, offset=0, limit=200)
        except Forbidden:
            mine = []
        for address in mine:
            items.append(
                FamilyAddressSourceOut(
                    source_kind="my_address",
                    source_id=address.id,
                    label=address.locality
                    or address.district
                    or address.purpose.value.replace("_", " ").title(),
                    group="My addresses",
                    snapshot=FamilyAddressSnapshot.model_validate(details.address_snapshot(address)),
                    link_allowed=False,
                )
            )
    if query:
        needle = query.casefold().strip()
        items = [
            item
            for item in items
            if needle
            in " ".join(
                str(value or "")
                for value in (
                    item.label,
                    item.snapshot.as_recorded,
                    item.snapshot.locality,
                    item.snapshot.district,
                    item.snapshot.state,
                )
            ).casefold()
        ]
    recent_keys: list[tuple[str, str]] = []
    if ctx.membership_id is not None and ctx.user_id is not None:
        events = ctx.db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.tree_id == ctx.tree_id,
                AuditEvent.actor_user_id == ctx.user_id,
                AuditEvent.action == "family_address.reused",
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        ).all()
        for event in events:
            event_details = event.details or {}
            if event_details.get("membership_id") != str(ctx.membership_id):
                continue
            key = (str(event_details.get("source_kind")), str(event_details.get("source_id")))
            if key not in recent_keys:
                recent_keys.append(key)
            if len(recent_keys) == 8:
                break
    recent_order = {key: index for index, key in enumerate(recent_keys)}
    recent: list[FamilyAddressSourceOut] = []
    other: list[FamilyAddressSourceOut] = []
    for item in items:
        key = (item.source_kind, str(item.source_id))
        if key in recent_order:
            recent.append(item.model_copy(update={"group": "Recent"}))
        else:
            other.append(item)
    recent.sort(key=lambda item: recent_order[(item.source_kind, str(item.source_id))])
    return recent + sorted(other, key=lambda item: (item.group, item.label.casefold(), str(item.source_id)))


def reuse(ctx: TreeContext, person_id: uuid.UUID, body: AddressReuseIn) -> PersonAddress:
    from app.modules.profile_details import service as details

    linked_version = None
    source_version = None
    root_version = None
    ancestral_id = None
    copied_from = None
    if body.source_kind == "family_address":
        family = _family(ctx, body.source_id, lock=True)
        version_number = body.source_version or family.current_version
        version = _version(ctx, family.id, version_number, lock=True)
        if not version_allows(ctx, version):
            raise NotFound("Family address not found")
        snapshot = _snapshot(version)
        root_version = version.root_source_version_id or version.id
        if body.mode == AddressReuseMode.LINK:
            linked_version = version.id
        else:
            source_version = version.id
    elif body.source_kind == "ancestral_assertion":
        _assertion, snapshot = _ancestral_snapshot(ctx, body.source_id)
        ancestral_id = body.source_id
    else:
        if ctx.membership is None or ctx.membership.linked_person_id is None:
            raise Forbidden("Use my address requires a linked profile")
        source = details.get_reusable_address(ctx, ctx.membership.linked_person_id, body.source_id, lock=True)
        snapshot = FamilyAddressSnapshot.model_validate(details.address_snapshot(source))
        copied_from = source.id

    address_body = AddressIn(
        **snapshot.model_dump(),
        purpose=body.purpose,
        status=body.status,
        is_primary_current=body.is_primary_current,
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        idempotency_key=body.idempotency_key,
    )
    row = details.create_address(ctx, person_id, address_body, source=body.source_kind)
    row.reuse_mode = body.mode
    row.linked_family_address_version_id = linked_version
    row.source_family_address_version_id = source_version
    row.root_source_family_address_version_id = root_version
    row.ancestral_assertion_id = ancestral_id
    row.copied_from_person_address_id = copied_from
    row.updated_by = ctx.user_id
    ctx.db.flush()
    audit.log(
        ctx,
        "family_address.reused",
        target_type="person_address",
        target_id=row.id,
        details={
            "membership_id": str(ctx.membership_id),
            "source_kind": body.source_kind,
            "source_id": str(body.source_id),
            "source_version": body.source_version,
        },
    )
    return row


def adopt(
    ctx: TreeContext,
    person_id: uuid.UUID,
    address_id: uuid.UUID,
    body: AdoptFamilyAddressVersionIn,
) -> PersonAddress:
    from app.modules.profile_details import service as details

    row = details.get_reusable_address(ctx, person_id, address_id, lock=True)
    if row.linked_family_address_version_id is None:
        raise Unprocessable("Only a linked family address can adopt a version", code="not_linked")
    old = _version_by_id(ctx, row.linked_family_address_version_id)
    if old is None:
        raise NotFound("Family address version not found")
    target = _version(ctx, old.family_address_id, body.version, lock=True)
    if not version_allows(ctx, target):
        raise NotFound("Family address version not found")
    snapshot = _snapshot(target)
    return details.adopt_family_snapshot(
        ctx,
        person_id,
        address_id,
        expected_revision=body.revision,
        snapshot=snapshot.model_dump(mode="json"),
        linked_version_id=target.id,
        root_version_id=target.root_source_version_id or target.id,
    )


def project_person_address(ctx: TreeContext, row: PersonAddress) -> AddressOut:
    from app.modules.profile_details import service as details

    return details.project_address(row, ctx)


def withdraw_person_address(
    ctx: TreeContext,
    person_id: uuid.UUID,
    address_id: uuid.UUID,
    revision: int,
    reason: str | None,
) -> None:
    """Own the cross-record workflow so derivatives are revoked before source withdrawal."""
    from app.modules.profile_details import service as details

    details.require_address_withdrawal(ctx, person_id, address_id, revision)
    revoke_person_address_source(ctx, address_id)
    details.withdraw_address(ctx, person_id, address_id, revision, reason)


def affected(ctx: TreeContext, family_address_id: uuid.UUID, target_version: int) -> list[AffectedAddressOut]:
    family = _family(ctx, family_address_id)
    _require_controller(ctx, family)
    _version(ctx, family.id, target_version)
    family_version_ids = select(FamilyAddressVersion.id).where(
        FamilyAddressVersion.tree_id == ctx.tree_id,
        FamilyAddressVersion.family_address_id == family.id,
        FamilyAddressVersion.version != target_version,
    )
    rows = ctx.db.execute(
        select(PersonAddress, Person)
        .join(
            Person,
            (Person.tree_id == PersonAddress.tree_id) & (Person.id == PersonAddress.person_id),
        )
        .where(
            PersonAddress.tree_id == ctx.tree_id,
            PersonAddress.linked_family_address_version_id.in_(family_version_ids),
            PersonAddress.withdrawn_at.is_(None),
        )
        .order_by(Person.preferred_display_name, PersonAddress.id)
    ).all()
    visible: list[AffectedAddressOut] = []
    for address, person in rows:
        subject = lookup.get_person_subject(ctx, person.id)
        if not can_view_field(ctx, subject, FieldGroup.ADDRESS):
            continue
        linked_version_id = address.linked_family_address_version_id
        if linked_version_id is None:
            continue
        version = _version_by_id(ctx, linked_version_id)
        if version and address_source_allows(ctx, address):
            visible.append(
                AffectedAddressOut(
                    person_id=person.id,
                    person_name=person.preferred_display_name,
                    address_id=address.id,
                    pinned_version=version.version,
                )
            )
    return visible


def retire(ctx: TreeContext, family_address_id: uuid.UUID, revision: int) -> None:
    row = _family(ctx, family_address_id, lock=True)
    _require_controller(ctx, row)
    if row.revision != revision:
        raise Conflict("Family address changed since it was loaded", code="stale_revision")
    row.retired_at = dt.datetime.now(dt.UTC)
    row.revision += 1
    row.updated_by = ctx.user_id
    audit.log(ctx, "family_address.retired", target_type="family_address", target_id=row.id)


def _descendant_version_ids(ctx: TreeContext, source_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not source_ids:
        return set()
    return source_ids | set(
        ctx.db.scalars(
            select(FamilyAddressVersionAncestor.descendant_version_id).where(
                FamilyAddressVersionAncestor.tree_id == ctx.tree_id,
                FamilyAddressVersionAncestor.ancestor_version_id.in_(source_ids),
            )
        )
    )


def _purge_family_versions(ctx: TreeContext, version_ids: set[uuid.UUID]) -> None:
    if not version_ids:
        return
    versions = ctx.db.scalars(
        select(FamilyAddressVersion).where(
            FamilyAddressVersion.tree_id == ctx.tree_id,
            FamilyAddressVersion.id.in_(version_ids),
        )
    ).all()
    family_ids = {version.family_address_id for version in versions}
    blank = _payload({})
    for version in versions:
        version.place_id = None
        version.locality = None
        version.sub_district = None
        version.district = None
        version.state = None
        version.country_code = None
        version.payload_enc = encrypt_json(blank, _aad(version.id))
        version.source_ancestral_assertion_id = None
        version.reason_enc = None
        version.updated_by = ctx.user_id
    now = dt.datetime.now(dt.UTC)
    families = ctx.db.scalars(
        select(FamilyAddress).where(
            FamilyAddress.tree_id == ctx.tree_id,
            FamilyAddress.id.in_(family_ids),
        )
    ).all()
    for family in families:
        family.label = "Withdrawn address"
        family.privacy_level = RecordPrivacyLevel.ONLY_ME
        family.audience_branch_id = None
        family.branch_id = None
        family.household_id = None
        family.property_id = None
        family.place_id = None
        family.ancestral_assertion_id = None
        family.sharing_released = False
        family.retired_at = family.retired_at or now
        family.revision += 1
        family.updated_by = ctx.user_id
    consents = ctx.db.scalars(
        select(FamilyAddressReleaseConsent).where(
            FamilyAddressReleaseConsent.tree_id == ctx.tree_id,
            (
                FamilyAddressReleaseConsent.source_version_id.in_(version_ids)
                | FamilyAddressReleaseConsent.destination_family_address_id.in_(family_ids)
            ),
            FamilyAddressReleaseConsent.withdrawn_at.is_(None),
        )
    ).all()
    for consent in consents:
        consent.withdrawn_at = now
        consent.updated_by = ctx.user_id


def _revoke_person_source_ids(
    ctx: TreeContext,
    source_address_ids: set[uuid.UUID],
    *,
    source_person_id: uuid.UUID | None = None,
) -> None:
    from app.modules.profile_details import service as details

    conditions = []
    if source_person_id is not None:
        conditions.append(FamilyAddressVersionSource.source_person_id == source_person_id)
    if source_address_ids:
        conditions.append(FamilyAddressVersionSource.source_person_address_id.in_(source_address_ids))
    if not conditions:
        return
    condition = conditions[0]
    for extra in conditions[1:]:
        condition |= extra
    provenance = ctx.db.scalars(
        select(FamilyAddressVersionSource).where(
            FamilyAddressVersionSource.tree_id == ctx.tree_id,
            condition,
        )
    ).all()
    source_versions = {row.version_id for row in provenance}
    impacted_versions = _descendant_version_ids(ctx, source_versions)
    details.purge_reused_address_derivatives(
        ctx,
        source_address_ids=source_address_ids,
        source_family_version_ids=impacted_versions,
    )
    _purge_family_versions(ctx, impacted_versions)
    for row in provenance:
        row.source_person_id = None
        row.source_person_address_id = None
        row.updated_by = ctx.user_id
    ctx.db.flush()


def revoke_person_address_source(ctx: TreeContext, address_id: uuid.UUID) -> None:
    """Withdraw every derivative before a reusable source address is withdrawn."""
    _revoke_person_source_ids(ctx, {address_id})


def revoke_person_sources(ctx: TreeContext, person_id: uuid.UUID) -> None:
    """Apply source-owner erasure to every reusable derivative before profile deletion."""
    source_address_ids = set(
        ctx.db.scalars(
            select(PersonAddress.id).where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.person_id == person_id,
            )
        )
    )
    _revoke_person_source_ids(ctx, source_address_ids, source_person_id=person_id)


def revoke_ancestral_source(ctx: TreeContext, assertion_id: uuid.UUID) -> None:
    """Withdraw all copies when their underlying ancestral assertion is removed."""
    from app.modules.profile_details import service as details

    source_versions = set(
        ctx.db.scalars(
            select(FamilyAddressVersion.id).where(
                FamilyAddressVersion.tree_id == ctx.tree_id,
                FamilyAddressVersion.source_ancestral_assertion_id == assertion_id,
            )
        )
    )
    impacted_versions = _descendant_version_ids(ctx, source_versions)
    details.purge_reused_address_derivatives(
        ctx,
        source_family_version_ids=impacted_versions,
        ancestral_assertion_ids={assertion_id},
    )
    _purge_family_versions(ctx, impacted_versions)
    ctx.db.flush()


def _release_context(
    ctx: TreeContext, family_address_id: uuid.UUID, body: ReleaseConsentIn
) -> tuple[FamilyAddressVersion, FamilyAddress, FamilyAddressVersion, set[uuid.UUID]]:
    source = _family(ctx, family_address_id)
    _require_controller(ctx, source)
    source_version = _version(ctx, source.id, body.source_version)
    destination = _family(ctx, body.destination_family_address_id)
    current = _version(ctx, destination.id, destination.current_version)
    ancestors = version_ancestor_ids(ctx, current.id)
    if source_version.id not in ancestors:
        raise Unprocessable("Destination was not copied from this source", code="source_mismatch")
    if destination.privacy_level != body.permitted_privacy_level:
        raise Unprocessable("Consent audience does not match the destination", code="audience_mismatch")
    if destination.audience_branch_id != body.audience_branch_id:
        raise Unprocessable("Consent branch does not match the destination", code="audience_mismatch")
    return source_version, destination, current, ancestors


def preview_release(
    ctx: TreeContext, family_address_id: uuid.UUID, body: ReleaseConsentIn
) -> ReleasePreviewOut:
    _source_version, destination, current, ancestors = _release_context(ctx, family_address_id, body)
    additional: list[ReleaseReaderOut] = []
    rows = ctx.db.execute(
        select(TreeMembership, User)
        .join(User, User.id == TreeMembership.user_id)
        .where(TreeMembership.tree_id == ctx.tree_id)
        .order_by(User.display_name, TreeMembership.id)
    ).all()
    for membership, user in rows:
        roles = frozenset(Role(role) for role in membership.roles)
        member_ctx = TreeContext(
            db=ctx.db,
            tree=ctx.tree,
            user=user,
            membership=membership,
            roles=roles,
            permissions=permissions_for(roles),
        )
        before = version_allows(member_ctx, current)
        after = family_address_audience_allows(
            member_ctx,
            destination,
            body.permitted_privacy_level,
            body.audience_branch_id,
        )
        if after and not before:
            additional.append(ReleaseReaderOut(membership_id=membership.id, display_name=user.display_name))
    source_versions = ctx.db.scalars(
        select(FamilyAddressVersion).where(
            FamilyAddressVersion.tree_id == ctx.tree_id,
            FamilyAddressVersion.id.in_(ancestors),
        )
    ).all()
    source_families = ctx.db.scalars(
        select(FamilyAddress).where(
            FamilyAddress.tree_id == ctx.tree_id,
            FamilyAddress.id.in_({version.family_address_id for version in source_versions}),
        )
    ).all()
    required = sorted(
        {
            family.controller_membership_id
            for family in source_families
            if family.controller_membership_id is not None
        },
        key=str,
    )
    return ReleasePreviewOut(
        additional_readers=additional,
        required_controller_membership_ids=required,
    )


def give_release_consent(
    ctx: TreeContext, family_address_id: uuid.UUID, body: ReleaseConsentIn
) -> FamilyAddressReleaseConsent:
    source_version, destination, _current, _ancestors = _release_context(ctx, family_address_id, body)
    existing = ctx.db.scalar(
        select(FamilyAddressReleaseConsent).where(
            FamilyAddressReleaseConsent.tree_id == ctx.tree_id,
            FamilyAddressReleaseConsent.source_version_id == source_version.id,
            FamilyAddressReleaseConsent.destination_family_address_id == destination.id,
        )
    )
    if existing:
        existing.consenting_controller_membership_id = ctx.membership_id
        existing.permitted_privacy_level = body.permitted_privacy_level
        existing.audience_branch_id = body.audience_branch_id
        existing.purpose = body.purpose
        existing.notice_version = body.notice_version
        existing.granted_at = dt.datetime.now(dt.UTC)
        existing.withdrawn_at = None
        existing.updated_by = ctx.user_id
        ctx.db.flush()
        return existing
    row = FamilyAddressReleaseConsent(
        id=uuid7(),
        tree_id=ctx.tree_id,
        source_version_id=source_version.id,
        destination_family_address_id=destination.id,
        consenting_controller_membership_id=ctx.membership_id,
        permitted_privacy_level=body.permitted_privacy_level,
        audience_branch_id=body.audience_branch_id,
        purpose=body.purpose,
        notice_version=body.notice_version,
        granted_at=dt.datetime.now(dt.UTC),
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    ctx.db.add(row)
    ctx.db.flush()
    return row


def project_consent(row: FamilyAddressReleaseConsent) -> ReleaseConsentOut:
    return ReleaseConsentOut.model_validate(row)


def activate_sharing(
    ctx: TreeContext, family_address_id: uuid.UUID, body: ActivateSharingIn
) -> FamilyAddress:
    destination = _family(ctx, family_address_id, lock=True)
    _require_controller(ctx, destination)
    if destination.revision != body.revision:
        raise Conflict("Family address changed since it was loaded", code="stale_revision")
    requested_consent = ctx.db.scalar(
        select(FamilyAddressReleaseConsent).where(
            FamilyAddressReleaseConsent.tree_id == ctx.tree_id,
            FamilyAddressReleaseConsent.id == body.consent_id,
            FamilyAddressReleaseConsent.destination_family_address_id == destination.id,
            FamilyAddressReleaseConsent.withdrawn_at.is_(None),
            FamilyAddressReleaseConsent.consenting_controller_membership_id.is_not(None),
        )
    )
    if requested_consent is None:
        raise NotFound("Active release consent not found")
    current = _version(ctx, destination.id, destination.current_version)
    ancestor_ids = version_ancestor_ids(ctx, current.id)
    if requested_consent.source_version_id not in ancestor_ids or not ancestor_ids:
        raise Forbidden("The consent does not cover this copy chain")
    ancestors = ctx.db.scalars(
        select(FamilyAddressVersion).where(
            FamilyAddressVersion.tree_id == ctx.tree_id,
            FamilyAddressVersion.id.in_(ancestor_ids),
        )
    ).all()
    consents = ctx.db.scalars(
        select(FamilyAddressReleaseConsent).where(
            FamilyAddressReleaseConsent.tree_id == ctx.tree_id,
            FamilyAddressReleaseConsent.destination_family_address_id == destination.id,
            FamilyAddressReleaseConsent.source_version_id.in_(ancestor_ids),
            FamilyAddressReleaseConsent.withdrawn_at.is_(None),
            FamilyAddressReleaseConsent.consenting_controller_membership_id.is_not(None),
        )
    ).all()
    by_source = {consent.source_version_id: consent for consent in consents}
    for ancestor in ancestors:
        consent = by_source.get(ancestor.id)
        source_family = _family(ctx, ancestor.family_address_id)
        if (
            consent is None
            or source_family.controller_membership_id != consent.consenting_controller_membership_id
            or consent.permitted_privacy_level != destination.privacy_level
            or consent.audience_branch_id != destination.audience_branch_id
        ):
            raise Forbidden("Every source controller must consent to this exact audience")
    destination.sharing_released = True
    destination.revision += 1
    destination.updated_by = ctx.user_id
    ctx.db.flush()
    return destination


def withdraw_consent(ctx: TreeContext, consent_id: uuid.UUID) -> None:
    consent = ctx.db.scalar(
        select(FamilyAddressReleaseConsent).where(
            FamilyAddressReleaseConsent.tree_id == ctx.tree_id,
            FamilyAddressReleaseConsent.id == consent_id,
        )
    )
    if consent is None:
        raise NotFound("Release consent not found")
    source_version = _version_by_id(ctx, consent.source_version_id)
    if source_version is None:
        raise NotFound("Release consent not found")
    _require_controller(ctx, _family(ctx, source_version.family_address_id))
    consent.withdrawn_at = dt.datetime.now(dt.UTC)
    consent.updated_by = ctx.user_id
    destination = _family(ctx, consent.destination_family_address_id, lock=True)
    if destination.sharing_released:
        destination.sharing_released = False
        destination.revision += 1
        destination.updated_by = ctx.user_id


def list_grants(ctx: TreeContext, family_address_id: uuid.UUID) -> list[FamilyAddressGrantOut]:
    family = _family(ctx, family_address_id)
    _require_controller(ctx, family)
    rows = ctx.db.scalars(
        select(AccessGrant)
        .where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.resource_type == GrantResource.FAMILY_ADDRESS,
            AccessGrant.resource_id == family.id,
            AccessGrant.permission == GrantPermission.VIEW,
        )
        .order_by(AccessGrant.granted_at, AccessGrant.id)
    ).all()
    return [FamilyAddressGrantOut.model_validate(row) for row in rows]


def _invalidate_release_for_audience_change(ctx: TreeContext, family: FamilyAddress) -> None:
    current = _version(ctx, family.id, family.current_version)
    if not version_ancestor_ids(ctx, current.id):
        return
    now = dt.datetime.now(dt.UTC)
    consents = ctx.db.scalars(
        select(FamilyAddressReleaseConsent).where(
            FamilyAddressReleaseConsent.tree_id == ctx.tree_id,
            FamilyAddressReleaseConsent.destination_family_address_id == family.id,
            FamilyAddressReleaseConsent.withdrawn_at.is_(None),
        )
    ).all()
    for consent in consents:
        consent.withdrawn_at = now
        consent.updated_by = ctx.user_id
    if family.sharing_released:
        family.sharing_released = False
        family.revision += 1
        family.updated_by = ctx.user_id


def grant_access(
    ctx: TreeContext, family_address_id: uuid.UUID, body: FamilyAddressGrantIn
) -> FamilyAddressGrantOut:
    family = _family(ctx, family_address_id)
    _require_controller(ctx, family)
    membership = ctx.db.scalar(
        select(TreeMembership).where(
            TreeMembership.tree_id == ctx.tree_id,
            TreeMembership.id == body.membership_id,
        )
    )
    if membership is None:
        raise NotFound("Membership not found")
    grant = ctx.db.scalar(
        select(AccessGrant).where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.membership_id == membership.id,
            AccessGrant.resource_type == GrantResource.FAMILY_ADDRESS,
            AccessGrant.resource_id == family.id,
            AccessGrant.permission == GrantPermission.VIEW,
        )
    )
    if grant is None:
        _invalidate_release_for_audience_change(ctx, family)
        grant = AccessGrant(
            id=uuid7(),
            tree_id=ctx.tree_id,
            membership_id=membership.id,
            user_id=membership.user_id,
            resource_type=GrantResource.FAMILY_ADDRESS,
            resource_id=family.id,
            permission=GrantPermission.VIEW,
            expires_at=body.expires_at,
            granted_at=dt.datetime.now(dt.UTC),
            created_by=ctx.user_id,
            updated_by=ctx.user_id,
        )
        ctx.db.add(grant)
        ctx.db.flush()
    return FamilyAddressGrantOut.model_validate(grant)


def revoke_grant(ctx: TreeContext, family_address_id: uuid.UUID, grant_id: uuid.UUID) -> None:
    family = _family(ctx, family_address_id)
    _require_controller(ctx, family)
    grant = ctx.db.scalar(
        select(AccessGrant).where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.id == grant_id,
            AccessGrant.resource_type == GrantResource.FAMILY_ADDRESS,
            AccessGrant.resource_id == family.id,
        )
    )
    if grant is None:
        raise NotFound("Address grant not found")
    source_version_ids = set(
        ctx.db.scalars(
            select(FamilyAddressVersion.id).where(
                FamilyAddressVersion.tree_id == ctx.tree_id,
                FamilyAddressVersion.family_address_id == family.id,
            )
        )
    )
    descendant_ids = set(
        ctx.db.scalars(
            select(FamilyAddressVersionAncestor.descendant_version_id).where(
                FamilyAddressVersionAncestor.tree_id == ctx.tree_id,
                FamilyAddressVersionAncestor.ancestor_version_id.in_(source_version_ids),
            )
        )
    )
    destination_ids = set(
        ctx.db.scalars(
            select(FamilyAddressVersion.family_address_id).where(
                FamilyAddressVersion.tree_id == ctx.tree_id,
                FamilyAddressVersion.id.in_(descendant_ids),
            )
        )
    )
    destinations = ctx.db.scalars(
        select(FamilyAddress).where(
            FamilyAddress.tree_id == ctx.tree_id,
            FamilyAddress.id.in_(destination_ids),
            FamilyAddress.sharing_released.is_(True),
        )
    ).all()
    for destination in destinations:
        _invalidate_release_for_audience_change(ctx, destination)
    ctx.db.delete(grant)
    ctx._grants = None
