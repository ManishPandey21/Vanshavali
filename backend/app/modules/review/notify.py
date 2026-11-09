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
    AdminNomination,
    BranchMembership,
    ChangeProposal,
    ChangeProposalItem,
    TreeMembership,
    TreeVocabularyTerm,
    User,
    UserNotification,
)
from app.models.enums import NotificationKind, ReviewTarget, Role
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
    # Family Admin nominations (ADR-0006 amendment of 9 Nov 2026); "{nominee}" is "you" for the nominee
    NotificationKind.NOMINATION_CREATED: "{actor} nominated {nominee} to be a family admin.",
    NotificationKind.NOMINATION_ACCEPTED: "{Nominee} accepted the nomination to be a family admin.",
    NotificationKind.NOMINATION_DECLINED: "{Nominee} declined the nomination to be a family admin.",
    NotificationKind.NOMINATION_APPROVED: "An owner approved the nomination of {nominee} to be a family admin.",
    NotificationKind.NOMINATION_REJECTED: "An owner did not approve the nomination of {nominee} to be a family admin.",
    NotificationKind.NOMINATION_EXPIRED: "The nomination of {nominee} to be a family admin expired.",
    NotificationKind.NOMINATION_LAPSED: "The nomination of {nominee} to be a family admin lapsed.",
    # ADR-0027 §5: the owner's record was narrowed because someone or an event linked to it is private
    NotificationKind.DOCUMENT_NARROWED: "Your document {label} was made more private to protect someone linked to it.",
    NotificationKind.TRADITION_NARROWED: "Your tradition entry {label} was made more private to protect someone linked to it.",
    # ADR-0027 §8.2 takedown; "{label}" is the report's reference, never the record
    NotificationKind.RECORD_REPORTED: "A record was reported ({label}); please review the report.",
    NotificationKind.RECORD_SUSPENDED: "One of your records was suspended after a report ({label}). You can appeal.",
    NotificationKind.SUSPENSION_APPEALED: "An appeal against a suspension needs a decision ({label}).",
    NotificationKind.APPEAL_OVERDUE: "An appeal against a suspension is overdue for a decision ({label}).",
    NotificationKind.SUSPENSION_UPHELD: "The suspension of your record was upheld ({label}); it stays hidden.",
    NotificationKind.SUSPENSION_LIFTED: "The suspension of your record was lifted ({label}).",
    NotificationKind.REPORT_REVIEWED: "Your report {label} was reviewed.",
}
TAKEDOWN_KINDS = frozenset(
    {
        NotificationKind.RECORD_REPORTED,
        NotificationKind.RECORD_SUSPENDED,
        NotificationKind.SUSPENSION_APPEALED,
        NotificationKind.APPEAL_OVERDUE,
        NotificationKind.SUSPENSION_UPHELD,
        NotificationKind.SUSPENSION_LIFTED,
        NotificationKind.REPORT_REVIEWED,
    }
)
NARROWED_KINDS = frozenset({NotificationKind.DOCUMENT_NARROWED, NotificationKind.TRADITION_NARROWED})
NOMINATION_KINDS = frozenset(k for k in NotificationKind if k.value.startswith("nomination_"))


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
    family_records: dict[uuid.UUID, str],
) -> str:
    p = proposals.get(n.proposal_id) if n.proposal_id else None
    person = "someone in the tree"
    if p is not None and p.person_id is None and p.id in family_records:
        person = family_records[p.id]
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
    if n.kind in NARROWED_KINDS:
        label = _record_label(ctx, n)
    if n.kind in TAKEDOWN_KINDS:
        label = _report_reference(ctx, n)
    nominee = "a member"
    if n.kind in NOMINATION_KINDS and n.subject_id is not None:
        nomination = ctx.db.get(AdminNomination, n.subject_id)
        if nomination is not None and nomination.tree_id == ctx.tree_id:
            if nomination.nominee_user_id == n.user_id:
                nominee = "you"
            elif nomination.nominee_user_id is not None:
                user = ctx.db.get(User, nomination.nominee_user_id)
                nominee = user.display_name if user is not None else nominee
    return TEXT[n.kind].format(
        actor=actor,
        person=person,
        label=label,
        nominee=nominee,
        Nominee=nominee[:1].upper() + nominee[1:],
        n=counts.get(n.proposal_id, 1) if n.proposal_id else 1,
    )


def _record_label(ctx: TreeContext, n: UserNotification) -> str:
    """The record's title, quoted, only while the reader may still see it."""
    from app.models import Document, TraditionEntry
    from app.modules.documents.access import can_view_document
    from app.modules.traditions.sharing import entry_allows

    if n.subject_id is None:
        return "(no longer available)"
    if n.kind == NotificationKind.DOCUMENT_NARROWED:
        doc = ctx.db.get(Document, n.subject_id)
        if (
            doc is not None
            and doc.tree_id == ctx.tree_id
            and doc.deleted_at is None
            and can_view_document(ctx, doc)
        ):
            return f"“{doc.title}”"
    else:
        entry = ctx.db.get(TraditionEntry, n.subject_id)
        if entry is not None and entry.tree_id == ctx.tree_id and entry_allows(ctx, entry):
            return f"“{entry.title}”"
    return "(no longer available)"


def _report_reference(ctx: TreeContext, n: UserNotification) -> str:
    """The report's reference: the subject is the report, or the suspension it led to."""
    from app.models import RecordReport, RecordSuspension

    if n.subject_id is None:
        return "a report"
    report_id = n.subject_id
    if n.kind not in (NotificationKind.RECORD_REPORTED, NotificationKind.REPORT_REVIEWED):
        susp = ctx.db.get(RecordSuspension, n.subject_id)
        if susp is None or susp.tree_id != ctx.tree_id:
            return "a report"
        report_id = susp.report_id
    rep = ctx.db.get(RecordReport, report_id)
    return rep.reference if rep is not None and rep.tree_id == ctx.tree_id else "a report"


def subject_for(ctx: TreeContext, n: UserNotification) -> uuid.UUID | None:
    """The record a narrowing notice links to; other kinds expose no subject."""
    return n.subject_id if n.kind in NARROWED_KINDS else None


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
    # proposals about the family as a whole (a tradition, the family's words), ADR-0026
    family_records: dict[uuid.UUID, str] = {}
    if pids:
        for pid, t in ctx.db.execute(
            select(ChangeProposalItem.proposal_id, ChangeProposalItem.target_type).where(
                ChangeProposalItem.proposal_id.in_(pids),
                ChangeProposalItem.target_type.in_([ReviewTarget.TRADITION, ReviewTarget.KINSHIP_WORD]),
            )
        ).all():
            family_records[pid] = (
                "a family tradition" if t == ReviewTarget.TRADITION else "the family's relationship words"
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
            "subject_id": subject_for(ctx, n),
            "text": _text(ctx, n, proposals, counts, names, family_records),
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
