from __future__ import annotations

import datetime as dt
import re
import secrets
import uuid
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.authz.context import RequestInfo, TreeContext
from app.authz.permissions import Permission, permissions_for
from app.core import audit
from app.core.config import get_settings
from app.core.errors import ApiError, Conflict, Forbidden, NotFound, Unprocessable
from app.core.security import new_token, token_hash
from app.models import AccessGrant, FamilyBranch, Tree, TreeInvitation, TreeMembership, User
from app.models.enums import GrantResource, Role
from app.modules.trees import nominations

INVITATION_TTL_DAYS = 14
_ADMIN_GRANTABLE = {Role.OWNER, Role.FAMILY_ADMIN}
_BRANCH_ADMIN_GRANTABLE = {Role.CONTRIBUTOR, Role.VIEWER, Role.RESEARCHER}


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "family"
    return f"{base}-{secrets.token_hex(3)}"


def create_tree(
    db: Session, user: User, name: str, description: str | None, info: RequestInfo
) -> tuple[Tree, TreeMembership]:
    tree = Tree(name=name.strip(), description=description, slug=_slugify(name), created_by=user.id)
    db.add(tree)
    db.flush()
    membership = TreeMembership(
        tree_id=tree.id, user_id=user.id, roles=[Role.OWNER.value], created_by=user.id
    )
    db.add(membership)
    db.flush()
    audit.record(
        db,
        action="tree.created",
        actor_user_id=user.id,
        tree_id=tree.id,
        target_type="tree",
        target_id=tree.id,
        ip=info.ip,
        user_agent=info.user_agent,
    )
    return tree, membership


def my_trees(db: Session, user: User) -> list[tuple[Tree, TreeMembership]]:
    rows = db.execute(
        select(Tree, TreeMembership)
        .join(TreeMembership, TreeMembership.tree_id == Tree.id)
        .where(TreeMembership.user_id == user.id, Tree.deleted_at.is_(None))
        .order_by(Tree.created_at)
    ).all()
    return [(t, m) for t, m in rows]


def _validate_roles(ctx: TreeContext, roles: list[Role], branch_id: uuid.UUID | None) -> None:
    requested = set(roles)
    if requested & _ADMIN_GRANTABLE and not ctx.is_owner:
        raise Forbidden("Only a tree owner can grant owner or family-admin roles")
    if not ctx.is_admin:
        # branch admins: may only invite limited roles into their own branch
        if not requested <= _BRANCH_ADMIN_GRANTABLE:
            raise Forbidden("Branch admins can only grant contributor, researcher or viewer roles")
        if branch_id is None or branch_id != ctx.branch_scope:
            raise Forbidden("Branch admins can only invite members into their own branch")
    if Role.BRANCH_ADMIN in requested and branch_id is None:
        raise Unprocessable("A branch admin must be assigned to a family branch", code="branch_required")
    if (
        branch_id is not None
        and ctx.db.scalar(
            select(FamilyBranch.id).where(FamilyBranch.tree_id == ctx.tree_id, FamilyBranch.id == branch_id)
        )
        is None
    ):
        raise NotFound("Branch not found")


def create_invitation(
    ctx: TreeContext, email: str, roles: list[Role], branch_id: uuid.UUID | None
) -> tuple[TreeInvitation, str]:
    ctx.require(Permission.MEMBERS_MANAGE)
    _validate_roles(ctx, roles, branch_id)
    token = new_token()
    inv = TreeInvitation(
        tree_id=ctx.tree_id,
        email=email.strip().lower(),
        roles=[r.value for r in roles],
        branch_id=branch_id,
        token_hash=token_hash(token),
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=INVITATION_TTL_DAYS),
        created_by=ctx.user_id,
    )
    ctx.db.add(inv)
    ctx.db.flush()
    audit.log(
        ctx,
        "member.invited",
        target_type="invitation",
        target_id=inv.id,
        details={"roles": [r.value for r in roles], "branch_scoped": branch_id is not None},
    )
    return inv, token


def invite_url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/invite/{token}"


def find_invitation(db: Session, token: str) -> TreeInvitation:
    inv = db.scalar(select(TreeInvitation).where(TreeInvitation.token_hash == token_hash(token)))
    if inv is None or inv.revoked_at is not None:
        raise NotFound("Invitation not found")
    return inv


def accept_invitation(db: Session, user: User, token: str, info: RequestInfo) -> TreeMembership:
    if user.email_verified_at is None:
        # the invitation is bound to an email address, so the address must be proven first
        raise Forbidden("Confirm your email address before joining a tree", code="email_not_verified")
    inv = find_invitation(db, token)
    if inv.accepted_at is not None:
        raise Conflict("Invitation has already been used", code="invitation_used")
    if inv.expires_at < dt.datetime.now(dt.UTC):
        raise ApiError("Invitation has expired", code="invitation_expired", status_code=410)
    if inv.email != user.email:
        raise Forbidden(
            "This invitation was issued to a different email address", code="invitation_email_mismatch"
        )
    existing = db.scalar(
        select(TreeMembership).where(TreeMembership.tree_id == inv.tree_id, TreeMembership.user_id == user.id)
    )
    if existing is not None:
        # Never silently change scope (SEC-2): a branch-scoped invitation cannot merge into a
        # membership with a different (or no) scope. An unscoped invitation comes from an admin
        # (only admins can issue them) and deliberately replaces the scope.
        if inv.branch_id is not None and existing.branch_id != inv.branch_id:
            raise Conflict(
                "You are already a member of this tree with a different scope; ask a tree admin to change "
                "your roles instead",
                code="scope_conflict",
            )
        before = list(existing.roles)
        existing.roles = sorted(set(existing.roles) | set(inv.roles))
        existing.branch_id = inv.branch_id
        membership = existing
        from app.core.db import bind_tree

        bind_tree(db, inv.tree_id)  # admin_nomination is row-level secured
        nominations.on_roles_changed(db, inv.tree_id, existing, before, existing.roles, user.id)
    else:
        membership = TreeMembership(
            tree_id=inv.tree_id,
            user_id=user.id,
            roles=list(inv.roles),
            branch_id=inv.branch_id,
            created_by=inv.created_by,
        )
        db.add(membership)
    inv.accepted_at = dt.datetime.now(dt.UTC)
    inv.accepted_by = user.id
    db.flush()
    audit.record(
        db,
        action="member.joined",
        actor_user_id=user.id,
        tree_id=inv.tree_id,
        target_type="membership",
        target_id=membership.id,
        details={"roles": list(membership.roles)},
        ip=info.ip,
        user_agent=info.user_agent,
    )
    return membership


def _owner_count(db: Session, tree_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(TreeMembership)
            .where(TreeMembership.tree_id == tree_id, TreeMembership.roles.contains([Role.OWNER.value]))
        )
        or 0
    )


def grantable_roles(ctx: TreeContext) -> frozenset[Role]:
    """The roles this caller may give or take away. Only an owner manages owner and family-admin roles;
    a branch admin manages contributor, researcher and viewer roles in its own branch."""
    if ctx.is_owner:
        return frozenset(Role)
    if ctx.is_admin:
        return frozenset(Role) - _ADMIN_GRANTABLE
    return frozenset(_BRANCH_ADMIN_GRANTABLE)


def grantable_for(m: TreeMembership) -> list[Role]:
    """What a member may grant, from their own membership (for the UI; the server re-checks)."""
    roles = {Role(r) for r in m.roles}
    if Role.OWNER in roles:
        return sorted(Role)
    if Role.FAMILY_ADMIN in roles:
        return sorted(frozenset(Role) - _ADMIN_GRANTABLE)
    if Permission.MEMBERS_MANAGE.value in tree_permissions(m) and m.branch_id is not None:
        return sorted(_BRANCH_ADMIN_GRANTABLE)
    return []


def can_manage(ctx: TreeContext, m: TreeMembership) -> bool:
    """Whether this caller may change or remove membership ``m`` (mirrors update/remove)."""
    if not ctx.has(Permission.MEMBERS_MANAGE):
        return False
    if not ctx.is_admin and (ctx.branch_scope is None or m.branch_id != ctx.branch_scope):
        return False
    if Role.OWNER.value in m.roles and not ctx.is_owner:
        return False
    return m.user_id == ctx.user_id or {Role(r) for r in m.roles} <= grantable_roles(ctx)


def _require_manageable(ctx: TreeContext, m: TreeMembership) -> None:
    """A member may be changed or removed only by someone who could have granted all of its roles.

    Without this, a family admin could delete another family admin's membership (taking away a role
    only the owner may take away), and a branch admin could demote or remove a peer or a custodian.
    """
    held = {Role(r) for r in m.roles}
    if m.user_id == ctx.user_id:
        return  # own membership: role changes are refused separately; leaving is not an escalation
    if not held <= grantable_roles(ctx):
        raise Forbidden("You can only manage members whose roles you could grant")


def _get_membership(ctx: TreeContext, membership_id: uuid.UUID) -> TreeMembership:
    m = ctx.db.scalar(
        select(TreeMembership).where(
            TreeMembership.tree_id == ctx.tree_id, TreeMembership.id == membership_id
        )
    )
    if m is None:
        raise NotFound("Member not found")
    if not ctx.is_admin and (ctx.branch_scope is None or m.branch_id != ctx.branch_scope):
        raise Forbidden("You can only manage members of your own branch")
    return m


def update_member(
    ctx: TreeContext,
    membership_id: uuid.UUID,
    *,
    roles: list[Role] | None,
    branch_id: uuid.UUID | None,
    linked_person_id: uuid.UUID | None,
    clear_branch: bool,
    clear_linked_person: bool,
) -> TreeMembership:
    ctx.require(Permission.MEMBERS_MANAGE)
    m = _get_membership(ctx, membership_id)
    if m.user_id == ctx.user_id and roles is not None and not ctx.is_owner:
        raise Forbidden("You cannot change your own roles")
    _require_manageable(ctx, m)
    previous_roles = sorted(m.roles)
    new_branch = None if clear_branch else (branch_id if branch_id is not None else m.branch_id)
    if roles is not None:
        old = {Role(r) for r in m.roles}
        new = set(roles)
        if (old ^ new) & _ADMIN_GRANTABLE and not ctx.is_owner:
            raise Forbidden("Only a tree owner can grant or remove owner/family-admin roles")
        if not (old ^ new) <= grantable_roles(ctx):
            raise Forbidden("You can only give or take away roles you could grant")
        added = new - old
        if added:
            _validate_roles(ctx, sorted(added), new_branch)
        if Role.OWNER in old and Role.OWNER not in new and _owner_count(ctx.db, ctx.tree_id) <= 1:
            raise Conflict("A tree must keep at least one owner", code="last_owner")
        m.roles = sorted(r.value for r in new)
    if clear_branch or branch_id is not None:
        if not ctx.is_admin:
            raise Forbidden("Only tree admins can change a member's branch")
        if new_branch is not None:
            _validate_roles(ctx, [], new_branch)
        m.branch_id = new_branch
    if clear_linked_person:
        m.linked_person_id = None
    elif linked_person_id is not None:
        # SEC-3: linking a member to a person affects branch visibility, so only admins may do it,
        # never on their own membership, and only to people they can see. (Self-access to a
        # profile comes from an approved profile claim, not from this link.)
        if not ctx.is_admin:
            raise Forbidden("Only tree admins can link a member to a person")
        if m.user_id == ctx.user_id:
            raise Forbidden("Link your own profile through a profile claim instead")
        from app.modules.genealogy import lookup

        lookup.get_person(ctx, linked_person_id)
        m.linked_person_id = linked_person_id
    ctx.db.flush()
    nominations.on_roles_changed(ctx.db, ctx.tree_id, m, previous_roles, m.roles, ctx.user_id)
    admin_change = bool(({Role(r) for r in previous_roles} ^ {Role(r) for r in m.roles}) & _ADMIN_GRANTABLE)
    audit.log(
        ctx,
        "member.updated",
        target_type="membership",
        target_id=m.id,
        details={
            "previous_roles": previous_roles,
            "roles": sorted(m.roles),
            "admin_change": admin_change,
            "branch_changed": clear_branch or branch_id is not None,
        },
    )
    return m


def remove_member(ctx: TreeContext, membership_id: uuid.UUID) -> None:
    ctx.require(Permission.MEMBERS_MANAGE)
    m = _get_membership(ctx, membership_id)
    if Role.OWNER.value in m.roles:
        if not ctx.is_owner:
            raise Forbidden("Only an owner can remove an owner")
        if _owner_count(ctx.db, ctx.tree_id) <= 1:
            raise Conflict("A tree must keep at least one owner", code="last_owner")
    _require_manageable(ctx, m)
    roles = sorted(m.roles)
    nominations.on_member_leaving(ctx.db, ctx.tree_id, m, ctx.user_id)
    audit_cascaded_grants(ctx.db, tree_id=ctx.tree_id, membership_id=m.id, actor_user_id=ctx.user_id)
    ctx.db.delete(m)
    audit.log(
        ctx,
        "member.removed",
        target_type="membership",
        target_id=m.id,
        details={"roles": roles, "admin_change": bool({Role(r) for r in roles} & _ADMIN_GRANTABLE)},
    )


def audit_cascaded_grants(
    db: Session, *, tree_id: uuid.UUID, membership_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> int:
    """Record how many grants go with a membership about to be deleted.

    The grants themselves are deleted by the ``ON DELETE CASCADE`` on ``access_grant.membership_id``
    (ADR-0027 §3). Call this before the delete. Audited with a count only: no resource ids or titles.
    ``access_grant`` is row-level secured, so the session must be bound to ``tree_id``.
    """
    count = int(
        db.scalar(
            select(func.count())
            .select_from(AccessGrant)
            .where(AccessGrant.tree_id == tree_id, AccessGrant.membership_id == membership_id)
        )
        or 0
    )
    if count:
        audit.record(
            db,
            action="grant.cascade_removed",
            actor_user_id=actor_user_id,
            tree_id=tree_id,
            target_type="membership",
            target_id=membership_id,
            details={"count": count},
        )
    return count


def create_grant(
    ctx: TreeContext,
    user_id: uuid.UUID,
    resource_type: GrantResource,
    resource_id: uuid.UUID,
    permission: str,
    expires_at: dt.datetime | None,
) -> AccessGrant:
    ctx.require(Permission.PRIVACY_MANAGE)
    membership_id = ctx.db.scalar(
        select(TreeMembership.id).where(
            TreeMembership.tree_id == ctx.tree_id, TreeMembership.user_id == user_id
        )
    )
    if membership_id is None:
        raise NotFound("Grants can only be given to members of this tree")
    if not manageable_grant_resources(ctx, [(resource_type, resource_id)]):
        raise NotFound("Resource not found")
    grant = AccessGrant(
        tree_id=ctx.tree_id,
        membership_id=membership_id,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        permission=permission,
        expires_at=expires_at,
        created_by=ctx.user_id,
    )
    ctx.db.add(grant)
    ctx.db.flush()
    audit.log(
        ctx,
        "grant.created",
        target_type=str(resource_type),
        target_id=resource_id,
        details={"permission": str(permission), "grantee": str(user_id)},
    )
    return grant


def manageable_grant_resources(
    ctx: TreeContext, resources: Iterable[tuple[GrantResource, uuid.UUID]]
) -> set[tuple[GrantResource, uuid.UUID]]:
    """The resources whose grants this caller may see, create or revoke (ADR-0027 §3, finding A7).

    ``privacy.manage`` plus the record being visible to the caller: a privacy manager is never told
    that a record they cannot see exists, nor who may see it. Anything else is treated as absent.
    """
    if not ctx.has(Permission.PRIVACY_MANAGE):
        return set()
    from app.models import Document, Property
    from app.modules.documents.access import can_view_document
    from app.modules.genealogy.lookup import visible_subjects
    from app.modules.property.service import can_view_property

    wanted: dict[GrantResource, set[uuid.UUID]] = {}
    for rt, rid in resources:
        wanted.setdefault(GrantResource(rt), set()).add(rid)
    ok: set[tuple[GrantResource, uuid.UUID]] = set()
    if ids := wanted.get(GrantResource.PERSON):
        ok |= {(GrantResource.PERSON, pid) for pid in visible_subjects(ctx, ids)}
    if ids := wanted.get(GrantResource.DOCUMENT):
        docs = ctx.db.scalars(select(Document).where(Document.tree_id == ctx.tree_id, Document.id.in_(ids)))
        ok |= {(GrantResource.DOCUMENT, d.id) for d in docs if can_view_document(ctx, d)}
    if ids := wanted.get(GrantResource.PROPERTY):
        props = ctx.db.scalars(select(Property).where(Property.tree_id == ctx.tree_id, Property.id.in_(ids)))
        ok |= {(GrantResource.PROPERTY, p.id) for p in props if can_view_property(ctx, p)}
    return ok


def tree_permissions(membership: TreeMembership) -> list[str]:
    return sorted(p.value for p in permissions_for(frozenset(Role(r) for r in membership.roles)))
