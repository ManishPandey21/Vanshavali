"""In-app notifications for proposals and challenges (ADR-0021 §7).

A notification stores a kind and ids only. Its text is built when it is read, with the reader's
current permissions, so it never shows more than the reader may see now: a person the reader can
no longer see becomes "someone in the tree". Nothing is sent outside the app.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import func, select, update

from app.authz.context import TreeContext
from app.authz.permissions import Permission, permissions_for
from app.models import (
    BranchMembership,
    ChangeProposal,
    ChangeProposalItem,
    TreeMembership,
    TreeVocabularyTerm,
    User,
    UserNotification,
)
from app.models.enums import NotificationKind, Role
from app.modules.genealogy import lookup

TEXT = {
    NotificationKind.PROPOSAL_TO_REVIEW: "{actor} proposed {n} change(s) to {person} for review.",
    NotificationKind.PROPOSAL_ACCEPTED: "Your proposed change to {person} was accepted.",
    NotificationKind.PROPOSAL_REJECTED: "Your proposed change to {person} was not accepted.",
    NotificationKind.PROPOSAL_STALE: "Your proposed change to {person} is out of date: the record changed first.",
    NotificationKind.CHALLENGE_OPENED: "{actor} challenged a fact about {person}.",
    NotificationKind.CHALLENGE_UPHELD: "Your challenge about {person} was upheld.",
    NotificationKind.CHALLENGE_DISMISSED: "Your challenge about {person} was dismissed.",
    NotificationKind.PROPOSAL_COMMENT: "{actor} commented on a proposed change to {person}.",
    NotificationKind.OFFER_ACCEPTED: "Your family's entry “{label}” was added to the common suggestions.",
    NotificationKind.OFFER_DECLINED: "Your family's entry “{label}” was not added to the common suggestions.",
}


def reviewers_for(
    ctx: TreeContext, people: Iterable[uuid.UUID], exclude: uuid.UUID | None
) -> list[uuid.UUID]:
    """Members with change.review over every person concerned."""
    people = [p for p in people if p]
    out = []
    for m in ctx.db.scalars(select(TreeMembership).where(TreeMembership.tree_id == ctx.tree_id)):
        if m.user_id == exclude:
            continue
        roles = frozenset(Role(r) for r in m.roles)
        if Permission.CHANGE_REVIEW not in permissions_for(roles):
            continue
        admin = bool(roles & {Role.OWNER, Role.FAMILY_ADMIN})
        if not admin and m.branch_id is not None:
            branch = set(
                ctx.db.scalars(
                    select(BranchMembership.person_id).where(
                        BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == m.branch_id
                    )
                )
            )
            if any(p not in branch for p in people):
                continue
        out.append(m.user_id)
    return out


def send(
    ctx: TreeContext, user_ids: Iterable[uuid.UUID], kind: NotificationKind, proposal_id: uuid.UUID | None
) -> None:
    for uid in dict.fromkeys(u for u in user_ids if u):
        ctx.db.add(
            UserNotification(
                tree_id=ctx.tree_id,
                user_id=uid,
                kind=kind,
                proposal_id=proposal_id,
                actor_id=ctx.user_id,
                created_by=ctx.user_id,
            )
        )


def _text(
    ctx: TreeContext,
    n: UserNotification,
    proposals: dict[uuid.UUID, ChangeProposal],
    counts: dict[uuid.UUID, int],
    names: dict[uuid.UUID, str],
) -> str:
    p = proposals.get(n.proposal_id) if n.proposal_id else None
    person = "someone in the tree"
    if p is not None and p.person_id is not None:
        visible = lookup.visible_subjects(ctx, [p.person_id])
        if p.person_id in visible:
            person = visible[p.person_id].person.preferred_display_name or person
    actor = names.get(n.actor_id, "A family member") if n.actor_id else "A family member"
    label = "an entry"
    if n.subject_id is not None and n.kind in (
        NotificationKind.OFFER_ACCEPTED,
        NotificationKind.OFFER_DECLINED,
    ):
        term = ctx.db.get(TreeVocabularyTerm, n.subject_id)
        label = term.label if term is not None and term.tree_id == ctx.tree_id else label
    return TEXT[n.kind].format(
        actor=actor, person=person, label=label, n=counts.get(n.proposal_id, 1) if n.proposal_id else 1
    )


def list_for(ctx: TreeContext, offset: int, limit: int) -> tuple[list[dict[str, Any]], int, bool]:
    if ctx.user_id is None:
        return [], 0, False
    base = select(UserNotification).where(
        UserNotification.tree_id == ctx.tree_id, UserNotification.user_id == ctx.user_id
    )
    rows = list(
        ctx.db.scalars(base.order_by(UserNotification.created_at.desc()).offset(offset).limit(limit + 1))
    )
    unread = (
        ctx.db.scalar(
            select(func.count())
            .select_from(UserNotification)
            .where(
                UserNotification.tree_id == ctx.tree_id,
                UserNotification.user_id == ctx.user_id,
                UserNotification.read_at.is_(None),
            )
        )
        or 0
    )
    page = rows[:limit]
    pids = {n.proposal_id for n in page if n.proposal_id}
    proposals = (
        {p.id: p for p in ctx.db.scalars(select(ChangeProposal).where(ChangeProposal.id.in_(pids)))}
        if pids
        else {}
    )
    counts = (
        dict(
            ctx.db.execute(
                select(ChangeProposalItem.proposal_id, func.count())
                .where(ChangeProposalItem.proposal_id.in_(pids))
                .group_by(ChangeProposalItem.proposal_id)
            ).all()
        )
        if pids
        else {}
    )
    actors = {n.actor_id for n in page if n.actor_id}
    names = (
        dict(
            ctx.db.execute(
                select(User.id, User.display_name)
                .join(TreeMembership, TreeMembership.user_id == User.id)
                .where(TreeMembership.tree_id == ctx.tree_id, User.id.in_(actors))
            ).all()
        )
        if actors
        else {}
    )
    items = [
        {
            "id": n.id,
            "kind": n.kind,
            "proposal_id": n.proposal_id,
            "text": _text(ctx, n, proposals, counts, names),
            "created_at": n.created_at,
            "read": n.read_at is not None,
        }
        for n in page
    ]
    return items, unread, len(rows) > limit


def mark_read(ctx: TreeContext, ids: list[uuid.UUID]) -> None:
    stmt = update(UserNotification).where(
        UserNotification.tree_id == ctx.tree_id,
        UserNotification.user_id == ctx.user_id,
        UserNotification.read_at.is_(None),
    )
    if ids:
        stmt = stmt.where(UserNotification.id.in_(ids))
    ctx.db.execute(stmt.values(read_at=dt.datetime.now(dt.UTC)))
