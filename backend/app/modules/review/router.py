"""Change proposals, challenges, review state, history, revert and notifications (ADR-0021 §9)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.api.deps import TreeCtx
from app.api.schemas import Page, decode_cursor, encode_cursor
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Forbidden
from app.core.ratelimit import enforce
from app.models import (
    ChangeProposal,
    ChangeProposalItem,
    ProposalCitation,
    ProposalComment,
    TreeMembership,
    User,
)
from app.models.enums import ChangeProposalStatus, ReviewState
from app.modules.genealogy import lookup
from app.modules.review import duplicates, history, notify, policy, redaction, service
from app.modules.review.schemas import (
    ChallengeIn,
    CommentIn,
    CommentOut,
    DecisionIn,
    DuplicateCheckIn,
    DuplicateCheckOut,
    NotificationsOut,
    NotificationsReadIn,
    ProposalIn,
    ProposalItemOut,
    ProposalOut,
    ProposalSummary,
    RejectIn,
    RevertOut,
    ReviewPolicyIn,
    ReviewStateIn,
    ReviewStateOut,
    RevisionOut,
    UpholdIn,
    UserRef,
)

router = APIRouter(prefix="/trees/{tree_id}", tags=["review"])


def _users(ctx: TreeCtx, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, UserRef]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = ctx.db.execute(
        select(User.id, User.display_name)
        .join(TreeMembership, TreeMembership.user_id == User.id)
        .where(TreeMembership.tree_id == ctx.tree_id, User.id.in_(ids))
    ).all()
    return {uid: UserRef(id=uid, display_name=name) for uid, name in rows}


def _person_label(ctx: TreeCtx, pid: uuid.UUID | None) -> str | None:
    if pid is None:
        return None
    visible = lookup.visible_subjects(ctx, [pid])
    return visible[pid].person.preferred_display_name if pid in visible else None


def _item_label(item: ChangeProposalItem) -> str:
    verb = {"create": "Add", "update": "Change", "delete": "Remove"}[item.op.value]
    return f"{verb} {item.target_type.value.replace('_', ' ')}"


def _out(ctx: TreeCtx, p: ChangeProposal) -> ProposalOut:
    items = service.items_of(ctx, p.id)
    comments = list(
        ctx.db.scalars(
            select(ProposalComment)
            .where(ProposalComment.tree_id == ctx.tree_id, ProposalComment.proposal_id == p.id)
            .order_by(ProposalComment.created_at)
        )
    )
    users = _users(ctx, {p.proposer_id, p.decided_by} | {c.author_id for c in comments})
    out_items = []
    for i in items:
        changes, outdated = redaction.diff_item(ctx, i)
        out_items.append(
            ProposalItemOut(
                id=i.id,
                target_type=i.target_type,
                op=i.op,
                target_id=i.target_id,
                person_id=i.person_id,
                label=_item_label(i),
                changes=changes,  # type: ignore[arg-type]
                outdated=outdated,
            )
        )
    why = service.decide_blockers(ctx, p)
    sources = list(
        ctx.db.scalars(
            select(ProposalCitation.source_id).where(
                ProposalCitation.tree_id == ctx.tree_id, ProposalCitation.proposal_id == p.id
            )
        )
    )
    mine = ctx.user_id is not None and p.proposer_id == ctx.user_id
    return ProposalOut(
        id=p.id,
        kind=p.kind,
        status=p.status,
        rationale=p.rationale,
        proposer=users.get(p.proposer_id) if p.proposer_id else None,
        person_id=p.person_id,
        person_label=_person_label(ctx, p.person_id),
        target_type=p.target_type,
        target_id=p.target_id,
        created_at=p.created_at,
        submitted_at=p.submitted_at,
        decided_by=users.get(p.decided_by) if p.decided_by else None,
        decided_at=p.decided_at,
        decision_note=p.decision_note,
        stale_reason=p.stale_reason,
        supersedes_id=p.supersedes_id,
        source_ids=sources,
        items=out_items,
        comments=[
            CommentOut(
                id=c.id,
                author=users.get(c.author_id) if c.author_id else None,
                body=c.body,
                created_at=c.created_at,
            )
            for c in comments
        ],
        can_decide=why is None,
        cannot_decide_reason=why if p.status == ChangeProposalStatus.AWAITING_REVIEW else None,
        can_withdraw=mine and p.status in (*service.OPEN, ChangeProposalStatus.STALE),
        can_rebase=mine and p.status == ChangeProposalStatus.STALE,
    )


def _stale_response(ctx: TreeCtx, p: ChangeProposal) -> Any:
    if p.status == ChangeProposalStatus.STALE:
        # the stale status is committed; the reviewer learns nothing was applied
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "proposal_stale",
                    "message": p.stale_reason or "The records changed after this proposal was made.",
                    "details": {"proposal_id": str(p.id)},
                }
            },
        )
    return _out(ctx, p)


# ------------------------------------------------------------------ policy
@router.put("/review-policy", response_model=ReviewPolicyIn)
def set_review_policy(body: ReviewPolicyIn, ctx: TreeCtx) -> ReviewPolicyIn:
    ctx.require(Permission.TREE_MANAGE)
    old = ctx.tree.review_policy
    ctx.tree.review_policy = body.review_policy
    audit.log(
        ctx,
        "tree.review_policy_changed",
        target_type="tree",
        target_id=ctx.tree_id,
        details={"from": old.value, "to": body.review_policy.value},
    )
    return ReviewPolicyIn(review_policy=ctx.tree.review_policy)


# ------------------------------------------------------------------ proposals
@router.post("/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def create_proposal(body: ProposalIn, ctx: TreeCtx) -> ProposalOut:
    ctx.require(Permission.TREE_READ)
    return _out(ctx, service.create_proposal(ctx, body))


@router.get("/proposals", response_model=Page[ProposalSummary])
def list_proposals(
    ctx: TreeCtx,
    view: str = Query(default="to_review", pattern="^(to_review|mine|closed|all)$"),
    person_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> Page[ProposalSummary]:
    offset = decode_cursor(cursor)
    stmt = select(ChangeProposal).where(ChangeProposal.tree_id == ctx.tree_id)
    if view == "to_review":
        stmt = stmt.where(ChangeProposal.status == ChangeProposalStatus.AWAITING_REVIEW)
    elif view == "mine":
        stmt = stmt.where(ChangeProposal.proposer_id == ctx.user_id)
    elif view == "closed":
        stmt = stmt.where(ChangeProposal.status.notin_(service.OPEN))
    if person_id is not None:
        stmt = stmt.where(ChangeProposal.person_id == person_id)
    rows = [
        p for p in ctx.db.scalars(stmt.order_by(ChangeProposal.created_at.desc())) if service.may_view(ctx, p)
    ]
    if view == "to_review":
        rows = [
            p
            for p in rows
            if p.proposer_id != ctx.user_id and policy.can_review(ctx, service.people_of(ctx, p))
        ]
    page = rows[offset : offset + limit]
    counts = (
        dict(
            ctx.db.execute(
                select(ChangeProposalItem.proposal_id, func.count())
                .where(
                    ChangeProposalItem.tree_id == ctx.tree_id,
                    ChangeProposalItem.proposal_id.in_([p.id for p in page]),
                )
                .group_by(ChangeProposalItem.proposal_id)
            ).all()
        )
        if page
        else {}
    )
    users = _users(ctx, {p.proposer_id for p in page})
    return Page(
        items=[
            ProposalSummary(
                id=p.id,
                kind=p.kind,
                status=p.status,
                proposer=users.get(p.proposer_id) if p.proposer_id else None,
                person_id=p.person_id,
                person_label=_person_label(ctx, p.person_id),
                item_count=counts.get(p.id, 0),
                created_at=p.created_at,
                submitted_at=p.submitted_at,
                decided_at=p.decided_at,
            )
            for p in page
        ],
        next_cursor=encode_cursor(offset + limit) if len(rows) > offset + limit else None,
    )


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: uuid.UUID, ctx: TreeCtx) -> ProposalOut:
    return _out(ctx, service.get_proposal(ctx, proposal_id))


@router.post("/proposals/{proposal_id}/submit", response_model=ProposalOut)
def submit_proposal(proposal_id: uuid.UUID, ctx: TreeCtx) -> ProposalOut:
    return _out(ctx, service.submit(ctx, proposal_id))


@router.post("/proposals/{proposal_id}/withdraw", response_model=ProposalOut)
def withdraw_proposal(proposal_id: uuid.UUID, ctx: TreeCtx) -> ProposalOut:
    return _out(ctx, service.withdraw(ctx, proposal_id))


@router.post(
    "/proposals/{proposal_id}/approve", response_model=ProposalOut, responses={409: {"description": "Stale"}}
)
def approve_proposal(proposal_id: uuid.UUID, body: DecisionIn, ctx: TreeCtx) -> Any:
    return _stale_response(ctx, service.approve(ctx, proposal_id, body.note))


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
def reject_proposal(proposal_id: uuid.UUID, body: RejectIn, ctx: TreeCtx) -> ProposalOut:
    return _out(ctx, service.reject(ctx, proposal_id, body.note))


@router.post(
    "/proposals/{proposal_id}/rebase", response_model=ProposalOut, status_code=status.HTTP_201_CREATED
)
def rebase_proposal(proposal_id: uuid.UUID, ctx: TreeCtx) -> ProposalOut:
    return _out(ctx, service.rebase(ctx, proposal_id))


@router.post(
    "/proposals/{proposal_id}/comments", response_model=ProposalOut, status_code=status.HTTP_201_CREATED
)
def comment(proposal_id: uuid.UUID, body: CommentIn, ctx: TreeCtx) -> ProposalOut:
    service.add_comment(ctx, proposal_id, body.body)
    return _out(ctx, service.get_proposal(ctx, proposal_id))


# ------------------------------------------------------------------ challenges
@router.post("/challenges", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def create_challenge(body: ChallengeIn, ctx: TreeCtx) -> ProposalOut:
    ctx.require(Permission.TREE_READ)
    return _out(ctx, service.create_challenge(ctx, body))


@router.post(
    "/proposals/{proposal_id}/uphold", response_model=ProposalOut, responses={409: {"description": "Stale"}}
)
def uphold(proposal_id: uuid.UUID, body: UpholdIn, ctx: TreeCtx) -> Any:
    return _stale_response(ctx, service.uphold(ctx, proposal_id, body.note, body.mark_disputed))


@router.post("/proposals/{proposal_id}/dismiss", response_model=ProposalOut)
def dismiss(proposal_id: uuid.UUID, body: RejectIn, ctx: TreeCtx) -> ProposalOut:
    return _out(ctx, service.dismiss(ctx, proposal_id, body.note))


@router.post("/review-state", response_model=ReviewStateOut)
def set_review_state(body: ReviewStateIn, ctx: TreeCtx) -> ReviewStateOut:
    rec = service.set_review_state(ctx, body.target_type, body.target_id, ReviewState(body.state))
    return ReviewStateOut(
        target_type=body.target_type,
        target_id=body.target_id,
        review_state=rec.review_state,
        review_state_at=rec.review_state_at,
    )


# ------------------------------------------------------------------ history and revert
@router.get("/people/{person_id}/history", response_model=Page[RevisionOut])
def person_history(
    person_id: uuid.UUID,
    ctx: TreeCtx,
    cursor: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> Page[RevisionOut]:
    offset = decode_cursor(cursor)
    items, more = history.person_history(ctx, person_id, offset, limit)
    return Page(
        items=[RevisionOut(**i) for i in items], next_cursor=encode_cursor(offset + limit) if more else None
    )


@router.post("/revisions/{revision_id}/revert", response_model=RevertOut)
def revert(revision_id: uuid.UUID, ctx: TreeCtx) -> RevertOut:
    if not (
        ctx.has(Permission.PERSON_WRITE)
        or ctx.has(Permission.RELATIONSHIP_WRITE)
        or ctx.has(Permission.ASSERTION_WRITE)
    ):
        raise Forbidden()
    outcome, pid = service.revert(ctx, revision_id)
    return RevertOut(outcome=outcome, proposal_id=pid)  # type: ignore[arg-type]


# ------------------------------------------------------------------ notifications
@router.get("/notifications", response_model=NotificationsOut)
def notifications(
    ctx: TreeCtx, cursor: str | None = None, limit: int = Query(default=30, ge=1, le=100)
) -> NotificationsOut:
    offset = decode_cursor(cursor)
    items, unread, more = notify.list_for(ctx, offset, limit)
    return NotificationsOut(
        items=items, unread=unread, next_cursor=encode_cursor(offset + limit) if more else None
    )  # type: ignore[arg-type]


@router.post("/notifications/read", response_model=NotificationsOut)
def notifications_read(body: NotificationsReadIn, ctx: TreeCtx) -> NotificationsOut:
    notify.mark_read(ctx, body.ids)
    ctx.db.flush()
    items, unread, more = notify.list_for(ctx, 0, 30)
    return NotificationsOut(items=items, unread=unread, next_cursor=encode_cursor(30) if more else None)  # type: ignore[arg-type]


# ------------------------------------------------------------------ duplicates at entry
@router.post("/duplicates/check", response_model=DuplicateCheckOut)
def check_duplicates(body: DuplicateCheckIn, ctx: TreeCtx) -> DuplicateCheckOut:
    """Is the person about to be added already in the tree? Visible people only; nothing is merged."""
    ctx.require(Permission.PERSON_WRITE)
    enforce(f"dup-check:{ctx.user_id}", 60)
    found = duplicates.check(
        ctx,
        names=[n.model_dump() for n in body.names],
        birth_year=body.birth_year,
        sex_at_birth=body.sex_at_birth,
        parent_ids=body.parent_ids,
        spouse_ids=body.spouse_ids,
        birth_place_id=body.birth_place_id,
        exclude_ids=body.exclude_ids,
    )
    return DuplicateCheckOut(candidates=found)  # type: ignore[arg-type]
