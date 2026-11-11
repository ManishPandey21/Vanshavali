"""Takedown API schemas (ADR-0027 §8.2). Nothing here carries a record's title or content."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.models.enums import (
    AppealStatus,
    DecisionReason,
    ReportReason,
    ReportStatus,
    SuspensionDecision,
    SuspensionStatus,
)

RecordType = Literal["document", "tradition", "collection"]


class ReportIn(ApiModel):
    reason: ReportReason
    note: str = Field(default="", max_length=500)


class ReportCreated(ApiModel):
    id: uuid.UUID
    reference: str
    status: ReportStatus


class ReportOut(ApiModel):
    """A report as the members who handle reports see it: never who reported, never the record."""

    id: uuid.UUID
    reference: str
    resource_type: RecordType
    reason: ReportReason
    note: str
    status: ReportStatus
    created_at: dt.datetime
    reviewed_at: dt.datetime | None
    review_reason: DecisionReason | None
    suspension_id: uuid.UUID | None
    # false when the caller owns the record: nobody acts on a report about their own record
    can_act: bool


class DismissIn(ApiModel):
    reason: Literal["mistaken_report", "not_a_takedown_matter", "other"]


class SuspensionOut(ApiModel):
    id: uuid.UUID
    reference: str
    resource_type: RecordType
    # only for the record's owner (who can open it); handlers never need it
    resource_id: uuid.UUID | None
    reason: ReportReason
    status: SuspensionStatus
    suspended_at: dt.datetime
    appeal_status: AppealStatus
    appeal_note: str
    appealed_at: dt.datetime | None
    appeal_due_at: dt.datetime | None
    overdue: bool
    escalated_at: dt.datetime | None
    decided_at: dt.datetime | None
    decision_reason: DecisionReason | None
    decision_note: str
    sole_reviewer: bool
    # who suspended and who decided: for the members who handle takedowns only
    suspended_by_name: str | None = None
    decided_by_name: str | None = None
    is_owner: bool
    can_decide: bool


class AppealIn(ApiModel):
    note: str = Field(min_length=1, max_length=1000)


class DecisionIn(ApiModel):
    decision: SuspensionDecision
    reason: DecisionReason
    note: str = Field(default="", max_length=1000)
    # the only member who may decide also suspended it (ADR-0027 §8.2 detail 4, fallback)
    confirm_sole_reviewer: bool = False
