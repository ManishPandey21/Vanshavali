from __future__ import annotations

import contextlib
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
from app.models import AccessGrant, AdminNomination, AuditEvent, Tree, TreeInvitation, TreeMembership, User
from app.models.enums import GrantResource, Role
from app.modules.trees import nominations, service
from app.modules.trees.schemas import (
    AuditEventOut,
    GrantCreate,
    GrantOut,
    InvitationCreate,
    InvitationOut,
    InvitationPreview,
    MemberOut,
    MemberUpdate,
    NominationApprove,
    NominationCreate,
    NominationOut,
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
            "my_grantable_roles": service.grantable_for(m),
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
    from app.modules.genealogy import lookup

    linked_visible = set(
        lookup.visible_subjects(ctx, [m.linked_person_id for m, _ in rows if m.linked_person_id])
    )

    def show_email(m: TreeMembership, u: User) -> bool:
        if u.id == ctx.user_id or ctx.is_admin:
            return True
        # branch admins manage (and see contact details of) their own branch's members only
        return (
            ctx.has(Permission.MEMBERS_MANAGE) and m.branch_id is not None and m.branch_id == ctx.branch_scope
        )

    return [
        MemberOut(
            id=m.id,
            user_id=u.id,
            email=u.email if show_email(m, u) else "",
            display_name=u.display_name,
            roles=[Role(r) for r in m.roles],
            branch_id=m.branch_id,
            linked_person_id=m.linked_person_id if m.linked_person_id in linked_visible else None,
            created_at=m.created_at,
            can_manage=service.can_manage(ctx, m),
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
        can_manage=service.can_manage(ctx, m),
    )


@router.delete("/trees/{tree_id}/members/{membership_id}", response_model=Message)
def remove_member(membership_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.remove_member(ctx, membership_id)
    return Message(message="Member removed")


# ---- Family Admin nominations (ADR-0006 amendment of 9 Nov 2026) ----
def _nomination_out(ctx: TreeContext, n: AdminNomination) -> NominationOut:
    return NominationOut(**nominations.describe(ctx, [n])[0])


@router.get("/trees/{tree_id}/admin-nominations", response_model=list[NominationOut])
def list_admin_nominations(ctx: TreeCtx) -> list[NominationOut]:
    """Open nominations: all of them for owners and family admins, only your own otherwise."""
    return [NominationOut(**d) for d in nominations.describe(ctx, nominations.list_open(ctx))]


@router.post(
    "/trees/{tree_id}/admin-nominations", response_model=NominationOut, status_code=status.HTTP_201_CREATED
)
def create_admin_nomination(body: NominationCreate, ctx: TreeCtx) -> NominationOut:
    return _nomination_out(ctx, nominations.create(ctx, body.membership_id, body.reason))


@router.post("/trees/{tree_id}/admin-nominations/{nomination_id}/accept", response_model=NominationOut)
def accept_admin_nomination(nomination_id: uuid.UUID, ctx: TreeCtx) -> NominationOut:
    return _nomination_out(ctx, nominations.accept(ctx, nomination_id))


@router.post("/trees/{tree_id}/admin-nominations/{nomination_id}/decline", response_model=NominationOut)
def decline_admin_nomination(nomination_id: uuid.UUID, ctx: TreeCtx) -> NominationOut:
    return _nomination_out(ctx, nominations.decline(ctx, nomination_id))


@router.post("/trees/{tree_id}/admin-nominations/{nomination_id}/approve", response_model=NominationOut)
def approve_admin_nomination(
    nomination_id: uuid.UUID, body: NominationApprove, ctx: TreeCtx
) -> NominationOut:
    return _nomination_out(ctx, nominations.approve(ctx, nomination_id, clear_branch=body.clear_branch))


@router.post("/trees/{tree_id}/admin-nominations/{nomination_id}/reject", response_model=NominationOut)
def reject_admin_nomination(nomination_id: uuid.UUID, ctx: TreeCtx) -> NominationOut:
    return _nomination_out(ctx, nominations.reject(ctx, nomination_id))


@router.post("/trees/{tree_id}/admin-nominations/{nomination_id}/withdraw", response_model=NominationOut)
def withdraw_admin_nomination(nomination_id: uuid.UUID, ctx: TreeCtx) -> NominationOut:
    return _nomination_out(ctx, nominations.withdraw(ctx, nomination_id))


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
    """Grants on records the caller may manage; others are not listed (ADR-0027 §3, A7). A record's
    owner manages the grants on it; grants on a private record are listed to its owner only."""
    if not (
        ctx.has(Permission.PRIVACY_MANAGE)
        or ctx.has(Permission.DOCUMENT_UPLOAD)
        or ctx.has(Permission.FAMILY_WRITE)
        or service.owns_a_record(ctx)
    ):
        raise Forbidden()  # only privacy managers and record owners have grants to manage
    grants = list(ctx.db.scalars(select(AccessGrant).where(AccessGrant.tree_id == ctx.tree_id)))
    manageable = service.manageable_grant_resources(ctx, [(g.resource_type, g.resource_id) for g in grants])
    return [
        GrantOut.model_validate(g)
        for g in grants
        if (GrantResource(g.resource_type), g.resource_id) in manageable
    ]


@router.post("/trees/{tree_id}/grants", response_model=GrantOut, status_code=status.HTTP_201_CREATED)
def create_grant(body: GrantCreate, ctx: TreeCtx) -> GrantOut:
    g = service.create_grant(
        ctx, body.user_id, body.resource_type, body.resource_id, body.permission, body.expires_at
    )
    return GrantOut.model_validate(g)


@router.delete("/trees/{tree_id}/grants/{grant_id}", response_model=Message)
def delete_grant(grant_id: uuid.UUID, ctx: TreeCtx) -> Message:
    g = ctx.db.scalar(
        select(AccessGrant).where(AccessGrant.tree_id == ctx.tree_id, AccessGrant.id == grant_id)
    )
    if g is None or not service.manageable_grant_resources(ctx, [(g.resource_type, g.resource_id)]):
        raise NotFound("Grant not found")
    ctx.db.delete(g)
    audit.log(ctx, "grant.revoked", target_type=str(g.resource_type), target_id=g.resource_id)
    return Message(message="Grant revoked")


# ---- audit ----
def _document_ids(item: AuditEventOut) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    if item.target_type == "document" and item.target_id is not None:
        ids.add(item.target_id)
    raw = (item.details or {}).get("document_id")
    if isinstance(raw, str):
        with contextlib.suppress(ValueError):
            ids.add(uuid.UUID(raw))
    return ids


def _hidden_traditions(ctx: TreeContext, items: list[AuditEventOut]) -> set[uuid.UUID]:
    """Private tradition entries named by these events that the reader may not see."""
    from app.authz.privacy import is_private_record_level
    from app.models import TraditionEntry
    from app.modules.traditions.service import may_read

    ids = {i.target_id for i in items if i.target_type == "tradition" and i.target_id is not None}
    if not ids:
        return set()
    entries = ctx.db.scalars(
        select(TraditionEntry).where(TraditionEntry.tree_id == ctx.tree_id, TraditionEntry.id.in_(ids))
    )
    return {e.id for e in entries if is_private_record_level(e.privacy_level) and not may_read(ctx, e)}


def _redact_private_records(ctx: TreeContext, items: list[AuditEventOut]) -> list[AuditEventOut]:
    """Events about a record the reader may not see become an opaque "private record" entry with
    no id, title or details, so the audit log never reveals a private record (ADR-0027 §11)."""
    from app.models import Document
    from app.modules.documents.access import can_view_document

    wanted = set().union(*(_document_ids(i) for i in items)) if items else set()
    if not wanted and not any(i.target_type == "tradition" for i in items):
        return items
    docs = ctx.db.scalars(select(Document).where(Document.tree_id == ctx.tree_id, Document.id.in_(wanted)))
    visible = {d.id for d in docs if can_view_document(ctx, d)}
    hidden_entries = _hidden_traditions(ctx, items)
    out = []
    for i in items:
        if _document_ids(i) - visible or (i.target_type == "tradition" and i.target_id in hidden_entries):
            i = i.model_copy(
                update={"target_type": "private_record", "target_id": None, "summary": None, "details": {}}
            )
        out.append(i)
    return out


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
    items = _redact_private_records(ctx, items)
    return Page(items=items, next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None)
