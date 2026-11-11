"""Visibility & Sharing for any shareable record (ADR-0027).

The rules are the same for every record type; each type supplies a ``RecordAdapter`` that says how
to evaluate its access rules against a proposed setting and how to store one.

* **Ceiling (§5).** A record is never more open than any *protected* person linked to it allows: a
  private person caps it at Selected members, a branch-private person at their branch, anyone else
  at All family members. Linking such a person, or making them more private, narrows it at once.
* **Audience (§9).** "Who has access" is computed here, on the server, by evaluating the real access
  rules for every membership of the tree against the current or the proposed settings.
* **Changes (§10).** The owner may change anything up to the ceiling. Anyone else allowed to manage
  the record may only narrow one that is not private (the new viewers and downloaders are a subset
  of the old ones). Widening needs ``confirm_wider``.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import permissions_for
from app.authz.privacy import RECORD_RANK, Subject, is_private_record_level, is_record_owner, load_subjects
from app.core import audit
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models import AccessGrant, FamilyBranch, Person, TreeMembership, User, UserNotification
from app.models.enums import (
    GrantPermission,
    GrantResource,
    NotificationKind,
    PrivacyLevel,
    RecordPrivacyLevel,
    Role,
)
from app.modules.sharing.schemas import (
    SharingCeilingOut,
    SharingMemberIn,
    SharingMemberOut,
    SharingOut,
    SharingUpdate,
)

L = RecordPrivacyLevel
# Audiences a member may choose for a record (ADR-0027 §1; no public records in v1).
CHOOSABLE = frozenset({L.ONLY_ME, L.SELECTED_MEMBERS, L.FAMILY_BRANCH, L.TREE_MEMBERS})


# ---------------------------------------------------------------- ceilings (§5)
@dataclass(frozen=True)
class Cap:
    level: RecordPrivacyLevel
    branches: frozenset[uuid.UUID] = frozenset()


def person_cap(subject: Subject) -> Cap | None:
    """The widest audience a record about ``subject`` may have, or None (deceased: no cap)."""
    if not subject.is_protected:
        return None
    level = PrivacyLevel(subject.person.privacy_level)
    if level in (PrivacyLevel.PRIVATE_SELF, PrivacyLevel.PRIVATE_TREE_ADMINS, PrivacyLevel.CUSTOM):
        return Cap(L.SELECTED_MEMBERS)
    if level == PrivacyLevel.FAMILY_BRANCH:
        if not subject.branch_ids:
            return Cap(L.SELECTED_MEMBERS)
        return Cap(L.FAMILY_BRANCH, frozenset(subject.branch_ids))
    return Cap(L.TREE_MEMBERS)


def caps_for_people(ctx: TreeContext, person_ids: list[uuid.UUID]) -> list[Cap]:
    if not person_ids:
        return []
    persons = ctx.db.scalars(
        select(Person).where(
            Person.tree_id == ctx.tree_id, Person.id.in_(person_ids), Person.deleted_at.is_(None)
        )
    ).all()
    caps = [person_cap(s) for s in load_subjects(ctx, persons).values()]
    return [c for c in caps if c is not None]


def event_cap(ctx: TreeContext, event: Any) -> Cap | None:
    """The widest audience a photo in ``event``'s album may have (ADR-0027 §5.3, ADR-0015): the
    event's own level, or None when the event has none (it then follows its people)."""
    if event.privacy_level is None:
        return None
    level = PrivacyLevel(event.privacy_level)
    if level in (PrivacyLevel.PRIVATE_SELF, PrivacyLevel.PRIVATE_TREE_ADMINS, PrivacyLevel.CUSTOM):
        return Cap(L.SELECTED_MEMBERS)
    if level == PrivacyLevel.FAMILY_BRANCH:
        from app.models import EventParticipant
        from app.models.enums import ParticipantRole

        principals = list(
            ctx.db.scalars(
                select(EventParticipant.person_id).where(
                    EventParticipant.tree_id == ctx.tree_id,
                    EventParticipant.event_id == event.id,
                    EventParticipant.role == ParticipantRole.PRINCIPAL,
                )
            )
        )
        persons = ctx.db.scalars(
            select(Person).where(Person.tree_id == ctx.tree_id, Person.id.in_(principals))
        ).all()
        branches = frozenset(b for s in load_subjects(ctx, persons).values() for b in s.branch_ids)
        return Cap(L.FAMILY_BRANCH, branches) if branches else Cap(L.SELECTED_MEMBERS)
    return Cap(L.TREE_MEMBERS)


def within(level: RecordPrivacyLevel | str, branch: uuid.UUID | None, caps: list[Cap]) -> bool:
    level = L(level)
    for cap in caps:
        rank, cap_rank = RECORD_RANK[level], RECORD_RANK[cap.level]
        if rank < cap_rank:
            return False
        if (
            rank == cap_rank
            and cap.level == L.FAMILY_BRANCH
            and level == L.FAMILY_BRANCH
            and branch is not None
            and branch not in cap.branches
        ):
            return False
    return True


def _common_branches(caps: list[Cap]) -> frozenset[uuid.UUID]:
    branch_caps = [c.branches for c in caps if c.level == L.FAMILY_BRANCH]
    return frozenset.intersection(*branch_caps) if branch_caps else frozenset()


def narrowest(caps: list[Cap]) -> tuple[RecordPrivacyLevel, uuid.UUID | None]:
    """The most open setting every cap allows (used to narrow a record that is now too open)."""
    strictest = max(caps, key=lambda c: RECORD_RANK[c.level])
    if strictest.level == L.FAMILY_BRANCH:
        common = _common_branches(caps)
        if not common:
            return L.SELECTED_MEMBERS, None
        return L.FAMILY_BRANCH, min(common, key=str)
    return strictest.level, None


def ceiling_out(caps: list[Cap]) -> SharingCeilingOut | None:
    if not caps:
        return None
    level, _ = narrowest(caps)
    branches = sorted(_common_branches(caps), key=str) if level == L.FAMILY_BRANCH else []
    return SharingCeilingOut(max_level=level, branch_ids=branches)


# ---------------------------------------------------------------- the record adapter
@dataclass
class Proposal:
    privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None
    allow_download: bool
    members: dict[uuid.UUID, bool] = field(default_factory=dict)  # membership → can download


class RecordAdapter(ABC):
    """How one record type plugs into the shared rules."""

    resource: GrantResource
    audit_type: str
    supports_download: bool = True
    # the owner is told when the record is narrowed automatically (ADR-0027 §5); None = never narrowed
    narrowed_notice: NotificationKind | None = None

    def __init__(self, record: Any) -> None:
        self.record = record

    @property
    def id(self) -> uuid.UUID:
        return self.record.id  # type: ignore[no-any-return]

    @property
    def owner_membership_id(self) -> uuid.UUID | None:
        return self.record.owner_membership_id  # type: ignore[no-any-return]

    @property
    def level(self) -> RecordPrivacyLevel:
        return L(self.record.privacy_level)

    @abstractmethod
    def audience_branch(self) -> uuid.UUID | None: ...

    @abstractmethod
    def allow_download(self) -> bool: ...

    @abstractmethod
    def linked_people(self, ctx: TreeContext) -> list[uuid.UUID]: ...

    def extra_caps(self, ctx: TreeContext) -> list[Cap]:
        """Ceilings other than linked people (e.g. the event of an album photo)."""
        return []

    def caps(self, ctx: TreeContext) -> list[Cap]:
        return caps_for_people(ctx, self.linked_people(ctx)) + self.extra_caps(ctx)

    @abstractmethod
    def can_view(self, mctx: TreeContext, p: Proposal) -> bool:
        """Would ``mctx`` see the record with settings ``p``? (``mctx`` carries the proposed grants)"""

    def can_download(self, mctx: TreeContext, p: Proposal) -> bool:
        return self.can_view(mctx, p)

    @abstractmethod
    def manager_may_narrow(self, ctx: TreeContext) -> bool:
        """May a non-owner with this context narrow the record (when it is not private)?"""

    @abstractmethod
    def store(self, ctx: TreeContext, p: Proposal) -> None:
        """Write the level, branch and download switch onto the record."""

    def is_owner(self, ctx: TreeContext) -> bool:
        return is_record_owner(ctx, self.owner_membership_id)

    def can_edit(self, ctx: TreeContext) -> bool:
        if self.is_owner(ctx):
            return True
        return not is_private_record_level(self.level) and self.manager_may_narrow(ctx)

    def current(self, ctx: TreeContext) -> Proposal:
        members: dict[uuid.UUID, bool] = {}
        for g in ctx.db.scalars(
            select(AccessGrant).where(
                AccessGrant.tree_id == ctx.tree_id,
                AccessGrant.resource_type == self.resource,
                AccessGrant.resource_id == self.id,
            )
        ):
            members[g.membership_id] = members.get(g.membership_id, False) or (
                g.permission == GrantPermission.DOWNLOAD
            )
        return Proposal(self.level, self.audience_branch(), self.allow_download(), members)


# ---------------------------------------------------------------- who has access (§9)
@dataclass
class Audience:
    viewers: dict[uuid.UUID, str]  # membership → how they get access
    downloaders: set[uuid.UUID]


@dataclass
class _Stub:
    id: uuid.UUID


def audience(ctx: TreeContext, rec: RecordAdapter, p: Proposal) -> Audience:
    memberships = ctx.db.scalars(select(TreeMembership).where(TreeMembership.tree_id == ctx.tree_id)).all()
    viewers: dict[uuid.UUID, str] = {}
    downloaders: set[uuid.UUID] = set()
    for m in memberships:
        roles = frozenset(Role(r) for r in m.roles)
        mctx = TreeContext(
            db=ctx.db, tree=ctx.tree, user=None, membership=m, roles=roles, permissions=permissions_for(roles)
        )
        # this member's grants on this record, as proposed (other grants do not matter here)
        mctx._grants = {}
        if m.id in p.members:
            perms = {GrantPermission.VIEW.value}
            if p.members[m.id]:
                perms.add(GrantPermission.DOWNLOAD.value)
            mctx._grants[(rec.resource.value, rec.id)] = perms
        mctx.user = _Stub(m.user_id)  # type: ignore[assignment]  # has_grant only needs a user present
        if not rec.can_view(mctx, p):
            continue
        if rec.is_owner(mctx):
            viewers[m.id] = "owner"
        elif m.id in p.members:
            viewers[m.id] = "selected"
        elif p.privacy_level == L.FAMILY_BRANCH and p.audience_branch_id in mctx.viewer_branch_ids():
            viewers[m.id] = "branch"
        elif p.privacy_level in (L.TREE_MEMBERS, L.INVITED_RESEARCHER, L.PUBLIC_DECEASED_ONLY):
            viewers[m.id] = "family"
        else:
            viewers[m.id] = "role"  # e.g. family admins on a branch record, custodians on legacy ones
        if rec.supports_download and rec.can_download(mctx, p):
            downloaders.add(m.id)
    return Audience(viewers, downloaders)


def sharing_out(ctx: TreeContext, rec: RecordAdapter, p: Proposal | None = None) -> SharingOut:
    p = p or rec.current(ctx)
    editable = rec.can_edit(ctx)
    owner = rec.is_owner(ctx)
    caps = rec.caps(ctx)
    members: list[SharingMemberOut] = []
    people: list[SharingMemberOut] = []
    if editable:
        aud = audience(ctx, rec, p)
        names = dict(
            ctx.db.execute(
                select(TreeMembership.id, User.display_name)
                .join(User, User.id == TreeMembership.user_id)
                .where(TreeMembership.tree_id == ctx.tree_id)
            ).all()
        )
        people = [
            SharingMemberOut(
                membership_id=mid,
                display_name=names.get(mid, ""),
                access=how,
                can_download=mid in aud.downloaders,
            )
            for mid, how in sorted(aud.viewers.items(), key=lambda kv: names.get(kv[0], "").lower())
        ]
        if owner or not is_private_record_level(rec.level):
            members = [
                SharingMemberOut(
                    membership_id=mid, display_name=names.get(mid, ""), access="selected", can_download=dl
                )
                for mid, dl in p.members.items()
            ]
    return SharingOut(
        privacy_level=p.privacy_level,
        audience_branch_id=p.audience_branch_id,
        allow_download=p.allow_download,
        is_owner=owner,
        has_owner=rec.owner_membership_id is not None,
        can_edit=editable,
        can_widen=owner,
        legacy=rec.level in (L.CUSTOM, L.PRIVATE_SELF),
        ceiling=ceiling_out(caps),
        members=members,
        audience=people,
    )


# ---------------------------------------------------------------- change (§10)
def proposal(ctx: TreeContext, rec: RecordAdapter, body: SharingUpdate) -> Proposal:
    level = L(body.privacy_level)
    if level == L.PUBLIC_DECEASED_ONLY:
        raise Unprocessable("Records cannot be public", code="public_not_supported")
    if level not in CHOOSABLE and level != rec.level:
        raise Unprocessable(
            "Choose Only me, Selected members, Selected branch or All family members", code="legacy_level"
        )
    branch = body.audience_branch_id if level == L.FAMILY_BRANCH else None
    if level == L.FAMILY_BRANCH and level == rec.level and branch is None:
        branch = rec.audience_branch()  # unchanged "Selected branch": keep its branch
    if level == L.FAMILY_BRANCH and level != rec.level and branch is None:
        raise Unprocessable("Choose the family branch to share with", code="branch_required")
    if branch is not None and (
        ctx.db.scalar(
            select(FamilyBranch.id).where(FamilyBranch.tree_id == ctx.tree_id, FamilyBranch.id == branch)
        )
        is None
    ):
        raise NotFound("Branch not found")
    members = _members(ctx, rec, body.members)
    if level == L.ONLY_ME and members:
        raise Unprocessable("A record kept for you only cannot be shared with members", code="only_me_record")
    if level == L.SELECTED_MEMBERS and not members:
        raise Unprocessable("Choose at least one member", code="members_required")
    allow_download = body.allow_download if rec.supports_download else False
    return Proposal(level, branch, allow_download, members)


def _members(ctx: TreeContext, rec: RecordAdapter, rows: list[SharingMemberIn]) -> dict[uuid.UUID, bool]:
    ids = {r.membership_id for r in rows}
    if not ids:
        return {}
    found = set(
        ctx.db.scalars(
            select(TreeMembership.id).where(TreeMembership.tree_id == ctx.tree_id, TreeMembership.id.in_(ids))
        )
    )
    if found != ids:
        raise NotFound("Member not found")  # never a membership of another tree (no cross-tree grants)
    out = {r.membership_id: (r.can_download and rec.supports_download) for r in rows}
    if rec.owner_membership_id is not None:
        out.pop(rec.owner_membership_id, None)  # the owner needs no grant
    return out


def require_editable(ctx: TreeContext, rec: RecordAdapter) -> None:
    if not rec.can_edit(ctx):
        raise Forbidden("You cannot change who can see this record")


def apply(ctx: TreeContext, rec: RecordAdapter, new: Proposal, *, confirm_wider: bool) -> None:
    caps = rec.caps(ctx)
    if not within(new.privacy_level, new.audience_branch_id, caps):
        raise Unprocessable(
            "A person tagged in this record is kept more private; it cannot be shared this widely",
            code="privacy_too_open",
            details={"ceiling": c.model_dump(mode="json") if (c := ceiling_out(caps)) else None},
        )
    old = rec.current(ctx)
    before, after = audience(ctx, rec, old), audience(ctx, rec, new)
    added = set(after.viewers) - set(before.viewers)
    added_dl = after.downloaders - before.downloaders
    # widening = anyone new can see or download; narrowing is open to managers (ADR-0027 §10)
    if not rec.is_owner(ctx) and (added or added_dl):
        raise Forbidden("Only the record's owner can share it more widely", code="owner_only_widening")
    if (added or added_dl) and not confirm_wider:
        raise Conflict(
            "This change lets more people see or download the record; confirm to continue",
            code="confirm_wider",
            details={"viewers_added": len(added), "downloaders_added": len(added_dl)},
        )
    rec.store(ctx, new)
    replace_grants(ctx, rec, old.members, new.members)
    ctx.db.flush()
    ctx._grants = None  # the caller's own cached grants may have changed
    if (old.privacy_level, old.audience_branch_id, old.allow_download, old.members) != (
        new.privacy_level,
        new.audience_branch_id,
        new.allow_download,
        new.members,
    ):
        audit.log(
            ctx,
            "record.visibility_changed",
            target_type=rec.audit_type,
            target_id=rec.id,
            details={
                "from": old.privacy_level.value,
                "to": new.privacy_level.value,
                "allow_download": new.allow_download,
                "members": len(new.members),
                "viewers_added": len(added),
                "viewers_removed": len(set(before.viewers) - set(after.viewers)),
                "downloaders_added": len(added_dl),
                "downloaders_removed": len(before.downloaders - after.downloaders),
            },
        )


def enforce_ceiling(ctx: TreeContext, rec: RecordAdapter, *, reason: str) -> bool:
    """Narrow the record if a linked protected person no longer allows its audience. Audited."""
    caps = rec.caps(ctx)
    if not caps or within(rec.level, rec.audience_branch(), caps):
        return False
    old = rec.level
    level, branch = narrowest(caps)
    rec.store(ctx, Proposal(level, branch, False if level == L.SELECTED_MEMBERS else rec.allow_download()))
    ctx.db.flush()
    audit.log(
        ctx,
        "record.visibility_changed",
        target_type=rec.audit_type,
        target_id=rec.id,
        details={"from": old.value, "to": level.value, "reason": reason},
    )
    _tell_owner(ctx, rec)
    return True


def _tell_owner(ctx: TreeContext, rec: RecordAdapter) -> None:
    """Tell the owner their record was made more private (ADR-0027 §5). Ids and a kind only; the
    actor is never named (it may be a person asking to be removed, or a system job). One unread
    notice per record is enough."""
    if rec.narrowed_notice is None or rec.owner_membership_id is None:
        return
    owner = ctx.db.get(TreeMembership, rec.owner_membership_id)
    if owner is None or owner.tree_id != ctx.tree_id or owner.user_id == ctx.user_id:
        return  # the owner left, or narrowed it themselves
    unread = ctx.db.scalar(
        select(UserNotification.id).where(
            UserNotification.tree_id == ctx.tree_id,
            UserNotification.user_id == owner.user_id,
            UserNotification.kind == rec.narrowed_notice,
            UserNotification.subject_id == rec.id,
            UserNotification.read_at.is_(None),
        )
    )
    if unread is None:
        ctx.db.add(
            UserNotification(
                tree_id=ctx.tree_id,
                user_id=owner.user_id,
                kind=rec.narrowed_notice,
                subject_id=rec.id,
                created_by=ctx.user_id,
            )
        )


def replace_grants(
    ctx: TreeContext, rec: RecordAdapter, old: dict[uuid.UUID, bool], new: dict[uuid.UUID, bool]
) -> None:
    if old == new:
        return
    users = dict(
        ctx.db.execute(
            select(TreeMembership.id, TreeMembership.user_id).where(
                TreeMembership.tree_id == ctx.tree_id, TreeMembership.id.in_(set(new) | set(old))
            )
        ).all()
    )
    wanted = {
        (mid, perm)
        for mid, dl in new.items()
        for perm in ({GrantPermission.VIEW, GrantPermission.DOWNLOAD} if dl else {GrantPermission.VIEW})
    }
    existing: set[tuple[uuid.UUID, GrantPermission]] = set()
    for g in ctx.db.scalars(
        select(AccessGrant).where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.resource_type == rec.resource,
            AccessGrant.resource_id == rec.id,
        )
    ):
        key = (g.membership_id, GrantPermission(g.permission))
        if key in wanted:
            existing.add(key)
        else:
            ctx.db.delete(g)
    ctx.db.flush()
    for mid, perm in sorted(wanted - existing, key=lambda k: (str(k[0]), k[1].value)):
        ctx.db.add(
            AccessGrant(
                tree_id=ctx.tree_id,
                user_id=users[mid],
                membership_id=mid,
                resource_type=rec.resource,
                resource_id=rec.id,
                permission=perm,
                created_by=ctx.user_id,
            )
        )


def enforce_event_ceiling(ctx: TreeContext, event_id: uuid.UUID) -> int:
    """After an event's privacy changed: narrow every photo in its album that is now too open."""
    from app.modules.documents.sharing import records_in_album

    return sum(enforce_ceiling(ctx, r, reason="event_privacy") for r in records_in_album(ctx, event_id))


# ---------------------------------------------------------------- person privacy → every linked record
def enforce_person_ceiling(ctx: TreeContext, person_id: uuid.UUID) -> int:
    """After a person's privacy changed: narrow every record linked to them that is now too open."""
    from app.modules.documents.sharing import records_linked_to as document_records
    from app.modules.traditions.sharing import records_linked_to as tradition_records

    recs = [*document_records(ctx, person_id), *tradition_records(ctx, person_id)]
    return sum(enforce_ceiling(ctx, r, reason="person_privacy") for r in recs)
