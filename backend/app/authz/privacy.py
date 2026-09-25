"""Privacy evaluation and field redaction (PRS §6, §30, §32; ADR-0006).

Levels are ordered from most open to most restricted:
PUBLIC_DECEASED_ONLY ⊇ INVITED_RESEARCHER ⊇ TREE_MEMBERS ⊇ FAMILY_BRANCH ⊇ PRIVATE_TREE_ADMINS ⊇
PRIVATE_SELF. CUSTOM = admins + explicit grants.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select

from app.authz.context import TreeContext
from app.core.dates import GenealogicalDate
from app.models import BranchMembership, Event, EventParticipant, Person
from app.models.enums import (
    EventType,
    GrantPermission,
    GrantResource,
    ParticipantRole,
    PrivacyLevel,
    ProfileStatus,
    Role,
)

MINOR_AGE = 18
PRESUMED_DECEASED_AFTER_YEARS = 110


class FieldGroup:
    BIRTH_DATE_FULL = "birth_date_full"
    BIRTH_TIME = "birth_time"
    BIRTH_PLACE_DETAIL = "birth_place_detail"
    CONTACT = "contact"
    ADDRESS = "address"
    GENDER_IDENTITY = "gender_identity"
    COMMUNITY = "community"
    JATI = "jati"
    RELIGION = "religion"
    HERITAGE = "heritage"
    ASTROLOGY = "astrology"
    NOTES = "notes"

    ALL = (
        BIRTH_DATE_FULL,
        BIRTH_TIME,
        BIRTH_PLACE_DETAIL,
        CONTACT,
        ADDRESS,
        GENDER_IDENTITY,
        COMMUNITY,
        JATI,
        RELIGION,
        HERITAGE,
        ASTROLOGY,
        NOTES,
    )


INHERIT = "INHERIT"  # use the person's own privacy level

# Defaults for protected subjects (living / unknown-status / minors): PRS §6 "always restricted".
PROTECTED_DEFAULTS: dict[str, str] = {
    FieldGroup.BIRTH_DATE_FULL: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.BIRTH_TIME: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.BIRTH_PLACE_DETAIL: PrivacyLevel.FAMILY_BRANCH,
    FieldGroup.CONTACT: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.ADDRESS: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.GENDER_IDENTITY: PrivacyLevel.PRIVATE_SELF,
    FieldGroup.COMMUNITY: PrivacyLevel.TREE_MEMBERS,
    FieldGroup.JATI: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.RELIGION: PrivacyLevel.TREE_MEMBERS,
    FieldGroup.HERITAGE: INHERIT,
    FieldGroup.ASTROLOGY: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.NOTES: INHERIT,
}

DECEASED_DEFAULTS: dict[str, str] = {
    FieldGroup.BIRTH_DATE_FULL: INHERIT,
    FieldGroup.BIRTH_TIME: INHERIT,
    FieldGroup.BIRTH_PLACE_DETAIL: INHERIT,
    FieldGroup.CONTACT: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.ADDRESS: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.GENDER_IDENTITY: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.COMMUNITY: INHERIT,
    FieldGroup.JATI: PrivacyLevel.PRIVATE_TREE_ADMINS,
    FieldGroup.RELIGION: INHERIT,
    FieldGroup.HERITAGE: INHERIT,
    FieldGroup.ASTROLOGY: INHERIT,
    FieldGroup.NOTES: INHERIT,
}

# Groups that may appear on a public (deceased-only) page. Everything else is withheld publicly.
PUBLIC_SAFE_GROUPS = frozenset({FieldGroup.BIRTH_DATE_FULL, FieldGroup.HERITAGE})

_RANK = {
    PrivacyLevel.PUBLIC_DECEASED_ONLY: 0,
    PrivacyLevel.INVITED_RESEARCHER: 1,
    PrivacyLevel.TREE_MEMBERS: 2,
    PrivacyLevel.FAMILY_BRANCH: 3,
    PrivacyLevel.PRIVATE_TREE_ADMINS: 4,
    PrivacyLevel.PRIVATE_SELF: 5,
}


@dataclass
class Subject:
    """What privacy evaluation needs to know about a person."""

    person: Person
    birth_date: GenealogicalDate | None = None
    branch_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def id(self) -> uuid.UUID:
        return self.person.id

    def age_years(self, today: dt.date | None = None) -> int | None:
        if self.birth_date is None or self.birth_date.year is None:
            return None
        lo, hi = self.birth_date.sort_range()
        today = today or dt.date.today()
        # the *youngest* possible age decides minor status (be conservative)
        latest_birth = hi or lo
        if latest_birth is None:
            return None
        years = (
            today.year
            - latest_birth.year
            - ((today.month, today.day) < (latest_birth.month, latest_birth.day))
        )
        return max(0, years)

    @property
    def is_minor(self) -> bool:
        if self.person.profile_status == ProfileStatus.DECEASED:
            return False
        age = self.age_years()
        return age is not None and age < MINOR_AGE

    @property
    def is_protected(self) -> bool:
        """Living, unknown-status (unless born >110 years ago) or minor → protected."""
        status = self.person.profile_status
        if status == ProfileStatus.LIVING:
            return True
        if status == ProfileStatus.UNKNOWN:
            age = self.age_years()
            return age is None or age < PRESUMED_DECEASED_AFTER_YEARS
        return False


def load_subjects(ctx: TreeContext, persons: Iterable[Person]) -> dict[uuid.UUID, Subject]:
    """Batch-load birth dates and branch memberships for privacy decisions."""
    persons = list(persons)
    ids = [p.id for p in persons]
    subjects = {p.id: Subject(person=p) for p in persons}
    if not ids:
        return subjects
    rows = ctx.db.execute(
        select(EventParticipant.person_id, Event.date, Event.is_preferred)
        .join(Event, (Event.id == EventParticipant.event_id) & (Event.tree_id == EventParticipant.tree_id))
        .where(
            EventParticipant.tree_id == ctx.tree_id,
            EventParticipant.person_id.in_(ids),
            EventParticipant.role == ParticipantRole.PRINCIPAL,
            Event.type == EventType.BIRTH,
        )
        .order_by(Event.is_preferred.desc())
    ).all()
    for pid, raw_date, _pref in rows:
        s = subjects[pid]
        if s.birth_date is None and raw_date:
            s.birth_date = GenealogicalDate.model_validate(raw_date)
    for pid, bid in ctx.db.execute(
        select(BranchMembership.person_id, BranchMembership.branch_id).where(
            BranchMembership.tree_id == ctx.tree_id, BranchMembership.person_id.in_(ids)
        )
    ).all():
        subjects[pid].branch_ids.add(bid)
    return subjects


def _is_self(ctx: TreeContext, subject: Subject | None) -> bool:
    if subject is None or ctx.user is None:
        return False
    if subject.person.claimed_by_user_id == ctx.user.id:
        return True
    return bool(ctx.membership and ctx.membership.linked_person_id == subject.id)


def level_allows(
    ctx: TreeContext,
    level: PrivacyLevel | str,
    *,
    subject: Subject | None = None,
    grant: tuple[GrantResource, uuid.UUID] | None = None,
) -> bool:
    """Can the viewer see something protected at ``level`` about ``subject``?"""
    level = PrivacyLevel(level)
    if ctx.public:
        return (
            level == PrivacyLevel.PUBLIC_DECEASED_ONLY
            and subject is not None
            and subject.person.profile_status == ProfileStatus.DECEASED
            and not subject.is_protected
            and subject.person.privacy_level == PrivacyLevel.PUBLIC_DECEASED_ONLY
        )
    if not ctx.is_member:
        return False
    if _is_self(ctx, subject):
        return True
    if level == PrivacyLevel.CUSTOM:
        return ctx.is_admin or (grant is not None and ctx.has_grant(grant[0], grant[1], GrantPermission.VIEW))
    if level == PrivacyLevel.PRIVATE_SELF:
        return ctx.is_owner
    if ctx.is_admin:
        return True
    if grant is not None and ctx.has_grant(grant[0], grant[1], GrantPermission.VIEW):
        return True
    if level == PrivacyLevel.PRIVATE_TREE_ADMINS:
        return False
    if level == PrivacyLevel.FAMILY_BRANCH:
        if subject is None:
            return False
        return bool(subject.branch_ids & ctx.viewer_branch_ids())
    if level == PrivacyLevel.TREE_MEMBERS:
        return not ctx.is_researcher_only
    return True  # INVITED_RESEARCHER / PUBLIC_DECEASED_ONLY: any member


def can_view_person(ctx: TreeContext, subject: Subject) -> bool:
    if subject.person.deleted_at is not None:
        return False
    return level_allows(
        ctx, subject.person.privacy_level, subject=subject, grant=(GrantResource.PERSON, subject.id)
    )


def field_level(subject: Subject, group: str) -> PrivacyLevel:
    override = (subject.person.field_privacy or {}).get(group)
    if override:
        return PrivacyLevel(override)
    defaults = PROTECTED_DEFAULTS if subject.is_protected else DECEASED_DEFAULTS
    value = defaults[group]
    if value == INHERIT:
        return PrivacyLevel(subject.person.privacy_level)
    # never *less* private than the person as a whole
    level = PrivacyLevel(value)
    person_level = PrivacyLevel(subject.person.privacy_level)
    if person_level in _RANK and level in _RANK and _RANK[person_level] > _RANK[level]:
        return person_level
    return level


def can_view_field(ctx: TreeContext, subject: Subject, group: str) -> bool:
    if ctx.public:
        return (
            group in PUBLIC_SAFE_GROUPS
            and group != FieldGroup.BIRTH_DATE_FULL
            and can_view_person(ctx, subject)
        )
    return level_allows(
        ctx, field_level(subject, group), subject=subject, grant=(GrantResource.PERSON, subject.id)
    )


def visible_field_groups(ctx: TreeContext, subject: Subject) -> set[str]:
    return {g for g in FieldGroup.ALL if can_view_field(ctx, subject, g)}


def roles_can_manage_privacy(roles: frozenset[Role]) -> bool:
    return bool(roles & {Role.OWNER, Role.FAMILY_ADMIN})
