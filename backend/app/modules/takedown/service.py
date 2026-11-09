"""Reports, suspensions and appeals of shareable records (ADR-0027 §8.2, owner's decisions of 9 Nov 2026).

Nobody gains read access here. A member who can see a record may report it. A member with
``record.takedown`` (owners, family admins) who does not own the record may suspend it by the report,
or dismiss the report, without seeing it. Suspension hides the record from everyone but its owner
(the access checks read ``suspended_at``) and stops it being widened; it changes nothing else. The
owner may appeal once; the appeal is due in ``APPEAL_REVIEW_DAYS`` days and is escalated once when
overdue. Only a decision lifts a suspension, and lifting re-evaluates the record as it is now:
nothing saved before the suspension is restored.

Audit details hold ids, codes and flags only. Notices hold a kind and an id; their text is built
when read. The reporter is never named to the record's owner.
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission, permissions_for
from app.authz.privacy import is_record_owner
from app.core import audit
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.ratelimit import enforce
from app.models import (
    Document,
    PhotoCollection,
    RecordReport,
    RecordSuspension,
    TraditionEntry,
    TreeMembership,
    User,
    UserNotification,
)
from app.models.enums import (
    AppealStatus,
    DecisionReason,
    GrantResource,
    NotificationKind,
    ReportReason,
    ReportStatus,
    Role,
    SuspensionDecision,
    SuspensionStatus,
)
from app.modules.takedown.schemas import ReportOut, SuspensionOut

APPEAL_REVIEW_DAYS = 14
_TYPES: dict[str, GrantResource] = {
    "document": GrantResource.DOCUMENT,
    "tradition": GrantResource.TRADITION,
    "collection": GrantResource.COLLECTION,
}
_MODELS: dict[GrantResource, Any] = {
    GrantResource.DOCUMENT: Document,
    GrantResource.TRADITION: TraditionEntry,
    GrantResource.COLLECTION: PhotoCollection,
}
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ---------------------------------------------------------------- records
def _load(ctx: TreeContext, rtype: GrantResource, rid: uuid.UUID) -> Any | None:
    model = _MODELS[rtype]
    rec = ctx.db.scalar(select(model).where(model.tree_id == ctx.tree_id, model.id == rid))
    if rec is None:
        return None
    if getattr(rec, "deleted_at", None) is not None or getattr(rec, "withdrawn_at", None) is not None:
        return None
    return rec


def _visible(ctx: TreeContext, rtype: GrantResource, rec: Any) -> bool:
    if rtype == GrantResource.DOCUMENT:
        from app.modules.documents.access import can_view_document

        return can_view_document(ctx, rec)
    if rtype == GrantResource.TRADITION:
        from app.modules.traditions.sharing import entry_allows

        return entry_allows(ctx, rec)
    from app.modules.collections.service import collection_allows

    return collection_allows(ctx, rec)


def _owner_user(ctx: TreeContext, rec: Any) -> uuid.UUID | None:
    if rec is None or rec.owner_membership_id is None:
        return None
    m = ctx.db.get(TreeMembership, rec.owner_membership_id)
    return m.user_id if m is not None and m.tree_id == ctx.tree_id else None


def _owns(ctx: TreeContext, rec: Any) -> bool:
    return rec is not None and is_record_owner(ctx, rec.owner_membership_id)


def _type_name(rtype: GrantResource | str) -> str:
    return next(k for k, v in _TYPES.items() if v == GrantResource(rtype))


# ---------------------------------------------------------------- who handles takedowns
def _handlers(ctx: TreeContext, exclude_membership: uuid.UUID | None) -> list[TreeMembership]:
    """Members with ``record.takedown``, except the record's owner."""
    out = []
    for m in ctx.db.scalars(select(TreeMembership).where(TreeMembership.tree_id == ctx.tree_id)):
        if m.id == exclude_membership:
            continue
        if Permission.RECORD_TAKEDOWN in permissions_for(frozenset(Role(r) for r in m.roles)):
            out.append(m)
    return out


def _require_handler(ctx: TreeContext) -> None:
    if not ctx.has(Permission.RECORD_TAKEDOWN):
        raise Forbidden("Only family admins handle reports", code="takedown_not_allowed")


def _notify(
    ctx: TreeContext, users: Iterable[uuid.UUID | None], kind: NotificationKind, subject: uuid.UUID
) -> None:
    for uid in dict.fromkeys(u for u in users if u and u != ctx.user_id):
        ctx.db.add(
            UserNotification(
                tree_id=ctx.tree_id, user_id=uid, kind=kind, subject_id=subject, created_by=ctx.user_id
            )
        )


# ---------------------------------------------------------------- reports
def _reference(ctx: TreeContext) -> str:
    while True:
        ref = "R-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))
        if ctx.db.scalar(select(RecordReport.id).where(RecordReport.reference == ref)) is None:
            return ref


def report(
    ctx: TreeContext, record_type: str, record_id: uuid.UUID, reason: ReportReason, note: str
) -> RecordReport:
    """A member reports a record they can see. Others are told it does not exist (404)."""
    if record_type not in _TYPES or ctx.user_id is None or ctx.membership_id is None:
        raise NotFound("Record not found")
    rtype = _TYPES[record_type]
    rec = _load(ctx, rtype, record_id)
    if rec is None or not _visible(ctx, rtype, rec):
        raise NotFound("Record not found")
    if _owns(ctx, rec):
        raise Conflict("You cannot report your own record; you can change or delete it", code="own_record")
    enforce(f"record-report:{ctx.user_id}", 20, 3600)
    already = ctx.db.scalar(
        select(RecordReport.id).where(
            RecordReport.tree_id == ctx.tree_id,
            RecordReport.resource_type == rtype,
            RecordReport.resource_id == record_id,
            RecordReport.reporter_membership_id == ctx.membership_id,
            RecordReport.status == ReportStatus.OPEN,
        )
    )
    if already is not None:
        raise Conflict("You have already reported this record", code="already_reported")
    r = RecordReport(
        tree_id=ctx.tree_id,
        reference=_reference(ctx),
        resource_type=rtype,
        resource_id=record_id,
        reason=reason,
        note=note.strip(),
        reporter_membership_id=ctx.membership_id,
        reporter_user_id=ctx.user_id,
        created_by=ctx.user_id,
    )
    ctx.db.add(r)
    ctx.db.flush()
    # the report, not the record, is the target: record owners never see who reported
    audit.log(
        ctx,
        "record.reported",
        target_type="record_report",
        target_id=r.id,
        details={"resource_type": rtype.value, "reason": reason.value},
    )
    _notify(
        ctx,
        [m.user_id for m in _handlers(ctx, rec.owner_membership_id)],
        NotificationKind.RECORD_REPORTED,
        r.id,
    )
    return r


def _suspension_for_report(ctx: TreeContext, report_id: uuid.UUID) -> uuid.UUID | None:
    return ctx.db.scalar(
        select(RecordSuspension.id).where(
            RecordSuspension.tree_id == ctx.tree_id, RecordSuspension.report_id == report_id
        )
    )


def report_out(ctx: TreeContext, r: RecordReport) -> ReportOut:
    rec = ctx.db.scalar(
        select(_MODELS[r.resource_type]).where(
            _MODELS[r.resource_type].tree_id == ctx.tree_id, _MODELS[r.resource_type].id == r.resource_id
        )
    )
    return ReportOut(
        id=r.id,
        reference=r.reference,
        resource_type=_type_name(r.resource_type),  # type: ignore[arg-type]
        reason=r.reason,
        note=r.note,
        status=r.status,
        created_at=r.created_at,
        reviewed_at=r.reviewed_at,
        review_reason=r.review_reason,
        suspension_id=_suspension_for_report(ctx, r.id),
        can_act=r.status == ReportStatus.OPEN and not _owns(ctx, rec),
    )


def list_reports(ctx: TreeContext) -> list[ReportOut]:
    _require_handler(ctx)
    rows = ctx.db.scalars(
        select(RecordReport)
        .where(RecordReport.tree_id == ctx.tree_id)
        .order_by(RecordReport.created_at.desc())
        .limit(200)
    )
    return [report_out(ctx, r) for r in rows]


def _open_report(ctx: TreeContext, report_id: uuid.UUID) -> tuple[RecordReport, Any]:
    _require_handler(ctx)
    r = ctx.db.scalar(
        select(RecordReport)
        .where(RecordReport.tree_id == ctx.tree_id, RecordReport.id == report_id)
        .with_for_update()
    )
    if r is None:
        raise NotFound("Report not found")
    rec = _load(ctx, r.resource_type, r.resource_id)
    if _owns(ctx, rec):
        raise Forbidden("Another admin must handle a report about your own record", code="own_record")
    if r.status != ReportStatus.OPEN:
        raise Conflict("This report has already been handled", code="report_closed")
    return r, rec


def _close_report(ctx: TreeContext, r: RecordReport, status: ReportStatus, reason: DecisionReason) -> None:
    r.status = status
    r.reviewed_by = ctx.user_id
    r.reviewed_at = _now()
    r.review_reason = reason
    # the reporter learns only that their report was reviewed, never the outcome for the record
    _notify(ctx, [r.reporter_user_id], NotificationKind.REPORT_REVIEWED, r.id)


def dismiss(ctx: TreeContext, report_id: uuid.UUID, reason: DecisionReason) -> RecordReport:
    """A mistaken report (or not a takedown matter): the record is not touched; its owner never knows."""
    r, _rec = _open_report(ctx, report_id)
    _close_report(ctx, r, ReportStatus.DISMISSED, reason)
    ctx.db.flush()
    audit.log(
        ctx,
        "record.report_dismissed",
        target_type="record_report",
        target_id=r.id,
        details={"reason": reason.value},
    )
    return r


def suspend(ctx: TreeContext, report_id: uuid.UUID) -> RecordSuspension:
    r, rec = _open_report(ctx, report_id)
    if rec is None:
        _close_report(ctx, r, ReportStatus.DISMISSED, DecisionReason.OWNER_CHANGED_THE_RECORD)
        ctx.db.flush()
        raise Conflict("The record no longer exists; the report was closed", code="record_gone")
    if rec.suspended_at is not None:
        raise Conflict("The record is already suspended", code="already_suspended")
    now = _now()
    s = RecordSuspension(
        tree_id=ctx.tree_id,
        report_id=r.id,
        resource_type=r.resource_type,
        resource_id=r.resource_id,
        suspended_by=ctx.user_id,
        created_by=ctx.user_id,
    )
    ctx.db.add(s)
    rec.suspended_at = now
    _close_report(ctx, r, ReportStatus.ACTIONED, DecisionReason.REPORT_CONFIRMED)
    ctx.db.flush()
    audit.log(
        ctx,
        "record.suspended",
        target_type="record_suspension",
        target_id=s.id,
        details={"resource_type": r.resource_type.value, "reason": r.reason.value},
    )
    _notify(ctx, [_owner_user(ctx, rec)], NotificationKind.RECORD_SUSPENDED, s.id)
    return s


# ---------------------------------------------------------------- suspensions and appeals
def _record_of(ctx: TreeContext, s: RecordSuspension) -> Any | None:
    model = _MODELS[s.resource_type]
    return ctx.db.scalar(select(model).where(model.tree_id == ctx.tree_id, model.id == s.resource_id))


def escalate_due(ctx: TreeContext) -> int:
    """Appeals past their due date are escalated once. Nothing is restored: only a decision lifts."""
    due = list(
        ctx.db.scalars(
            select(RecordSuspension).where(
                RecordSuspension.tree_id == ctx.tree_id,
                RecordSuspension.status == SuspensionStatus.ACTIVE,
                RecordSuspension.appeal_status == AppealStatus.PENDING,
                RecordSuspension.appeal_due_at <= _now(),
                RecordSuspension.escalated_at.is_(None),
            )
        )
    )
    for s in due:
        s.escalated_at = _now()
        rec = _record_of(ctx, s)
        owner_mid = rec.owner_membership_id if rec is not None else None
        tree_owners = ctx.db.scalars(
            select(TreeMembership.user_id).where(
                TreeMembership.tree_id == ctx.tree_id, TreeMembership.roles.contains([Role.OWNER.value])
            )
        )
        users = [m.user_id for m in _handlers(ctx, owner_mid)] + [
            u for u in tree_owners if rec is None or u != _owner_user(ctx, rec)
        ]
        for uid in dict.fromkeys(users):
            ctx.db.add(
                UserNotification(
                    tree_id=ctx.tree_id, user_id=uid, kind=NotificationKind.APPEAL_OVERDUE, subject_id=s.id
                )
            )
        audit.record(
            ctx.db,
            action="record.appeal_escalated",
            actor_user_id=None,
            tree_id=ctx.tree_id,
            target_type="record_suspension",
            target_id=s.id,
            details={"resource_type": s.resource_type.value},
        )
    if due:
        ctx.db.flush()
    return len(due)


def _names(ctx: TreeContext, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(ctx.db.execute(select(User.id, User.display_name).where(User.id.in_(wanted))).all())


def _may_decide(ctx: TreeContext, s: RecordSuspension, rec: Any) -> bool:
    return (
        s.status == SuspensionStatus.ACTIVE
        and ctx.has(Permission.RECORD_TAKEDOWN)
        and not _owns(ctx, rec)
        and (s.suspended_by != ctx.user_id or not _other_deciders(ctx, s, rec))
    )


def _other_deciders(ctx: TreeContext, s: RecordSuspension, rec: Any) -> list[TreeMembership]:
    owner_mid = rec.owner_membership_id if rec is not None else None
    return [m for m in _handlers(ctx, owner_mid) if m.user_id != s.suspended_by]


def _suspension_out(
    ctx: TreeContext, s: RecordSuspension, report_ref: str, reason: ReportReason
) -> SuspensionOut:
    rec = _record_of(ctx, s)
    owner = _owns(ctx, rec)
    handler = ctx.has(Permission.RECORD_TAKEDOWN) and not owner
    names = _names(ctx, {s.suspended_by, s.decided_by}) if handler else {}
    return SuspensionOut(
        id=s.id,
        reference=report_ref,
        resource_type=_type_name(s.resource_type),  # type: ignore[arg-type]
        resource_id=s.resource_id if owner else None,
        reason=reason,
        status=s.status,
        suspended_at=s.created_at,
        appeal_status=s.appeal_status,
        appeal_note=s.appeal_note,
        appealed_at=s.appealed_at,
        appeal_due_at=s.appeal_due_at,
        overdue=bool(
            s.appeal_status == AppealStatus.PENDING
            and s.appeal_due_at is not None
            and s.appeal_due_at <= _now()
        ),
        escalated_at=s.escalated_at,
        decided_at=s.decided_at,
        decision_reason=s.decision_reason,
        decision_note=s.decision_note,
        sole_reviewer=s.sole_reviewer,
        suspended_by_name=names.get(s.suspended_by) if s.suspended_by else None,
        decided_by_name=names.get(s.decided_by) if s.decided_by else None,
        is_owner=owner,
        can_decide=_may_decide(ctx, s, rec),
    )


def list_suspensions(ctx: TreeContext) -> list[SuspensionOut]:
    """Handlers see every suspension (without the record); an owner sees those of their records."""
    escalate_due(ctx)
    rows = ctx.db.execute(
        select(RecordSuspension, RecordReport.reference, RecordReport.reason)
        .join(RecordReport, RecordReport.id == RecordSuspension.report_id)
        .where(RecordSuspension.tree_id == ctx.tree_id)
        .order_by(RecordSuspension.created_at.desc())
        .limit(200)
    ).all()
    out = []
    for s, ref, reason in rows:
        item = _suspension_out(ctx, s, ref, reason)
        if item.is_owner or (ctx.has(Permission.RECORD_TAKEDOWN)):
            out.append(item)
    return out


def _get(ctx: TreeContext, suspension_id: uuid.UUID) -> tuple[RecordSuspension, Any, RecordReport]:
    s = ctx.db.scalar(
        select(RecordSuspension)
        .where(RecordSuspension.tree_id == ctx.tree_id, RecordSuspension.id == suspension_id)
        .with_for_update()
    )
    if s is None:
        raise NotFound("Suspension not found")
    rec = _record_of(ctx, s)
    if not (_owns(ctx, rec) or ctx.has(Permission.RECORD_TAKEDOWN)):
        raise NotFound("Suspension not found")
    r = ctx.db.get(RecordReport, s.report_id)
    assert r is not None  # noqa: S101 - foreign key
    return s, rec, r


def get_suspension(ctx: TreeContext, suspension_id: uuid.UUID) -> SuspensionOut:
    escalate_due(ctx)
    s, _rec, r = _get(ctx, suspension_id)
    return _suspension_out(ctx, s, r.reference, r.reason)


def appeal(ctx: TreeContext, suspension_id: uuid.UUID, note: str) -> SuspensionOut:
    """The owner appeals once; the suspension stays in effect while it is reviewed."""
    s, rec, r = _get(ctx, suspension_id)
    if not _owns(ctx, rec):
        raise Forbidden("Only the record's owner can appeal", code="not_record_owner")
    if s.status != SuspensionStatus.ACTIVE:
        raise Conflict("This suspension has been lifted", code="suspension_not_active")
    if s.appeal_status != AppealStatus.NONE:
        raise Conflict("This suspension has already been appealed", code="already_appealed")
    now = _now()
    s.appeal_status = AppealStatus.PENDING
    s.appeal_note = note.strip()
    s.appealed_at = now
    s.appeal_due_at = now + dt.timedelta(days=APPEAL_REVIEW_DAYS)
    ctx.db.flush()
    audit.log(
        ctx,
        "record.suspension_appealed",
        target_type="record_suspension",
        target_id=s.id,
        details={"resource_type": s.resource_type.value},
    )
    others = _other_deciders(ctx, s, rec)
    reviewers = others or [m for m in _handlers(ctx, rec.owner_membership_id) if m.user_id == s.suspended_by]
    _notify(ctx, [m.user_id for m in reviewers], NotificationKind.SUSPENSION_APPEALED, s.id)
    return _suspension_out(ctx, s, r.reference, r.reason)


def decide(
    ctx: TreeContext,
    suspension_id: uuid.UUID,
    decision: SuspensionDecision,
    reason: DecisionReason,
    note: str,
    *,
    confirm_sole_reviewer: bool,
) -> SuspensionOut:
    s, rec, r = _get(ctx, suspension_id)
    _require_handler(ctx)
    if _owns(ctx, rec):
        raise Forbidden("Another admin must decide about your own record", code="own_record")
    if s.status != SuspensionStatus.ACTIVE:
        raise Conflict("This suspension has already been lifted", code="suspension_not_active")
    if decision == SuspensionDecision.UPHOLD and s.appeal_status != AppealStatus.PENDING:
        raise Conflict("There is no appeal to decide", code="no_pending_appeal")
    sole = False
    if s.suspended_by == ctx.user_id:
        if _other_deciders(ctx, s, rec):
            raise Forbidden(
                "Another admin must review a suspension you made", code="different_reviewer_required"
            )
        if not confirm_sole_reviewer:
            raise Conflict(
                "You are the only admin who can decide this, and you made the suspension; confirm to continue",
                code="sole_reviewer_confirmation_required",
            )
        sole = True
    appealed = s.appeal_status == AppealStatus.PENDING
    s.decided_by = ctx.user_id
    s.decided_at = _now()
    s.decision_reason = reason
    s.decision_note = note.strip()
    s.sole_reviewer = sole
    if decision == SuspensionDecision.UPHOLD:
        s.appeal_status = AppealStatus.UPHELD
        kind = NotificationKind.SUSPENSION_UPHELD
    else:
        s.status = SuspensionStatus.LIFTED
        if appealed:
            s.appeal_status = AppealStatus.LIFTED
        kind = NotificationKind.SUSPENSION_LIFTED
        if rec is not None:
            rec.suspended_at = None
            ctx.db.flush()
            _reevaluate(ctx, s.resource_type, rec)
    ctx.db.flush()
    audit.log(
        ctx,
        "record.suspension_decided",
        target_type="record_suspension",
        target_id=s.id,
        details={
            "resource_type": s.resource_type.value,
            "decision": decision.value,
            "reason": reason.value,
            "appealed": appealed,
            "sole_reviewer": sole,
        },
    )
    _notify(ctx, [_owner_user(ctx, rec)], kind, s.id)
    return _suspension_out(ctx, s, r.reference, r.reason)


def _reevaluate(ctx: TreeContext, rtype: GrantResource, rec: Any) -> None:
    """After a lift the record follows its *current* audience, grants and memberships (nothing saved
    before the suspension is restored) and is narrowed at once if a privacy ceiling tightened while
    it was suspended."""
    from app.modules.sharing import core

    if rtype == GrantResource.DOCUMENT:
        from app.modules.documents.sharing import DocumentRecord

        core.enforce_ceiling(ctx, DocumentRecord(rec), reason="lifted")
    elif rtype == GrantResource.TRADITION:
        from app.modules.traditions.sharing import TraditionRecord

        core.enforce_ceiling(ctx, TraditionRecord(rec), reason="lifted")
