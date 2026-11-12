"""Central authorization policy for reusable address sources (ADR-0031 section 5)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.authz.assertions import assertion_allows
from app.authz.context import TreeContext
from app.authz.privacy import FieldGroup, can_view_field, record_allows
from app.authz.subjects import get_person_subject
from app.core.errors import Forbidden
from app.models import (
    Assertion,
    FamilyAddress,
    FamilyAddressReleaseConsent,
    FamilyAddressVersion,
    FamilyAddressVersionAncestor,
    FamilyAddressVersionSource,
    PersonAddress,
    TreeMembership,
)
from app.models.enums import GrantResource, RecordPrivacyLevel


def family_address_base_allows(ctx: TreeContext, row: FamilyAddress) -> bool:
    return (
        row.retired_at is None
        and row.controller_membership_id is not None
        and record_allows(
            ctx,
            row.privacy_level,
            owner_membership_id=row.controller_membership_id,
            audience_branch_id=row.audience_branch_id,
            grant=(GrantResource.FAMILY_ADDRESS, row.id),
        )
    )


def require_family_address_controller(ctx: TreeContext, row: FamilyAddress) -> None:
    if row.controller_membership_id is None or row.controller_membership_id != ctx.membership_id:
        raise Forbidden("Only the current address controller can change this record")


def family_address_audience_allows(
    ctx: TreeContext,
    row: FamilyAddress,
    level: RecordPrivacyLevel,
    audience_branch_id: uuid.UUID | None,
) -> bool:
    return row.controller_membership_id is not None and record_allows(
        ctx,
        level,
        owner_membership_id=row.controller_membership_id,
        audience_branch_id=audience_branch_id,
        grant=(GrantResource.FAMILY_ADDRESS, row.id),
    )


def version_ancestor_ids(ctx: TreeContext, version_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        ctx.db.scalars(
            select(FamilyAddressVersionAncestor.ancestor_version_id).where(
                FamilyAddressVersionAncestor.tree_id == ctx.tree_id,
                FamilyAddressVersionAncestor.descendant_version_id == version_id,
            )
        )
    )


def family_address_version_allows(ctx: TreeContext, version: FamilyAddressVersion) -> bool:
    family = ctx.db.scalar(
        select(FamilyAddress).where(
            FamilyAddress.tree_id == ctx.tree_id,
            FamilyAddress.id == version.family_address_id,
        )
    )
    if family is None or not family_address_base_allows(ctx, family):
        return False
    ancestor_ids = version_ancestor_ids(ctx, version.id)
    if not ancestor_ids and version.root_source_version_id is not None:
        return False  # malformed legacy/copy row fails closed
    relevant_ids = ancestor_ids | {version.id}
    relevant_versions = ctx.db.scalars(
        select(FamilyAddressVersion).where(
            FamilyAddressVersion.tree_id == ctx.tree_id,
            FamilyAddressVersion.id.in_(relevant_ids),
        )
    ).all()
    if len(relevant_versions) != len(relevant_ids):
        return False
    if not all(_version_source_allows(ctx, item, independent=True) for item in relevant_versions):
        return False
    if not ancestor_ids:
        return family.sharing_released or _version_source_allows(ctx, version, independent=False)
    ancestors = [item for item in relevant_versions if item.id in ancestor_ids]
    family_ids = {ancestor.family_address_id for ancestor in ancestors}
    families = ctx.db.scalars(
        select(FamilyAddress).where(
            FamilyAddress.tree_id == ctx.tree_id,
            FamilyAddress.id.in_(family_ids),
        )
    ).all()
    if len(families) != len(family_ids):
        return False
    if family.sharing_released:
        if any(
            source.retired_at is not None or source.controller_membership_id is None for source in families
        ):
            return False
        if family.controller_membership_id is None or not all(
            record_allows(
                ctx,
                source.privacy_level,
                owner_membership_id=source.controller_membership_id,
                audience_branch_id=source.audience_branch_id,
                grant=(GrantResource.FAMILY_ADDRESS, source.id),
                viewer_membership_id=family.controller_membership_id,
            )
            for source in families
        ):
            return False
        consents = ctx.db.scalars(
            select(FamilyAddressReleaseConsent).where(
                FamilyAddressReleaseConsent.tree_id == ctx.tree_id,
                FamilyAddressReleaseConsent.destination_family_address_id == family.id,
                FamilyAddressReleaseConsent.source_version_id.in_(ancestor_ids),
                FamilyAddressReleaseConsent.withdrawn_at.is_(None),
                FamilyAddressReleaseConsent.consenting_controller_membership_id.is_not(None),
            )
        ).all()
        by_source = {consent.source_version_id: consent for consent in consents}
        families_by_id = {source.id: source for source in families}
        return all(
            (consent := by_source.get(ancestor.id)) is not None
            and families_by_id[ancestor.family_address_id].controller_membership_id
            == consent.consenting_controller_membership_id
            and consent.permitted_privacy_level == family.privacy_level
            and consent.audience_branch_id == family.audience_branch_id
            for ancestor in ancestors
        )
    return all(family_address_base_allows(ctx, source) for source in families) and all(
        _version_source_allows(ctx, item, independent=False) for item in relevant_versions
    )


def _version_source_allows(ctx: TreeContext, version: FamilyAddressVersion, *, independent: bool) -> bool:
    if version.source_ancestral_assertion_id is not None:
        assertion = ctx.db.scalar(
            select(Assertion).where(
                Assertion.tree_id == ctx.tree_id,
                Assertion.id == version.source_ancestral_assertion_id,
            )
        )
        if assertion is None or not assertion_allows(ctx, assertion):
            return False
    return _version_person_source_allows(ctx, version, independent=independent)


def _version_person_source_allows(
    ctx: TreeContext, version: FamilyAddressVersion, *, independent: bool
) -> bool:
    provenance = ctx.db.scalar(
        select(FamilyAddressVersionSource).where(
            FamilyAddressVersionSource.tree_id == ctx.tree_id,
            FamilyAddressVersionSource.version_id == version.id,
        )
    )
    if provenance is None:
        return True
    if provenance.source_person_id is None or provenance.source_person_address_id is None:
        return False
    source = ctx.db.scalar(
        select(PersonAddress).where(
            PersonAddress.tree_id == ctx.tree_id,
            PersonAddress.id == provenance.source_person_address_id,
            PersonAddress.person_id == provenance.source_person_id,
            PersonAddress.withdrawn_at.is_(None),
            PersonAddress.source_revoked_at.is_(None),
        )
    )
    if source is None or not _person_address_provenance_active(ctx, source):
        return False
    family = ctx.db.scalar(
        select(FamilyAddress).where(
            FamilyAddress.tree_id == ctx.tree_id,
            FamilyAddress.id == version.family_address_id,
        )
    )
    controller = (
        ctx.db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == ctx.tree_id,
                TreeMembership.id == family.controller_membership_id,
            )
        )
        if family and family.controller_membership_id
        else None
    )
    if controller is None or controller.linked_person_id != provenance.source_person_id:
        return False
    if independent:
        return True
    subject = get_person_subject(ctx, source.person_id)
    return can_view_field(ctx, subject, FieldGroup.ADDRESS) and person_address_source_allows(ctx, source)


def _person_address_provenance_active(
    ctx: TreeContext, row: PersonAddress, *, seen: set[uuid.UUID] | None = None
) -> bool:
    if row.withdrawn_at is not None or row.source_revoked_at is not None:
        return False
    seen = set(seen or ())
    if row.id in seen:
        return False
    seen.add(row.id)
    version_id = row.linked_family_address_version_id or row.source_family_address_version_id
    if version_id:
        source_version = ctx.db.scalar(
            select(FamilyAddressVersion).where(
                FamilyAddressVersion.tree_id == ctx.tree_id,
                FamilyAddressVersion.id == version_id,
            )
        )
        if source_version is None:
            return False
        source_family = ctx.db.scalar(
            select(FamilyAddress).where(
                FamilyAddress.tree_id == ctx.tree_id,
                FamilyAddress.id == source_version.family_address_id,
            )
        )
        return (
            source_family is not None
            and source_family.retired_at is None
            and source_family.controller_membership_id is not None
        )
    if row.ancestral_assertion_id:
        return (
            ctx.db.scalar(
                select(Assertion.id).where(
                    Assertion.tree_id == ctx.tree_id,
                    Assertion.id == row.ancestral_assertion_id,
                )
            )
            is not None
        )
    if row.copied_from_person_address_id:
        source = ctx.db.scalar(
            select(PersonAddress).where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.id == row.copied_from_person_address_id,
            )
        )
        return source is not None and _person_address_provenance_active(ctx, source, seen=seen)
    if row.reuse_mode is not None or row.source in {
        "family_address",
        "ancestral_assertion",
        "my_address",
    }:
        return False
    return True


def person_address_source_allows(
    ctx: TreeContext, row: PersonAddress, *, _seen: set[uuid.UUID] | None = None
) -> bool:
    if row.source_revoked_at is not None:
        return False
    seen = _seen or set()
    if row.id in seen:
        return False
    seen.add(row.id)
    version_id = row.linked_family_address_version_id or row.source_family_address_version_id
    if version_id:
        version = ctx.db.scalar(
            select(FamilyAddressVersion).where(
                FamilyAddressVersion.tree_id == ctx.tree_id,
                FamilyAddressVersion.id == version_id,
            )
        )
        return version is not None and family_address_version_allows(ctx, version)
    if row.ancestral_assertion_id:
        assertion = ctx.db.scalar(
            select(Assertion).where(
                Assertion.tree_id == ctx.tree_id,
                Assertion.id == row.ancestral_assertion_id,
            )
        )
        return assertion is not None and assertion_allows(ctx, assertion)
    if row.copied_from_person_address_id:
        source = ctx.db.scalar(
            select(PersonAddress).where(
                PersonAddress.tree_id == ctx.tree_id,
                PersonAddress.id == row.copied_from_person_address_id,
                PersonAddress.withdrawn_at.is_(None),
            )
        )
        if source is None:
            return False
        subject = get_person_subject(ctx, source.person_id)
        return can_view_field(ctx, subject, FieldGroup.ADDRESS) and person_address_source_allows(
            ctx, source, _seen=seen
        )
    if row.reuse_mode is not None or row.source in {
        "family_address",
        "ancestral_assertion",
        "my_address",
    }:
        return False  # a missing reuse provenance reference never widens access
    return True
