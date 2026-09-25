from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, TreeCtx, request_info
from app.api.schemas import Message, Page, decode_cursor, encode_cursor
from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Forbidden, NotFound
from app.models import AccessGrant, AuditEvent, Tree, TreeInvitation, TreeMembership, User
from app.models.enums import Role
from app.modules.trees import service
from app.modules.trees.schemas import (
    AuditEventOut,
    GrantCreate,
    GrantOut,
    InvitationCreate,
    InvitationOut,
    InvitationPreview,
    MemberOut,
    MemberUpdate,
    TreeCreate,
    TreeOut,
    TreeUpdate,
)

router = APIRouter(tags=["trees"])


def _require_membership(ctx: TreeContext) -> TreeMembership:
    if ctx.membership is None:
        raise NotFound("Tree not found")
    return ctx.membership


def _tree_out(tree: Tree, m: TreeMembership) -> TreeOut:
    return TreeOut.model_validate(tree).model_copy(
        update={
            "my_roles": [Role(r) for r in m.roles],
            "my_permissions": service.tree_permissions(m),
            "my_branch_id": m.branch_id,
            "my_linked_person_id": m.linked_person_id,
        }
    )


@router.get("/trees", response_model=list[TreeOut])
def list_trees(user: CurrentUser, db: DbDep) -> list[TreeOut]:
    return [_tree_out(t, m) for t, m in service.my_trees(db, user)]


@router.post("/trees", response_model=TreeOut, status_code=status.HTTP_201_CREATED)
def create_tree(body: TreeCreate, request: Request, user: CurrentUser, db: DbDep) -> TreeOut:
    tree, m = service.create_tree(db, user, body.name, body.description, request_info(request))
    return _tree_out(tree, m)


@router.get("/trees/{tree_id}", response_model=TreeOut)
def get_tree(ctx: TreeCtx) -> TreeOut:
    membership = _require_membership(ctx)
    return _tree_out(ctx.tree, membership)


@router.patch("/trees/{tree_id}", response_model=TreeOut)
def update_tree(body: TreeUpdate, ctx: TreeCtx) -> TreeOut:
    ctx.require(Permission.TREE_MANAGE)
    changed = body.model_dump(exclude_unset=True)
    for k, v in changed.items():
        setattr(ctx.tree, k, v)
    if "public_mode" in changed:
        audit.log(
            ctx,
            "tree.public_sharing_changed",
            target_type="tree",
            target_id=ctx.tree_id,
            details={"public_mode": str(body.public_mode)},
        )
    audit.log(
        ctx, "tree.updated", target_type="tree", target_id=ctx.tree_id, details={"fields": sorted(changed)}
    )
    membership = _require_membership(ctx)
    return _tree_out(ctx.tree, membership)


@router.delete("/trees/{tree_id}", response_model=Message)
def delete_tree(ctx: TreeCtx) -> Message:
    if not ctx.is_owner:
        raise Forbidden("Only a tree owner can delete a tree")
    ctx.tree.deleted_at = dt.datetime.now(dt.UTC)
    audit.log(ctx, "tree.deleted", target_type="tree", target_id=ctx.tree_id)
    return Message(message="Tree deleted")


# ---- members ----
@router.get("/trees/{tree_id}/members", response_model=list[MemberOut])
def list_members(ctx: TreeCtx) -> list[MemberOut]:
    rows = ctx.db.execute(
        select(TreeMembership, User)
        .join(User, User.id == TreeMembership.user_id)
        .where(TreeMembership.tree_id == ctx.tree_id)
        .order_by(TreeMembership.created_at)
    ).all()
    show_email = ctx.has(Permission.MEMBERS_MANAGE)
    return [
        MemberOut(
            id=m.id,
            user_id=u.id,
            email=u.email if show_email or u.id == ctx.user_id else "",
            display_name=u.display_name,
            roles=[Role(r) for r in m.roles],
            branch_id=m.branch_id,
            linked_person_id=m.linked_person_id,
            created_at=m.created_at,
        )
        for m, u in rows
    ]


@router.patch("/trees/{tree_id}/members/{membership_id}", response_model=MemberOut)
def update_member(membership_id: uuid.UUID, body: MemberUpdate, ctx: TreeCtx) -> MemberOut:
    m = service.update_member(
        ctx,
        membership_id,
        roles=body.roles,
        branch_id=body.branch_id,
        linked_person_id=body.linked_person_id,
        clear_branch=body.clear_branch,
        clear_linked_person=body.clear_linked_person,
    )
    u = ctx.db.get(User, m.user_id)
    if u is None:
        raise NotFound("Member not found")
    return MemberOut(
        id=m.id,
        user_id=u.id,
        email=u.email,
        display_name=u.display_name,
        roles=[Role(r) for r in m.roles],
        branch_id=m.branch_id,
        linked_person_id=m.linked_person_id,
        created_at=m.created_at,
    )


@router.delete("/trees/{tree_id}/members/{membership_id}", response_model=Message)
def remove_member(membership_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.remove_member(ctx, membership_id)
    return Message(message="Member removed")


# ---- invitations ----
@router.get("/trees/{tree_id}/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: TreeCtx) -> list[InvitationOut]:
    ctx.require(Permission.MEMBERS_MANAGE)
    q = (
        select(TreeInvitation)
        .where(TreeInvitation.tree_id == ctx.tree_id)
        .order_by(TreeInvitation.created_at.desc())
    )
    if not ctx.is_admin:
        q = q.where(TreeInvitation.branch_id == ctx.branch_scope)
    return [InvitationOut.model_validate(i) for i in ctx.db.scalars(q)]


@router.post(
    "/trees/{tree_id}/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED
)
def create_invitation(body: InvitationCreate, ctx: TreeCtx) -> InvitationOut:
    inv, token = service.create_invitation(ctx, body.email, body.roles, body.branch_id)
    return InvitationOut.model_validate(inv).model_copy(
        update={"invite_url": service.invite_url(token), "token": token}
    )


@router.delete("/trees/{tree_id}/invitations/{invitation_id}", response_model=Message)
def revoke_invitation(invitation_id: uuid.UUID, ctx: TreeCtx) -> Message:
    ctx.require(Permission.MEMBERS_MANAGE)
    inv = ctx.db.scalar(
        select(TreeInvitation).where(
            TreeInvitation.tree_id == ctx.tree_id, TreeInvitation.id == invitation_id
        )
    )
    if inv is None or (not ctx.is_admin and inv.branch_id != ctx.branch_scope):
        raise NotFound("Invitation not found")
    inv.revoked_at = dt.datetime.now(dt.UTC)
    audit.log(ctx, "member.invitation_revoked", target_type="invitation", target_id=inv.id)
    return Message(message="Invitation revoked")


@router.get("/invitations/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, user: CurrentUser, db: DbDep) -> InvitationPreview:
    inv = service.find_invitation(db, token)
    tree = db.get(Tree, inv.tree_id)
    if tree is None:
        raise NotFound("Tree not found")
    return InvitationPreview(
        tree_id=tree.id,
        tree_name=tree.name,
        roles=[Role(r) for r in inv.roles],
        email=inv.email,
        expired=inv.expires_at < dt.datetime.now(dt.UTC),
    )


@router.post("/invitations/{token}/accept", response_model=TreeOut)
def accept_invitation(token: str, request: Request, user: CurrentUser, db: DbDep) -> TreeOut:
    m = service.accept_invitation(db, user, token, request_info(request))
    tree = db.get(Tree, m.tree_id)
    if tree is None:
        raise NotFound("Tree not found")
    return _tree_out(tree, m)


# ---- explicit access grants ----
@router.get("/trees/{tree_id}/grants", response_model=list[GrantOut])
def list_grants(ctx: TreeCtx) -> list[GrantOut]:
    ctx.require(Permission.PRIVACY_MANAGE)
    return [
        GrantOut.model_validate(g)
        for g in ctx.db.scalars(select(AccessGrant).where(AccessGrant.tree_id == ctx.tree_id))
    ]


@router.post("/trees/{tree_id}/grants", response_model=GrantOut, status_code=status.HTTP_201_CREATED)
def create_grant(body: GrantCreate, ctx: TreeCtx) -> GrantOut:
    g = service.create_grant(
        ctx, body.user_id, body.resource_type, body.resource_id, body.permission, body.expires_at
    )
    return GrantOut.model_validate(g)


@router.delete("/trees/{tree_id}/grants/{grant_id}", response_model=Message)
def delete_grant(grant_id: uuid.UUID, ctx: TreeCtx) -> Message:
    ctx.require(Permission.PRIVACY_MANAGE)
    g = ctx.db.scalar(
        select(AccessGrant).where(AccessGrant.tree_id == ctx.tree_id, AccessGrant.id == grant_id)
    )
    if g is None:
        raise NotFound("Grant not found")
    ctx.db.delete(g)
    audit.log(ctx, "grant.revoked", target_type=str(g.resource_type), target_id=g.resource_id)
    return Message(message="Grant revoked")


# ---- audit ----
@router.get("/trees/{tree_id}/audit", response_model=Page[AuditEventOut])
def list_audit(
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    action: str | None = None,
) -> Page[AuditEventOut]:
    ctx.require(Permission.AUDIT_READ)
    offset = decode_cursor(cursor)
    q = (
        select(AuditEvent, User.display_name)
        .outerjoin(User, User.id == AuditEvent.actor_user_id)
        .where(AuditEvent.tree_id == ctx.tree_id)
    )
    if action:
        q = q.where(AuditEvent.action.startswith(action))
    rows = ctx.db.execute(
        q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset(offset).limit(limit + 1)
    ).all()
    items = [
        AuditEventOut.model_validate(e).model_copy(update={"actor_name": name}) for e, name in rows[:limit]
    ]
    return Page(items=items, next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None)
