"""Takedown of shareable records: reports, suspensions and appeals (ADR-0027 §8.2). Members only."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import TreeCtx
from app.models.enums import DecisionReason
from app.modules.takedown import service
from app.modules.takedown.schemas import (
    AppealIn,
    DecisionIn,
    DismissIn,
    RecordType,
    ReportCreated,
    ReportIn,
    ReportOut,
    SuspensionOut,
)

router = APIRouter(prefix="/trees/{tree_id}", tags=["takedown"])


@router.post(
    "/records/{record_type}/{record_id}/reports",
    response_model=ReportCreated,
    status_code=status.HTTP_201_CREATED,
)
def report_record(
    record_type: RecordType, record_id: uuid.UUID, body: ReportIn, ctx: TreeCtx
) -> ReportCreated:
    """Report a record you can see. Its owner is never told who reported it."""
    r = service.report(ctx, record_type, record_id, body.reason, body.note)
    return ReportCreated(id=r.id, reference=r.reference, status=r.status)


@router.get("/record-reports", response_model=list[ReportOut])
def list_reports(ctx: TreeCtx) -> list[ReportOut]:
    """Reports, for the members who handle them: never the record, never who reported."""
    return service.list_reports(ctx)


@router.post("/record-reports/{report_id}/dismiss", response_model=ReportOut)
def dismiss_report(report_id: uuid.UUID, body: DismissIn, ctx: TreeCtx) -> ReportOut:
    r = service.dismiss(ctx, report_id, DecisionReason(body.reason))
    return service.report_out(ctx, r)


@router.post(
    "/record-reports/{report_id}/suspend", response_model=SuspensionOut, status_code=status.HTTP_201_CREATED
)
def suspend_record(report_id: uuid.UUID, ctx: TreeCtx) -> SuspensionOut:
    s = service.suspend(ctx, report_id)
    return service.get_suspension(ctx, s.id)


@router.get("/record-suspensions", response_model=list[SuspensionOut])
def list_suspensions(ctx: TreeCtx) -> list[SuspensionOut]:
    return service.list_suspensions(ctx)


@router.get("/record-suspensions/{suspension_id}", response_model=SuspensionOut)
def get_suspension(suspension_id: uuid.UUID, ctx: TreeCtx) -> SuspensionOut:
    return service.get_suspension(ctx, suspension_id)


@router.post("/record-suspensions/{suspension_id}/appeal", response_model=SuspensionOut)
def appeal_suspension(suspension_id: uuid.UUID, body: AppealIn, ctx: TreeCtx) -> SuspensionOut:
    return service.appeal(ctx, suspension_id, body.note)


@router.post("/record-suspensions/{suspension_id}/decision", response_model=SuspensionOut)
def decide_suspension(suspension_id: uuid.UUID, body: DecisionIn, ctx: TreeCtx) -> SuspensionOut:
    return service.decide(
        ctx,
        suspension_id,
        body.decision,
        body.reason,
        body.note,
        confirm_sole_reviewer=body.confirm_sole_reviewer,
    )
