"""Central visibility policy for heritage assertions."""

from __future__ import annotations

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import FieldGroup, Subject, can_view_field, level_allows
from app.authz.subjects import get_person_subject
from app.core.errors import NotFound
from app.models import Assertion, FamilyBranch
from app.models.enums import AssertionSubject, HeritageAttribute, PrivacyLevel

ATTRIBUTE_GROUP = {
    HeritageAttribute.JATI_OR_SUBGROUP.value: FieldGroup.JATI,
    HeritageAttribute.COMMUNITY.value: FieldGroup.COMMUNITY,
    HeritageAttribute.RELIGION.value: FieldGroup.RELIGION,
}


def assertion_subject(ctx: TreeContext, assertion: Assertion) -> Subject | None:
    if assertion.subject_type == AssertionSubject.PERSON:
        if assertion.person_id is None:
            raise NotFound("Assertion not found")
        return get_person_subject(ctx, assertion.person_id)
    if assertion.branch_id is None or not ctx.db.scalar(
        select(FamilyBranch.id).where(
            FamilyBranch.tree_id == ctx.tree_id,
            FamilyBranch.id == assertion.branch_id,
        )
    ):
        raise NotFound("Assertion not found")
    return None


def assertion_allows(ctx: TreeContext, assertion: Assertion, subject: Subject | None = None) -> bool:
    """Apply the assertion's subject-field and explicit privacy ceilings."""
    if assertion.tree_id != ctx.tree_id:
        return False
    try:
        subject = assertion_subject(ctx, assertion) if subject is None else subject
    except NotFound:
        return False
    group = ATTRIBUTE_GROUP.get(assertion.attribute, FieldGroup.HERITAGE)
    if subject is not None:
        return can_view_field(ctx, subject, group) and (
            assertion.privacy_level is None or level_allows(ctx, assertion.privacy_level, subject=subject)
        )
    if assertion.attribute in ATTRIBUTE_GROUP:
        default = (
            PrivacyLevel.PRIVATE_TREE_ADMINS
            if assertion.attribute == HeritageAttribute.JATI_OR_SUBGROUP.value
            else PrivacyLevel.TREE_MEMBERS
        )
    else:
        default = PrivacyLevel.TREE_MEMBERS
    return level_allows(ctx, assertion.privacy_level or default)
