"""Visibility & Sharing for documents (ADR-0027).

* **Ceiling (§5).** A record is never more open than any *protected* person linked to it allows:
  a private person caps it at Selected members, a branch-private person at their branch, anyone
  else at All family members. Linking such a person, or making them more private, narrows the
  record at once (never widens it).
* **Audience (§9).** "Who has access" is computed here, on the server, by evaluating the real access
  rules for every membership of the tree against the current or the proposed settings.
* **Changes (§10).** The owner may change anything up to the ceiling. Anyone else who can manage
  documents may only narrow a record that is not private (the new viewers and downloaders are a
  subset of the old ones). Widening needs ``confirm_wider``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission, permissions_for
from app.authz.privacy import RECORD_RANK, Subject, is_private_record_level, load_subjects
from app.core import audit
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models import AccessGrant, Document, DocumentLink, FamilyBranch, Person, TreeMembership, User
from app.models.enums import (
    DocumentLinkTarget,
    GrantPermission,
    GrantResource,
    PrivacyLevel,
    RecordPrivacyLevel,
    Role,
)
from app.modules.documents import access
from app.modules.documents.schemas import (
    SharingCeilingOut,
    SharingMemberIn,
    SharingMemberOut,
    SharingOut,
    SharingUpdate,
)

L = RecordPrivacyLevel
# Audiences a member may choose for a record (ADR-0027 §1; no public records in v1).
CHOOSABLE = frozenset({L.ONLY_ME, L.SELECTED_MEMBERS, L.FAMILY_BRANCH, L.TREE_MEMBERS})
LEGACY = frozenset({L.CUSTOM, L.PRIVATE_SELF, L.PRIVATE_TREE_ADMINS, L.INVITED_RESEARCHER})


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


def linked_people(ctx: TreeContext, doc_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        ctx.db.scalars(
            select(DocumentLink.target_id).where(
                DocumentLink.tree_id == ctx.tree_id,
                DocumentLink.document_id == doc_id,
                DocumentLink.target_type == DocumentLinkTarget.PERSON,
            )
        )
    )


def within(level: RecordPrivacyLevel | str, branch: uuid.UUID | None, caps: list[Cap]) -> bool:
    level = L(level)
    for cap in caps:
        rank, cap_rank = RECORD_RANK[level], RECORD_RANK[cap.level]
        if rank < cap_rank:
            return False
        if rank == cap_rank and cap.level == L.FAMILY_BRANCH and level == L.FAMILY_BRANCH:
            if branch is not None and branch not in cap.branches:
                return False
    return True


def narrowest(caps: list[Cap]) -> tuple[RecordPrivacyLevel, uuid.UUID | None]:
    """The most open setting every cap allows (used to narrow a record that is now too open)."""
    strictest = max(caps, key=lambda c: RECORD_RANK[c.level])
    if strictest.level == L.FAMILY_BRANCH:
        common = frozenset.intersection(*[c.branches for c in caps if c.level == L.FAMILY_BRANCH])
        if not common:
            return L.SELECTED_MEMBERS, None
        return L.FAMILY_BRANCH, min(common)
    return strictest.level, None


def ceiling_out(caps: list[Cap]) -> SharingCeilingOut | None:
    if not caps:
        return None
    level, _ = narrowest(caps)
    branches: list[uuid.UUID] = []
    if level == L.FAMILY_BRANCH:
        branches = sorted(frozenset.intersection(*[c.branches for c in caps if c.level == L.FAMILY_BRANCH]))
    return SharingCeilingOut(max_level=level, branch_ids=branches)


def enforce_ceiling(ctx: TreeContext, doc: Document, *, reason: str) -> bool:
    """Narrow ``doc`` if a linked protected person no longer allows its audience. Audited."""
    caps = caps_for_people(ctx, linked_people(ctx, doc.id))
    if not caps or within(doc.privacy_level, doc.audience_branch_id, caps):
        return False
    old = L(doc.privacy_level)
    doc.privacy_level, doc.audience_branch_id = narrowest(caps)
    if doc.privacy_level == L.SELECTED_MEMBERS:
        doc.allow_download = False
    ctx.db.flush()
    audit.log(
        ctx,
        "record.visibility_changed",
        target_type="document",
        target_id=doc.id,
        details={"from": old.value, "to": L(doc.privacy_level).value, "reason": reason},
    )
    return True


def enforce_person_ceiling(ctx: TreeContext, person_id: uuid.UUID) -> int:
    """After a person's privacy changed: narrow every record linked to them that is now too open."""
    docs = ctx.db.scalars(
        select(Document).where(
            Document.tree_id == ctx.tree_id,
            Document.id.in_(
                select(DocumentLink.document_id).where(
                    DocumentLink.tree_id == ctx.tree_id,
                    DocumentLink.target_type == DocumentLinkTarget.PERSON,
                    DocumentLink.target_id == person_id,
                )
            ),
        )
    ).all()
    return sum(enforce_ceiling(ctx, d, reason="person_privacy") for d in docs)


# ---------------------------------------------------------------- who has access (§9)
@dataclass
class Proposal:
    privacy_level: RecordPrivacyLevel
    audience_branch_id: uuid.UUID | None
    allow_download: bool
    members: dict[uuid.UUID, bool] = field(default_factory=dict)  # membership → can download


def _current(ctx: TreeContext, doc: Document) -> Proposal:
    members: dict[uuid.UUID, bool] = {}
    for g in ctx.db.scalars(
        select(AccessGrant).where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.resource_type == GrantResource.DOCUMENT,
            AccessGrant.resource_id == doc.id,
        )
    ):
        members[g.membership_id] = members.get(g.membership_id, False) or (
            g.permission == GrantPermission.DOWNLOAD
        )
    return Proposal(L(doc.privacy_level), doc.audience_branch_id, doc.allow_download, members)


def _as_document(doc: Document, p: Proposal) -> Document:
    """An unsaved copy of ``doc`` carrying the proposed settings, for evaluation only."""
    return Document(
        id=doc.id,
        tree_id=doc.tree_id,
        category=doc.category,
        storage_class=doc.storage_class,
        privacy_level=p.privacy_level,
        owner_membership_id=doc.owner_membership_id,
        audience_branch_id=p.audience_branch_id,
        allow_download=p.allow_download,
        created_by=doc.created_by,
    )


@dataclass
class Audience:
    viewers: dict[uuid.UUID, str]  # membership → how they get access
    downloaders: set[uuid.UUID]


def audience(ctx: TreeContext, doc: Document, p: Proposal) -> Audience:
    copy = _as_document(doc, p)
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
            mctx._grants[(GrantResource.DOCUMENT.value, doc.id)] = perms
        mctx.user = _Stub(m.user_id)  # type: ignore[assignment]  # has_grant only needs a user present
        if not access.can_view_document(mctx, copy):
            continue
        if access.is_owner(mctx, copy):
            viewers[m.id] = "owner"
        elif m.id in p.members:
            viewers[m.id] = "selected"
        elif p.privacy_level == L.FAMILY_BRANCH and p.audience_branch_id in mctx.viewer_branch_ids():
            viewers[m.id] = "branch"
        elif p.privacy_level in (L.TREE_MEMBERS, L.INVITED_RESEARCHER, L.PUBLIC_DECEASED_ONLY):
            viewers[m.id] = "family"
        else:
            viewers[m.id] = "role"  # e.g. family admins on a branch record, custodians on legacy ones
        if access.can_download(mctx, copy):
            downloaders.add(m.id)
    return Audience(viewers, downloaders)


@dataclass
class _Stub:
    id: uuid.UUID


# ---------------------------------------------------------------- read
def can_edit(ctx: TreeContext, doc: Document) -> bool:
    if access.is_owner(ctx, doc):
        return True
    return not is_private_record_level(doc.privacy_level) and ctx.has(Permission.DOCUMENT_MANAGE)


def sharing_out(ctx: TreeContext, doc: Document, p: Proposal | None = None) -> SharingOut:
    current = _current(ctx, doc)
    p = p or current
    editable = can_edit(ctx, doc)
    owner = access.is_owner(ctx, doc)
    caps = caps_for_people(ctx, linked_people(ctx, doc.id))
    members: list[SharingMemberOut] = []
    people: list[SharingMemberOut] = []
    if editable:
        aud = audience(ctx, doc, p)
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
        if owner or not is_private_record_level(doc.privacy_level):
            members = [
                SharingMemberOut(
                    membership_id=mid,
                    display_name=names.get(mid, ""),
                    access="selected",
                    can_download=dl,
                )
                for mid, dl in p.members.items()
            ]
    return SharingOut(
        privacy_level=p.privacy_level,
        audience_branch_id=p.audience_branch_id,
        allow_download=p.allow_download,
        is_owner=owner,
        has_owner=doc.owner_membership_id is not None,
        can_edit=editable,
        can_widen=owner,
        legacy=L(doc.privacy_level) in (L.CUSTOM, L.PRIVATE_SELF),
        ceiling=ceiling_out(caps),
        members=members,
        audience=people,
    )


# ---------------------------------------------------------------- change
def _proposal(ctx: TreeContext, doc: Document, body: SharingUpdate) -> Proposal:
    level = L(body.privacy_level)
    if level == L.PUBLIC_DECEASED_ONLY:
        raise Unprocessable("Records cannot be public", code="public_not_supported")
    if level not in CHOOSABLE and level != L(doc.privacy_level):
        raise Unprocessable(
            "Choose Only me, Selected members, Selected branch or All family members",
            code="legacy_level",
        )
    branch = body.audience_branch_id if level == L.FAMILY_BRANCH else None
    if level == L.FAMILY_BRANCH and level != L(doc.privacy_level) and branch is None:
        raise Unprocessable("Choose the family branch to share with", code="branch_required")
    if (
        branch is not None
        and ctx.db.scalar(
            select(FamilyBranch.id).where(FamilyBranch.tree_id == ctx.tree_id, FamilyBranch.id == branch)
        )
        is None
    ):
        raise NotFound("Branch not found")
    members = _members(ctx, doc, body.members)
    if level == L.ONLY_ME and members:
        raise Unprocessable("A record kept for you only cannot be shared with members", code="only_me_record")
    if level == L.SELECTED_MEMBERS and not members:
        raise Unprocessable("Choose at least one member", code="members_required")
    return Proposal(level, branch, body.allow_download, members)


def _members(ctx: TreeContext, doc: Document, rows: list[SharingMemberIn]) -> dict[uuid.UUID, bool]:
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
    out = {r.membership_id: r.can_download for r in rows}
    if doc.owner_membership_id is not None:
        out.pop(doc.owner_membership_id, None)  # the owner needs no grant
    return out


def preview(ctx: TreeContext, document_id: uuid.UUID, body: SharingUpdate) -> SharingOut:
    doc = access.get_document(ctx, document_id)
    if not can_edit(ctx, doc):
        raise Forbidden("You cannot change who can see this record")
    return sharing_out(ctx, doc, _proposal(ctx, doc, body))


def update(ctx: TreeContext, document_id: uuid.UUID, body: SharingUpdate) -> SharingOut:
    doc = access.get_document(ctx, document_id)
    if not can_edit(ctx, doc):
        raise Forbidden("You cannot change who can see this record")
    new = _proposal(ctx, doc, body)
    apply(ctx, doc, new, confirm_wider=body.confirm_wider)
    return sharing_out(ctx, doc)


def apply(ctx: TreeContext, doc: Document, new: Proposal, *, confirm_wider: bool) -> None:
    caps = caps_for_people(ctx, linked_people(ctx, doc.id))
    if not within(new.privacy_level, new.audience_branch_id, caps):
        raise Unprocessable(
            "A person tagged in this record is kept more private; it cannot be shared this widely",
            code="privacy_too_open",
            details={"ceiling": c.model_dump(mode="json") if (c := ceiling_out(caps)) else None},
        )
    old = _current(ctx, doc)
    before, after = audience(ctx, doc, old), audience(ctx, doc, new)
    added = set(after.viewers) - set(before.viewers)
    added_dl = after.downloaders - before.downloaders
    # widening = anyone new can see or download; narrowing is open to managers (ADR-0027 §10)
    if not access.is_owner(ctx, doc) and (added or added_dl):
        raise Forbidden("Only the record's owner can share it more widely", code="owner_only_widening")
    if (added or added_dl) and not confirm_wider:
        raise Conflict(
            "This change lets more people see or download the record; confirm to continue",
            code="confirm_wider",
            details={"viewers_added": len(added), "downloaders_added": len(added_dl)},
        )
    doc.privacy_level = new.privacy_level
    doc.audience_branch_id = new.audience_branch_id
    doc.allow_download = new.allow_download
    _replace_grants(ctx, doc, old.members, new.members)
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
            target_type="document",
            target_id=doc.id,
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


def _replace_grants(
    ctx: TreeContext, doc: Document, old: dict[uuid.UUID, bool], new: dict[uuid.UUID, bool]
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
            AccessGrant.resource_type == GrantResource.DOCUMENT,
            AccessGrant.resource_id == doc.id,
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
                resource_type=GrantResource.DOCUMENT,
                resource_id=doc.id,
                permission=perm,
                created_by=ctx.user_id,
            )
        )
