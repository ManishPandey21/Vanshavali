"""Change proposals, review, challenges and revert (ADR-0021 §2, §4–§6).

A proposal's items are validated by the same request schemas as the direct endpoints and applied
by the same service functions, as the proposer, so a proposal can never do more than its proposer
could. Approval locks every target and compares the revisions the items were based on: any change
in between makes the proposal stale and nothing is applied.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from app.authz.context import TreeContext, load_tree_context
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.ratelimit import enforce
from app.models import (
    ChangeProposal,
    ChangeProposalItem,
    ProposalCitation,
    ProposalComment,
    RecordRevision,
    Source,
    TreeMembership,
    User,
)
from app.models.enums import (
    AssertionSubject,
    ChangeProposalStatus,
    EvidenceStatus,
    NotificationKind,
    ProposalKind,
    ProposalOp,
    ReviewState,
    ReviewTarget,
)
from app.modules.genealogy import lookup
from app.modules.genealogy import service as genealogy
from app.modules.genealogy.schemas import (
    EventIn,
    EventUpdate,
    NameIn,
    NameUpdate,
    PersonUpdate,
    RelationshipIn,
    RelationshipUpdate,
)
from app.modules.heritage import service as heritage
from app.modules.heritage.schemas import AssertionIn, AssertionUpdate
from app.modules.review import notify, policy, redaction
from app.modules.review.revisions import MODEL_FOR, applying
from app.modules.review.schemas import ChallengeIn, ProposalIn, ProposalItemIn

PROPOSALS_PER_MINUTE = 20
MAX_OPEN_CHALLENGES = 20
OPEN = (ChangeProposalStatus.DRAFT, ChangeProposalStatus.AWAITING_REVIEW)

# (target type, op) -> request schema of the direct endpoint
SCHEMAS: dict[tuple[ReviewTarget, ProposalOp], type[BaseModel] | None] = {
    (ReviewTarget.PERSON, ProposalOp.UPDATE): PersonUpdate,
    (ReviewTarget.PERSON, ProposalOp.DELETE): None,
    (ReviewTarget.NAME, ProposalOp.CREATE): NameIn,
    (ReviewTarget.NAME, ProposalOp.UPDATE): NameUpdate,
    (ReviewTarget.NAME, ProposalOp.DELETE): None,
    (ReviewTarget.EVENT, ProposalOp.CREATE): EventIn,
    (ReviewTarget.EVENT, ProposalOp.UPDATE): EventUpdate,
    (ReviewTarget.EVENT, ProposalOp.DELETE): None,
    (ReviewTarget.RELATIONSHIP, ProposalOp.CREATE): RelationshipIn,
    (ReviewTarget.RELATIONSHIP, ProposalOp.UPDATE): RelationshipUpdate,
    (ReviewTarget.RELATIONSHIP, ProposalOp.DELETE): None,
    (ReviewTarget.ASSERTION, ProposalOp.CREATE): AssertionIn,
    (ReviewTarget.ASSERTION, ProposalOp.UPDATE): AssertionUpdate,
    (ReviewTarget.ASSERTION, ProposalOp.DELETE): None,
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _key(t: ReviewTarget, rid: uuid.UUID) -> str:
    return f"{t.value}:{rid}"


# ------------------------------------------------------------------ validating items
@dataclass
class Resolved:
    """What an item touches: its people, the revisions it binds to, and the parsed patch."""

    people: list[uuid.UUID]
    base: dict[str, int]
    body: BaseModel | None
    record: Any | None


def _parse(t: ReviewTarget, op: ProposalOp, patch: dict[str, Any]) -> BaseModel | None:
    if (t, op) not in SCHEMAS:
        raise Unprocessable(f"Cannot propose {op.value} of a {t.value}")
    schema = SCHEMAS[(t, op)]
    if schema is None:
        if patch:
            raise Unprocessable("A delete carries no values")
        return None
    try:
        return schema.model_validate(patch)
    except ValidationError as exc:
        raise Unprocessable(
            "The proposed values are not valid",
            details=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()],
        ) from exc


def _person_rev(ctx: TreeContext, pid: uuid.UUID) -> dict[str, int]:
    return {_key(ReviewTarget.PERSON, pid): lookup.get_person(ctx, pid).revision}


def resolve_item(ctx: TreeContext, item: ProposalItemIn) -> Resolved:
    """Check the proposer could make this change, and bind it to the current revisions."""
    t, op = item.target_type, item.op
    body = _parse(t, op, item.patch)
    if op != ProposalOp.CREATE and item.target_id is None:
        raise Unprocessable("target_id is required to change or delete a record")
    if t == ReviewTarget.PERSON:
        p = lookup.get_person(ctx, item.target_id)  # type: ignore[arg-type]
        ctx.require(Permission.PERSON_WRITE, person_id=p.id)
        return Resolved([p.id], {_key(t, p.id): p.revision}, body, p)
    if t == ReviewTarget.NAME:
        if op == ProposalOp.CREATE:
            if item.person_id is None:
                raise Unprocessable("person_id is required to add a name")
            ctx.require(Permission.PERSON_WRITE, person_id=item.person_id)
            return Resolved([item.person_id], _person_rev(ctx, item.person_id), body, None)
        n = lookup.get_name(ctx, item.target_id)  # type: ignore[arg-type]
        lookup.get_person(ctx, n.person_id)
        ctx.require(Permission.PERSON_WRITE, person_id=n.person_id)
        return Resolved([n.person_id], {_key(t, n.id): n.revision}, body, n)
    if t == ReviewTarget.EVENT:
        if op == ProposalOp.CREATE:
            assert isinstance(body, EventIn)  # noqa: S101 -- guaranteed by SCHEMAS
            people = sorted({p.person_id for p in body.participants}, key=str)
            base: dict[str, int] = {}
            for pid in people:
                ctx.require(Permission.PERSON_WRITE, person_id=pid)
                base |= _person_rev(ctx, pid)
            return Resolved(people, base, body, None)
        e, principal = genealogy.get_event_checked(ctx, item.target_id)  # type: ignore[arg-type]
        ctx.require(Permission.PERSON_WRITE, person_id=principal)
        return Resolved([p for p in [principal] if p], {_key(t, e.id): e.revision}, body, e)
    if t == ReviewTarget.RELATIONSHIP:
        if op == ProposalOp.CREATE:
            assert isinstance(body, RelationshipIn)  # noqa: S101 -- guaranteed by SCHEMAS
            a, b = body.person_a_id, body.person_b_id
            base = _person_rev(ctx, a) | _person_rev(ctx, b)
            genealogy._require_rel_write(ctx, a, b)
            return Resolved([a, b], base, body, None)
        rel = lookup.get_relationship(ctx, item.target_id)  # type: ignore[arg-type]
        lookup.get_person(ctx, rel.person_a_id)
        lookup.get_person(ctx, rel.person_b_id)
        genealogy._require_rel_write(ctx, rel.person_a_id, rel.person_b_id)
        return Resolved([rel.person_a_id, rel.person_b_id], {_key(t, rel.id): rel.revision}, body, rel)
    # assertions: person subjects (branch heritage is edited by family writers directly)
    if op == ProposalOp.CREATE:
        if item.person_id is None:
            raise Unprocessable("person_id is required to add a heritage claim")
        ctx.require(Permission.ASSERTION_WRITE, person_id=item.person_id)
        return Resolved([item.person_id], _person_rev(ctx, item.person_id), body, None)
    claim, _ = heritage.get_assertion(ctx, _need(item.target_id))  # type: ignore[arg-type]
    if claim.subject_type != AssertionSubject.PERSON or claim.person_id is None:
        raise Unprocessable("Only a person's heritage claims can be proposed")
    ctx.require(Permission.ASSERTION_WRITE, person_id=claim.person_id)
    return Resolved([claim.person_id], {_key(t, claim.id): claim.revision}, body, claim)


def _patch_json(body: BaseModel | None, op: ProposalOp) -> dict[str, Any]:
    if body is None:
        return {}
    return body.model_dump(mode="json", exclude_unset=op == ProposalOp.UPDATE)


def _sources(ctx: TreeContext, ids: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    out = []
    for sid in dict.fromkeys(ids):
        lookup.get_in_tree(ctx, Source, sid, "Source")
        out.append(sid)
    return out


def _add_items(ctx: TreeContext, proposal: ChangeProposal, items: list[ProposalItemIn]) -> list[uuid.UUID]:
    people: list[uuid.UUID] = []
    for pos, item in enumerate(items):
        r = resolve_item(ctx, item)
        people += r.people
        ctx.db.add(
            ChangeProposalItem(
                tree_id=ctx.tree_id,
                proposal_id=proposal.id,
                position=pos,
                target_type=item.target_type,
                op=item.op,
                target_id=item.target_id,
                person_id=item.person_id or (r.people[0] if r.people else None),
                patch=_patch_json(r.body, item.op),
                base_revisions=r.base,
                created_by=ctx.user_id,
            )
        )
    return people


def create_proposal(ctx: TreeContext, body: ProposalIn) -> ChangeProposal:
    if ctx.user_id is None:
        raise Forbidden()
    enforce(f"proposal:{ctx.user_id}", PROPOSALS_PER_MINUTE)
    if body.submit and not body.rationale.strip():
        raise Unprocessable("Say why this change is right before sending it for review")
    proposal = ChangeProposal(
        tree_id=ctx.tree_id,
        proposer_id=ctx.user_id,
        kind=ProposalKind.CHANGE,
        status=ChangeProposalStatus.DRAFT,
        rationale=body.rationale.strip(),
        created_by=ctx.user_id,
    )
    ctx.db.add(proposal)
    ctx.db.flush()
    people = _add_items(ctx, proposal, body.items)
    proposal.person_id = people[0] if people else None
    for sid in _sources(ctx, body.source_ids):
        ctx.db.add(
            ProposalCitation(
                tree_id=ctx.tree_id, proposal_id=proposal.id, source_id=sid, created_by=ctx.user_id
            )
        )
    audit.log(
        ctx,
        "proposal.created",
        target_type="change_proposal",
        target_id=proposal.id,
        details={"items": len(body.items)},
    )
    if body.submit:
        submit(ctx, proposal.id)
    ctx.db.flush()
    return proposal


def create_challenge(ctx: TreeContext, body: ChallengeIn) -> ChangeProposal:
    if ctx.user_id is None:
        raise Forbidden()
    enforce(f"proposal:{ctx.user_id}", PROPOSALS_PER_MINUTE)
    open_count = ctx.db.scalar(
        select(func.count())
        .select_from(ChangeProposal)
        .where(
            ChangeProposal.tree_id == ctx.tree_id,
            ChangeProposal.proposer_id == ctx.user_id,
            ChangeProposal.kind == ProposalKind.CHALLENGE,
            ChangeProposal.status.in_(OPEN),
        )
    )
    if (open_count or 0) >= MAX_OPEN_CHALLENGES:
        raise Conflict(
            f"You already have {MAX_OPEN_CHALLENGES} open challenges in this tree; wait for a reviewer",
            code="too_many_challenges",
        )
    record, people = target_record(ctx, body.target_type, body.target_id)  # any member who can see it
    proposal = ChangeProposal(
        tree_id=ctx.tree_id,
        proposer_id=ctx.user_id,
        kind=ProposalKind.CHALLENGE,
        status=ChangeProposalStatus.DRAFT,
        rationale=body.rationale.strip(),
        person_id=people[0] if people else None,
        target_type=body.target_type,
        target_id=body.target_id,
        created_by=ctx.user_id,
    )
    ctx.db.add(proposal)
    ctx.db.flush()
    if body.items:
        _add_items(ctx, proposal, body.items)  # a correction: only what the challenger could change
    for sid in _sources(ctx, body.source_ids):
        ctx.db.add(
            ProposalCitation(
                tree_id=ctx.tree_id, proposal_id=proposal.id, source_id=sid, created_by=ctx.user_id
            )
        )
    audit.log(ctx, "challenge.created", target_type="change_proposal", target_id=proposal.id)
    submit(ctx, proposal.id)
    creator = getattr(record, "created_by", None)
    if creator and creator != ctx.user_id:
        notify.send(ctx, [creator], NotificationKind.CHALLENGE_OPENED, proposal.id)
    return proposal


def target_record(ctx: TreeContext, t: ReviewTarget, rid: uuid.UUID) -> tuple[Any, list[uuid.UUID]]:
    """A reviewable record the reader can see, and the people it belongs to."""
    if t == ReviewTarget.PERSON:
        p = lookup.get_person(ctx, rid)
        return p, [p.id]
    if t == ReviewTarget.NAME:
        n = lookup.get_name(ctx, rid)
        lookup.get_person(ctx, n.person_id)
        return n, [n.person_id]
    if t == ReviewTarget.EVENT:
        e, principal = genealogy.get_event_checked(ctx, rid)
        return e, [p for p in [principal] if p]
    if t == ReviewTarget.RELATIONSHIP:
        rel = lookup.get_relationship(ctx, rid)
        lookup.get_person(ctx, rel.person_a_id)
        lookup.get_person(ctx, rel.person_b_id)
        return rel, [rel.person_a_id, rel.person_b_id]
    a, _subject = heritage.get_assertion(ctx, rid)
    if a.person_id is not None:
        lookup.get_person(ctx, a.person_id)
    return a, [p for p in [a.person_id] if p]


# ------------------------------------------------------------------ lifecycle
def get_proposal(ctx: TreeContext, proposal_id: uuid.UUID) -> ChangeProposal:
    p = lookup.get_in_tree(ctx, ChangeProposal, proposal_id, "Proposal")
    if not may_view(ctx, p):
        raise NotFound("Proposal not found")
    return p


def items_of(ctx: TreeContext, proposal_id: uuid.UUID) -> list[ChangeProposalItem]:
    return list(
        ctx.db.scalars(
            select(ChangeProposalItem)
            .where(ChangeProposalItem.tree_id == ctx.tree_id, ChangeProposalItem.proposal_id == proposal_id)
            .order_by(ChangeProposalItem.position)
        )
    )


def people_of(ctx: TreeContext, p: ChangeProposal) -> list[uuid.UUID]:
    people = {i.person_id for i in items_of(ctx, p.id) if i.person_id}
    for i in items_of(ctx, p.id):
        if i.target_type == ReviewTarget.RELATIONSHIP and i.op == ProposalOp.CREATE:
            people |= {uuid.UUID(i.patch["person_a_id"]), uuid.UUID(i.patch["person_b_id"])}
    if p.person_id:
        people.add(p.person_id)
    return sorted(people, key=str)


def may_view(ctx: TreeContext, p: ChangeProposal) -> bool:
    """The proposer, those who may review it, and (for a challenge) members who can see the fact."""
    if ctx.user_id is not None and p.proposer_id == ctx.user_id:
        return True
    people = people_of(ctx, p)
    if policy.can_review(ctx, people):
        return True
    if p.kind == ProposalKind.CHALLENGE and p.target_type and p.target_id:
        try:
            target_record(ctx, p.target_type, p.target_id)
            return True
        except NotFound:
            return False
    return False


def submit(ctx: TreeContext, proposal_id: uuid.UUID) -> ChangeProposal:
    p = lookup.get_in_tree(ctx, ChangeProposal, proposal_id, "Proposal")
    if p.proposer_id != ctx.user_id:
        raise NotFound("Proposal not found")
    if p.status != ChangeProposalStatus.DRAFT:
        raise Conflict("Only a draft can be sent for review", code="proposal_not_draft")
    if p.kind == ProposalKind.CHANGE and not p.rationale.strip():
        raise Unprocessable("Say why this change is right before sending it for review")
    p.status = ChangeProposalStatus.AWAITING_REVIEW
    p.submitted_at = _now()
    ctx.db.flush()
    reviewers = notify.reviewers_for(ctx, people_of(ctx, p), exclude=ctx.user_id)
    notify.send(ctx, reviewers, NotificationKind.PROPOSAL_TO_REVIEW, p.id)
    audit.log(ctx, "proposal.submitted", target_type="change_proposal", target_id=p.id)
    return p


def withdraw(ctx: TreeContext, proposal_id: uuid.UUID) -> ChangeProposal:
    p = get_proposal(ctx, proposal_id)
    if p.proposer_id != ctx.user_id:
        raise Forbidden("Only the proposer can withdraw a proposal")
    if p.status not in OPEN and p.status != ChangeProposalStatus.STALE:
        raise Conflict("This proposal has already been decided", code="proposal_decided")
    p.status = ChangeProposalStatus.WITHDRAWN
    audit.log(ctx, "proposal.withdrawn", target_type="change_proposal", target_id=p.id)
    return p


def decide_blockers(ctx: TreeContext, p: ChangeProposal) -> str | None:
    """Why the reader may not decide this proposal, or None."""
    if ctx.user_id is None or p.proposer_id == ctx.user_id:
        return "You cannot review your own proposal."
    if p.status != ChangeProposalStatus.AWAITING_REVIEW:
        return "This proposal is not awaiting review."
    if not policy.can_review(ctx, people_of(ctx, p)):
        return "You may not review changes to everyone this proposal touches."
    if any(redaction.item_has_hidden(ctx, i) for i in items_of(ctx, p.id)):
        return "Part of this change is hidden from you; someone who can see it must decide."
    return None


def _require_decide(ctx: TreeContext, p: ChangeProposal) -> None:
    why = decide_blockers(ctx, p)
    if why:
        if p.proposer_id == ctx.user_id and ctx.user_id is not None:
            raise Forbidden(why, code="self_approval")
        raise Forbidden(why)


def _lock_and_check(ctx: TreeContext, items: list[ChangeProposalItem]) -> str | None:
    """Lock every record the items depend on and compare revisions; return why it is stale."""
    for item in items:
        for key, rev in sorted(item.base_revisions.items()):
            tname, _, rid = key.partition(":")
            model: Any = MODEL_FOR[ReviewTarget(tname)]
            rec = ctx.db.scalar(
                select(model)
                .where(model.tree_id == ctx.tree_id, model.id == uuid.UUID(rid))
                .with_for_update()
            )
            if rec is None or getattr(rec, "deleted_at", None) is not None:
                return f"A {tname} this change depends on no longer exists."
            if rec.revision != rev:
                return f"A {tname} this change depends on was changed after the proposal was made."
    return None


def _apply_items(ctx: TreeContext, p: ChangeProposal, items: list[ChangeProposalItem]) -> list[Any]:
    """Apply as the proposer (their rights are checked again by the services), all or nothing."""
    proposer = ctx.db.get(User, p.proposer_id) if p.proposer_id else None
    membership = (
        ctx.db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == ctx.tree_id, TreeMembership.user_id == p.proposer_id
            )
        )
        if proposer
        else None
    )
    if proposer is None or membership is None:
        raise Conflict("The proposer is no longer a member of this tree", code="proposer_gone")
    reviewer_id = ctx.user_id
    pctx = load_tree_context(ctx.db, ctx.tree_id, proposer, ctx.request)
    touched: list[Any] = []
    ctx.db.info[policy.APPLYING] = True
    try:
        with applying(ctx.db, actor_id=proposer.id, proposal_id=p.id, reviewer_id=reviewer_id):  # type: ignore[arg-type]
            for item in items:
                rec = _apply_one(pctx, item)
                if rec is not None:
                    touched.append(rec)
            ctx.db.flush()
    finally:
        ctx.db.info.pop(policy.APPLYING, None)
        ctx.db.info["actor_id"] = reviewer_id
    return touched


def _apply_one(pctx: TreeContext, item: ChangeProposalItem) -> Any:
    """Run the direct service for one item, as the proposer (whose rights the service checks)."""
    body: Any = _parse(item.target_type, item.op, item.patch)
    t, op = item.target_type, item.op
    if op == ProposalOp.CREATE:
        if t == ReviewTarget.NAME:
            return genealogy.add_name(pctx, _need(item.person_id), body)
        if t == ReviewTarget.EVENT:
            return genealogy.create_event(pctx, body)
        if t == ReviewTarget.RELATIONSHIP:
            return genealogy.create_relationship(pctx, body)
        if t == ReviewTarget.ASSERTION:
            return heritage.create_assertion(pctx, AssertionSubject.PERSON, _need(item.person_id), body)
        raise Unprocessable(f"Cannot add a {t.value} by proposal")
    rid = _need(item.target_id)
    if t == ReviewTarget.PERSON:
        if op == ProposalOp.UPDATE:
            return genealogy.update_person(pctx, rid, body)
        genealogy.delete_person(pctx, rid)
        return None
    if t == ReviewTarget.NAME:
        owner = lookup.get_name(pctx, rid).person_id
        if op == ProposalOp.UPDATE:
            return genealogy.update_name(pctx, owner, rid, body)
        genealogy.delete_name(pctx, owner, rid)
        return None
    if t == ReviewTarget.EVENT:
        if op == ProposalOp.UPDATE:
            return genealogy.update_event(pctx, rid, body)
        genealogy.delete_event(pctx, rid)
        return None
    if t == ReviewTarget.RELATIONSHIP:
        if op == ProposalOp.UPDATE:
            return genealogy.update_relationship(pctx, rid, body)
        genealogy.delete_relationship(pctx, rid)
        return None
    if op == ProposalOp.UPDATE:
        return heritage.update_assertion(pctx, rid, body)
    heritage.delete_assertion(pctx, rid)
    return None


def _need(value: uuid.UUID | None) -> uuid.UUID:
    if value is None:
        raise Unprocessable("This item names no record")
    return value


def _mark_reviewed(ctx: TreeContext, records: Iterable[Any], state: ReviewState) -> None:
    now = _now()
    for rec in records:
        if hasattr(rec, "review_state"):
            rec.review_state = state
            rec.review_state_by = ctx.user_id
            rec.review_state_at = now


def mark_stale(ctx: TreeContext, p: ChangeProposal, reason: str) -> None:
    p.status = ChangeProposalStatus.STALE
    p.stale_reason = reason
    if p.proposer_id:
        notify.send(ctx, [p.proposer_id], NotificationKind.PROPOSAL_STALE, p.id)
    audit.log(ctx, "proposal.stale", target_type="change_proposal", target_id=p.id)


def approve(ctx: TreeContext, proposal_id: uuid.UUID, note: str | None) -> ChangeProposal:
    """Apply a change proposal, or mark it stale. The caller reports a stale proposal as 409."""
    p = get_proposal(ctx, proposal_id)
    if p.kind != ProposalKind.CHANGE:
        raise Unprocessable("Decide a challenge with uphold or dismiss")
    _require_decide(ctx, p)
    items = items_of(ctx, p.id)
    stale = _lock_and_check(ctx, items)
    if stale:
        mark_stale(ctx, p, stale)
        return p
    touched = _apply_items(ctx, p, items)
    _mark_reviewed(ctx, touched, ReviewState.FAMILY_REVIEWED)
    p.status = ChangeProposalStatus.ACCEPTED
    p.decided_by, p.decided_at, p.decision_note = ctx.user_id, _now(), note
    if p.proposer_id:
        notify.send(ctx, [p.proposer_id], NotificationKind.PROPOSAL_ACCEPTED, p.id)
    audit.log(
        ctx, "proposal.approved", target_type="change_proposal", target_id=p.id, details={"items": len(items)}
    )
    return p


def reject(ctx: TreeContext, proposal_id: uuid.UUID, note: str) -> ChangeProposal:
    p = get_proposal(ctx, proposal_id)
    if p.kind != ProposalKind.CHANGE:
        raise Unprocessable("Decide a challenge with uphold or dismiss")
    _require_decide(ctx, p)
    p.status = ChangeProposalStatus.REJECTED
    p.decided_by, p.decided_at, p.decision_note = ctx.user_id, _now(), note
    if p.proposer_id:
        notify.send(ctx, [p.proposer_id], NotificationKind.PROPOSAL_REJECTED, p.id)
    audit.log(ctx, "proposal.rejected", target_type="change_proposal", target_id=p.id)
    return p


def uphold(ctx: TreeContext, proposal_id: uuid.UUID, note: str | None, mark_disputed: bool) -> ChangeProposal:
    p = get_proposal(ctx, proposal_id)
    if p.kind != ProposalKind.CHALLENGE or p.target_type is None or p.target_id is None:
        raise Unprocessable("Only a challenge can be upheld")
    _require_decide(ctx, p)
    items = items_of(ctx, p.id)
    stale = _lock_and_check(ctx, items)
    if stale:
        mark_stale(ctx, p, stale)
        return p
    record, _people = target_record(ctx, p.target_type, p.target_id)
    touched = _apply_items(ctx, p, items) if items else []
    if mark_disputed and hasattr(record, "evidence_status"):
        record.evidence_status = EvidenceStatus.DISPUTED
    ctx.db.flush()
    _mark_reviewed(ctx, [record], ReviewState.CONTESTED)
    _mark_reviewed(ctx, [t for t in touched if t is not record], ReviewState.FAMILY_REVIEWED)
    p.status = ChangeProposalStatus.ACCEPTED
    p.decided_by, p.decided_at, p.decision_note = ctx.user_id, _now(), note
    if p.proposer_id:
        notify.send(ctx, [p.proposer_id], NotificationKind.CHALLENGE_UPHELD, p.id)
    audit.log(ctx, "challenge.upheld", target_type="change_proposal", target_id=p.id)
    return p


def dismiss(ctx: TreeContext, proposal_id: uuid.UUID, note: str) -> ChangeProposal:
    p = get_proposal(ctx, proposal_id)
    if p.kind != ProposalKind.CHALLENGE:
        raise Unprocessable("Only a challenge can be dismissed")
    _require_decide(ctx, p)
    p.status = ChangeProposalStatus.REJECTED
    p.decided_by, p.decided_at, p.decision_note = ctx.user_id, _now(), note
    if p.proposer_id:
        notify.send(ctx, [p.proposer_id], NotificationKind.CHALLENGE_DISMISSED, p.id)
    audit.log(ctx, "challenge.dismissed", target_type="change_proposal", target_id=p.id)
    return p


def rebase(ctx: TreeContext, proposal_id: uuid.UUID) -> ChangeProposal:
    """A fresh proposal against today's records; the old approval never carries over (§5)."""
    old = get_proposal(ctx, proposal_id)
    if old.proposer_id != ctx.user_id:
        raise Forbidden("Only the proposer can rebase a proposal")
    if old.status != ChangeProposalStatus.STALE:
        raise Conflict("Only a stale proposal can be rebased", code="proposal_not_stale")
    items = [
        ProposalItemIn(
            target_type=i.target_type, op=i.op, target_id=i.target_id, person_id=i.person_id, patch=i.patch
        )
        for i in items_of(ctx, old.id)
    ]
    if not items:
        raise Conflict("Nothing is left to propose: the records were removed", code="proposal_empty")
    sources = [
        c.source_id
        for c in ctx.db.scalars(
            select(ProposalCitation).where(
                ProposalCitation.tree_id == ctx.tree_id, ProposalCitation.proposal_id == old.id
            )
        )
    ]
    if old.kind == ProposalKind.CHALLENGE and old.target_type and old.target_id:
        new = create_challenge(
            ctx,
            ChallengeIn(
                target_type=old.target_type,
                target_id=old.target_id,
                rationale=old.rationale,
                items=items,
                source_ids=sources,
            ),
        )
    else:
        new = create_proposal(
            ctx, ProposalIn(rationale=old.rationale, items=items, source_ids=sources, submit=True)
        )
    new.supersedes_id = old.id
    old.status = ChangeProposalStatus.WITHDRAWN
    return new


def add_comment(ctx: TreeContext, proposal_id: uuid.UUID, body: str) -> ProposalComment:
    p = get_proposal(ctx, proposal_id)
    enforce(f"proposal-comment:{ctx.user_id}", 30)
    c = ProposalComment(
        tree_id=ctx.tree_id,
        proposal_id=p.id,
        author_id=ctx.user_id,
        body=body.strip(),
        created_by=ctx.user_id,
    )
    ctx.db.add(c)
    ctx.db.flush()
    others = {p.proposer_id} | set(
        ctx.db.scalars(
            select(ProposalComment.author_id).where(
                ProposalComment.tree_id == ctx.tree_id, ProposalComment.proposal_id == p.id
            )
        )
    )
    notify.send(ctx, [u for u in others if u and u != ctx.user_id], NotificationKind.PROPOSAL_COMMENT, p.id)
    return c


def set_review_state(ctx: TreeContext, t: ReviewTarget, rid: uuid.UUID, state: ReviewState) -> Any:
    record, people = target_record(ctx, t, rid)
    if not policy.can_review(ctx, people):
        raise Forbidden("Only reviewers can confirm facts for the family")
    _mark_reviewed(ctx, [record], state)
    audit.log(ctx, "review_state.set", target_type=t.value, target_id=rid, details={"state": state.value})
    return record


# ------------------------------------------------------------------ revert
def revert(ctx: TreeContext, revision_id: uuid.UUID) -> tuple[str, uuid.UUID | None]:
    """Put back the values a revision changed: directly when the reader may, else as a proposal."""
    rev = lookup.get_in_tree(ctx, RecordRevision, revision_id, "Revision")
    if rev.op != ProposalOp.UPDATE:
        raise Unprocessable("Only a change to a record can be reverted")
    record, people = target_record(ctx, rev.record_type, rev.record_id)
    schema = SCHEMAS.get((rev.record_type, ProposalOp.UPDATE))
    if schema is None:
        raise Unprocessable("This change cannot be reverted")
    if redaction.revision_has_hidden(ctx, rev, people):
        raise Forbidden("Part of this change is hidden from you")
    patch = {k: v for k, v in rev.before.items() if k in schema.model_fields}
    if not patch:
        raise Unprocessable("This change cannot be reverted")
    item = ProposalItemIn(
        target_type=rev.record_type, op=ProposalOp.UPDATE, target_id=rev.record_id, patch=patch
    )
    category: policy.Category = (
        "structure" if rev.record_type in (ReviewTarget.RELATIONSHIP, ReviewTarget.ASSERTION) else "all"
    )
    if policy.needs_review(ctx, category, people, [record]):
        p = create_proposal(
            ctx, ProposalIn(rationale=f"Revert to the values before revision {rev.revision}", items=[item])
        )
        return "proposed", p.id
    resolve_item(ctx, item)  # the reader's own rights, as for a direct edit
    _apply_one(
        ctx,
        ChangeProposalItem(
            target_type=item.target_type,
            op=item.op,
            target_id=item.target_id,
            person_id=None,
            patch=_patch_json(_parse(item.target_type, item.op, patch), ProposalOp.UPDATE),
        ),
    )
    audit.log(ctx, "revision.reverted", target_type=rev.record_type.value, target_id=rev.record_id)
    return "applied", None


# ------------------------------------------------------------------ erasure (§5)
def on_person_erased(ctx: TreeContext, person_id: uuid.UUID, record_ids: set[uuid.UUID]) -> None:
    """Erasure wins over review: drop the values and make open proposals stale."""
    ids = record_ids | {person_id}
    items = list(
        ctx.db.scalars(
            select(ChangeProposalItem)
            .where(ChangeProposalItem.tree_id == ctx.tree_id)
            .where((ChangeProposalItem.person_id == person_id) | ChangeProposalItem.target_id.in_(ids))
        )
    )
    proposal_ids = {i.proposal_id for i in items}
    for i in items:
        i.patch = {}
    proposals = list(
        ctx.db.scalars(
            select(ChangeProposal)
            .where(ChangeProposal.tree_id == ctx.tree_id)
            .where(
                ChangeProposal.id.in_(proposal_ids)
                | (ChangeProposal.person_id == person_id)
                | ChangeProposal.target_id.in_(ids)
            )
        )
    )
    for p in proposals:
        if p.status in OPEN:
            p.status = ChangeProposalStatus.STALE
            p.stale_reason = "A person this change concerned was erased."
