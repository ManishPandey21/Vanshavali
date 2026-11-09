"""Family Admin nominations, approved by an Owner (ADR-0006 amendment of 9 Nov 2026).

A Family Admin puts a member forward; the nominee accepts; an Owner approves, and only then does the
role change, through ``service.update_member`` as that Owner with its usual rules and audit. Nothing
here grants a role by itself.

- Visibility (§7): Owners and Family Admins see every open nomination with its reason; the nominee
  sees their own (who nominated them and why); nobody else sees any, and unseen ids answer 404.
- Lapsing (§6): ``on_roles_changed`` and ``on_member_leaving`` are called from every path that
  changes or ends a membership. Approval re-checks the same conditions, so a missed hook still
  cannot let a stale nomination through.
- Expiry: open nominations past ``expires_at`` are closed whenever the tree's nominations are read
  or acted on, and approval refuses an expired one even before that.
- The reason is erased when a nomination closes, and audit events never hold it (§9).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authz.context import TreeContext
from app.core import audit
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.ratelimit import enforce
from app.models import AdminNomination, Tree, TreeMembership, User, UserNotification
from app.models.enums import NominationStatus, NotificationKind, Role

NOMINATION_TTL_DAYS = 14
MAX_OPEN_PER_TREE = 5
RATE_LIMIT_PER_MINUTE = 30
_ADMIN = {Role.OWNER.value, Role.FAMILY_ADMIN.value}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _rate_limit(ctx: TreeContext) -> None:
    enforce(f"admin-nomination:{ctx.user_id}", RATE_LIMIT_PER_MINUTE)


def _audit(
    db: Session, tree_id: uuid.UUID, actor: uuid.UUID | None, step: str, n: AdminNomination, **extra: Any
) -> None:
    """One audit event per step: actor, nominee membership and outcome; never the reason (§9)."""
    audit.record(
        db,
        action=f"admin_nomination.{step}",
        actor_user_id=actor,
        tree_id=tree_id,
        target_type="admin_nomination",
        target_id=n.id,
        details={
            "nominee_membership_id": str(n.nominee_membership_id) if n.nominee_membership_id else None,
            "status": n.status.value,
            **extra,
        },
    )


def _notify(
    db: Session,
    tree_id: uuid.UUID,
    users: Iterable[uuid.UUID | None],
    kind: NotificationKind,
    n: AdminNomination,
    actor: uuid.UUID | None,
) -> None:
    """In-app only (§8): a kind and ids; the text is built when read."""
    for uid in dict.fromkeys(u for u in users if u and u != actor):
        db.add(
            UserNotification(
                tree_id=tree_id, user_id=uid, kind=kind, subject_id=n.id, actor_id=actor, created_by=actor
            )
        )


def _owners(db: Session, tree_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(TreeMembership.user_id).where(
                TreeMembership.tree_id == tree_id, TreeMembership.roles.contains([Role.OWNER.value])
            )
        )
    )


def _close(
    db: Session,
    tree_id: uuid.UUID,
    n: AdminNomination,
    status: NominationStatus,
    actor: uuid.UUID | None,
    step: str,
    **extra: Any,
) -> None:
    n.status = status
    n.closed_at = _now()
    n.reason = ""  # the reason is only needed while the nomination is open
    if status in (NominationStatus.APPROVED, NominationStatus.DECLINED_BY_OWNER):
        n.decided_by = actor
    _audit(db, tree_id, actor, step, n, **extra)


def _open(db: Session, tree_id: uuid.UUID, *conditions: Any) -> list[AdminNomination]:
    return list(
        db.scalars(
            select(AdminNomination)
            .where(
                AdminNomination.tree_id == tree_id,
                AdminNomination.status == NominationStatus.OPEN,
                *conditions,
            )
            .with_for_update()
        )
    )


# ------------------------------------------------------------------ lapsing and expiry
def _lapse(db: Session, tree_id: uuid.UUID, n: AdminNomination, actor: uuid.UUID | None, cause: str) -> None:
    _close(db, tree_id, n, NominationStatus.LAPSED, actor, "lapsed", cause=cause)
    _notify(db, tree_id, [n.nominator_id], NotificationKind.NOMINATION_LAPSED, n, None)


def on_roles_changed(
    db: Session,
    tree_id: uuid.UUID,
    m: TreeMembership,
    before: Iterable[str],
    after: Iterable[str],
    actor: uuid.UUID | None,
) -> None:
    """§6: the nominator lost Family Admin, or the nominee became an Owner or Family Admin."""
    before, after = set(before), set(after)
    if Role.FAMILY_ADMIN.value in before and Role.FAMILY_ADMIN.value not in after:
        for n in _open(db, tree_id, AdminNomination.nominator_id == m.user_id):
            _lapse(db, tree_id, n, actor, "nominator_lost_role")
    if (after & _ADMIN) - before:
        for n in _open(db, tree_id, AdminNomination.nominee_membership_id == m.id):
            _lapse(db, tree_id, n, actor, "nominee_became_admin")


def on_member_leaving(db: Session, tree_id: uuid.UUID, m: TreeMembership, actor: uuid.UUID | None) -> None:
    """§6: the nominator or the nominee leaves the tree (removed, or the account was closed)."""
    for n in _open(db, tree_id, AdminNomination.nominator_id == m.user_id):
        _lapse(db, tree_id, n, actor, "nominator_left")
    for n in _open(db, tree_id, AdminNomination.nominee_membership_id == m.id):
        _lapse(db, tree_id, n, actor, "nominee_left")


def expire_due(db: Session, tree_id: uuid.UUID) -> int:
    due = _open(db, tree_id, AdminNomination.expires_at <= _now())
    for n in due:
        _close(db, tree_id, n, NominationStatus.EXPIRED, None, "expired")
        _notify(db, tree_id, [n.nominator_id], NotificationKind.NOMINATION_EXPIRED, n, None)
    return len(due)


# ------------------------------------------------------------------ reading
def _can_see(ctx: TreeContext, n: AdminNomination) -> bool:
    return ctx.is_admin or (ctx.user_id is not None and n.nominee_user_id == ctx.user_id)


def _get(ctx: TreeContext, nomination_id: uuid.UUID) -> AdminNomination:
    n = ctx.db.scalar(
        select(AdminNomination)
        .where(AdminNomination.tree_id == ctx.tree_id, AdminNomination.id == nomination_id)
        .with_for_update()
    )
    if n is None or not _can_see(ctx, n):
        raise NotFound("Nomination not found")
    return n


def _require_open(n: AdminNomination) -> None:
    if n.status != NominationStatus.OPEN:
        raise Conflict("This nomination is already closed", code="nomination_closed")
    if n.expires_at <= _now():
        raise Conflict("This nomination has expired", code="nomination_closed")


def describe(ctx: TreeContext, items: list[AdminNomination]) -> list[dict[str, Any]]:
    users = {u for n in items for u in (n.nominator_id, n.nominee_user_id) if u}
    names = (
        dict(ctx.db.execute(select(User.id, User.display_name).where(User.id.in_(users))).all())
        if users
        else {}
    )
    mids = [n.nominee_membership_id for n in items if n.nominee_membership_id]
    branches = (
        dict(
            ctx.db.execute(
                select(TreeMembership.id, TreeMembership.branch_id).where(
                    TreeMembership.tree_id == ctx.tree_id, TreeMembership.id.in_(mids)
                )
            ).all()
        )
        if mids
        else {}
    )
    out = []
    for n in items:
        is_open = n.status == NominationStatus.OPEN
        mine = n.nominee_user_id == ctx.user_id
        out.append(
            {
                "id": n.id,
                "nominee_membership_id": n.nominee_membership_id,
                "nominee_name": names.get(n.nominee_user_id, "A former member") if n.nominee_user_id else "",
                "nominator_name": names.get(n.nominator_id, "A former member") if n.nominator_id else "",
                "reason": n.reason,
                "status": n.status,
                "created_at": n.created_at,
                "expires_at": n.expires_at,
                "nominee_accepted": n.nominee_accepted_at is not None,
                "nominee_branch_scoped": n.nominee_membership_id is not None
                and branches.get(n.nominee_membership_id) is not None,
                "is_mine": mine,
                "can_accept": is_open and mine and n.nominee_accepted_at is None,
                "can_decline": is_open and mine,
                "can_decide": is_open and ctx.is_owner,
                "can_withdraw": is_open and n.nominator_id == ctx.user_id,
            }
        )
    return out


def list_open(ctx: TreeContext) -> list[AdminNomination]:
    if ctx.membership is None:
        raise NotFound("Tree not found")
    _rate_limit(ctx)
    expire_due(ctx.db, ctx.tree_id)
    q = select(AdminNomination).where(
        AdminNomination.tree_id == ctx.tree_id, AdminNomination.status == NominationStatus.OPEN
    )
    if not ctx.is_admin:
        q = q.where(AdminNomination.nominee_user_id == ctx.user_id)
    return list(ctx.db.scalars(q.order_by(AdminNomination.created_at)))


# ------------------------------------------------------------------ steps
def create(ctx: TreeContext, membership_id: uuid.UUID, reason: str) -> AdminNomination:
    """§1–§3, §10: a Family Admin nominates an existing member who is not an admin and not themselves."""
    if ctx.membership is None:
        raise NotFound("Tree not found")
    _rate_limit(ctx)
    if Role.FAMILY_ADMIN not in ctx.roles:
        raise Forbidden("Only a family admin can nominate a member for family admin")
    reason = reason.strip()
    if not reason:
        raise Unprocessable("Give a reason for the nomination", code="reason_required")
    nominee = ctx.db.scalar(
        select(TreeMembership).where(
            TreeMembership.tree_id == ctx.tree_id, TreeMembership.id == membership_id
        )
    )
    if nominee is None:
        raise NotFound("Member not found")
    if nominee.user_id == ctx.user_id:
        raise Forbidden("You cannot nominate yourself", code="self_nomination")
    if set(nominee.roles) & _ADMIN:
        raise Conflict("This member is already an owner or family admin", code="already_admin")
    # serialise nominations in this tree, so the per-tree limit holds under concurrent requests
    ctx.db.execute(select(Tree.id).where(Tree.id == ctx.tree_id).with_for_update())
    expire_due(ctx.db, ctx.tree_id)
    open_count = ctx.db.scalar(
        select(func.count())
        .select_from(AdminNomination)
        .where(AdminNomination.tree_id == ctx.tree_id, AdminNomination.status == NominationStatus.OPEN)
    )
    if (open_count or 0) >= MAX_OPEN_PER_TREE:
        raise Conflict(
            f"A tree can have at most {MAX_OPEN_PER_TREE} open nominations", code="nomination_limit"
        )
    n = AdminNomination(
        tree_id=ctx.tree_id,
        nominator_id=ctx.user_id,
        nominee_membership_id=nominee.id,
        nominee_user_id=nominee.user_id,
        reason=reason,
        status=NominationStatus.OPEN,
        expires_at=_now() + dt.timedelta(days=NOMINATION_TTL_DAYS),
        created_by=ctx.user_id,
    )
    try:
        with ctx.db.begin_nested():
            ctx.db.add(n)
            ctx.db.flush()
    except IntegrityError:
        raise Conflict("This member already has an open nomination", code="already_nominated") from None
    _audit(ctx.db, ctx.tree_id, ctx.user_id, "created", n)
    _notify(
        ctx.db,
        ctx.tree_id,
        [*_owners(ctx.db, ctx.tree_id), nominee.user_id],
        NotificationKind.NOMINATION_CREATED,
        n,
        ctx.user_id,
    )
    return n


def _as_nominee(ctx: TreeContext, nomination_id: uuid.UUID) -> AdminNomination:
    _rate_limit(ctx)
    n = _get(ctx, nomination_id)
    if n.nominee_user_id != ctx.user_id:
        raise Forbidden("Only the person nominated can answer this nomination")
    _require_open(n)
    return n


def accept(ctx: TreeContext, nomination_id: uuid.UUID) -> AdminNomination:
    n = _as_nominee(ctx, nomination_id)
    if n.nominee_accepted_at is not None:
        raise Conflict("You have already accepted this nomination", code="already_accepted")
    n.nominee_accepted_at = _now()
    _audit(ctx.db, ctx.tree_id, ctx.user_id, "accepted_by_nominee", n)
    _notify(
        ctx.db,
        ctx.tree_id,
        [n.nominator_id, *_owners(ctx.db, ctx.tree_id)],
        NotificationKind.NOMINATION_ACCEPTED,
        n,
        ctx.user_id,
    )
    return n


def decline(ctx: TreeContext, nomination_id: uuid.UUID) -> AdminNomination:
    n = _as_nominee(ctx, nomination_id)
    _close(ctx.db, ctx.tree_id, n, NominationStatus.DECLINED_BY_NOMINEE, ctx.user_id, "declined_by_nominee")
    _notify(ctx.db, ctx.tree_id, [n.nominator_id], NotificationKind.NOMINATION_DECLINED, n, ctx.user_id)
    return n


def _as_owner(ctx: TreeContext, nomination_id: uuid.UUID) -> AdminNomination:
    _rate_limit(ctx)
    n = _get(ctx, nomination_id)
    if not ctx.is_owner:
        raise Forbidden("Only a tree owner can approve or decline a nomination")
    _require_open(n)
    return n


def approve(ctx: TreeContext, nomination_id: uuid.UUID, *, clear_branch: bool) -> AdminNomination:
    """§4–§5: only an Owner, only after the nominee accepted; the role changes through update_member."""
    from app.modules.trees import service

    n = _as_owner(ctx, nomination_id)
    if n.nominee_accepted_at is None:
        raise Conflict("The nominee has not accepted the nomination yet", code="nominee_not_accepted")
    nominee = (
        ctx.db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == ctx.tree_id, TreeMembership.id == n.nominee_membership_id
            )
        )
        if n.nominee_membership_id
        else None
    )
    nominator = ctx.db.scalar(
        select(TreeMembership).where(
            TreeMembership.tree_id == ctx.tree_id, TreeMembership.user_id == n.nominator_id
        )
    )
    # the lapse hooks should already have closed these; re-check so a stale nomination never passes
    cause = None
    if nominee is None:
        cause = "nominee_left"
    elif set(nominee.roles) & _ADMIN:
        cause = "nominee_became_admin"
    elif nominator is None:
        cause = "nominator_left"
    elif Role.FAMILY_ADMIN.value not in nominator.roles:
        cause = "nominator_lost_role"
    if cause is not None or nominee is None:
        cause = cause or "nominee_left"
        _lapse(ctx.db, ctx.tree_id, n, ctx.user_id, cause)
        ctx.db.commit()  # keep the lapse even though this request fails
        raise Conflict("This nomination has lapsed", code="nomination_lapsed", details={"cause": cause})
    scoped = nominee.branch_id is not None
    if scoped and not clear_branch:
        raise Unprocessable(
            "Approving makes this member a family admin for the whole tree and removes their branch "
            "scope; confirm with clear_branch",
            code="branch_scope_confirmation_required",
        )
    roles = {Role(r) for r in nominee.roles} | {Role.FAMILY_ADMIN}
    if scoped:
        roles.discard(Role.BRANCH_ADMIN)  # a branch admin needs a branch; family admin covers it
    _close(ctx.db, ctx.tree_id, n, NominationStatus.APPROVED, ctx.user_id, "approved", cleared_branch=scoped)
    service.update_member(
        ctx,
        nominee.id,
        roles=sorted(roles),
        branch_id=None,
        linked_person_id=None,
        clear_branch=scoped,
        clear_linked_person=False,
    )
    _notify(
        ctx.db,
        ctx.tree_id,
        [n.nominator_id, n.nominee_user_id],
        NotificationKind.NOMINATION_APPROVED,
        n,
        ctx.user_id,
    )
    return n


def reject(ctx: TreeContext, nomination_id: uuid.UUID) -> AdminNomination:
    n = _as_owner(ctx, nomination_id)
    _close(ctx.db, ctx.tree_id, n, NominationStatus.DECLINED_BY_OWNER, ctx.user_id, "declined_by_owner")
    _notify(
        ctx.db,
        ctx.tree_id,
        [n.nominator_id, n.nominee_user_id],
        NotificationKind.NOMINATION_REJECTED,
        n,
        ctx.user_id,
    )
    return n


def withdraw(ctx: TreeContext, nomination_id: uuid.UUID) -> AdminNomination:
    _rate_limit(ctx)
    n = _get(ctx, nomination_id)
    if n.nominator_id != ctx.user_id:
        raise Forbidden("Only the member who made a nomination can withdraw it")
    _require_open(n)
    _close(ctx.db, ctx.tree_id, n, NominationStatus.WITHDRAWN, ctx.user_id, "withdrawn")
    return n
