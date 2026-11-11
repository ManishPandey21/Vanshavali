"""Change proposal, challenge, history and notification schemas (ADR-0021 §9)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.models.enums import (
    ChangeProposalStatus,
    NotificationKind,
    ProposalKind,
    ProposalOp,
    ReviewPolicy,
    ReviewState,
    ReviewTarget,
)
from app.modules.genealogy.schemas import PersonSummary

MAX_ITEMS = 50
MAX_TEXT = 2000


class ProposalItemIn(ApiModel):
    target_type: ReviewTarget
    op: ProposalOp
    target_id: uuid.UUID | None = None  # required for update and delete
    person_id: uuid.UUID | None = None  # required to add a name or heritage claim to a person
    # validated by the same schema as the direct endpoint (PersonUpdate, NameIn, RelationshipIn…)
    patch: dict[str, Any] = {}


class ProposalIn(ApiModel):
    rationale: str = Field(default="", max_length=MAX_TEXT)
    items: list[ProposalItemIn] = Field(min_length=1, max_length=MAX_ITEMS)
    source_ids: list[uuid.UUID] = Field(default=[], max_length=20)
    submit: bool = True


class ChallengeIn(ApiModel):
    target_type: ReviewTarget
    target_id: uuid.UUID
    rationale: str = Field(min_length=3, max_length=MAX_TEXT)
    # an optional proposed correction, applied only if a reviewer upholds the challenge
    items: list[ProposalItemIn] = Field(default=[], max_length=MAX_ITEMS)
    source_ids: list[uuid.UUID] = Field(default=[], max_length=20)


class DecisionIn(ApiModel):
    note: str | None = Field(default=None, max_length=MAX_TEXT)


class RejectIn(ApiModel):
    note: str = Field(min_length=1, max_length=MAX_TEXT)


class UpholdIn(ApiModel):
    note: str | None = Field(default=None, max_length=MAX_TEXT)
    mark_disputed: bool = True  # also record evidence_status DISPUTED on the fact


class CommentIn(ApiModel):
    body: str = Field(min_length=1, max_length=MAX_TEXT)


class ReviewStateIn(ApiModel):
    target_type: ReviewTarget
    target_id: uuid.UUID
    state: Literal["family_reviewed", "unreviewed"]


class ReviewPolicyIn(ApiModel):
    review_policy: ReviewPolicy


class UserRef(ApiModel):
    id: uuid.UUID
    display_name: str | None = None


class FieldChange(ApiModel):
    field: str
    current: Any = None
    proposed: Any = None
    # the reader may not see this field: values withheld, and they cannot decide the proposal
    hidden: bool = False


class ProposalItemOut(ApiModel):
    id: uuid.UUID
    target_type: ReviewTarget
    op: ProposalOp
    target_id: uuid.UUID | None
    person_id: uuid.UUID | None
    label: str
    changes: list[FieldChange]
    # the record changed since the proposal was made (or no longer exists)
    outdated: bool = False


class CommentOut(ApiModel):
    id: uuid.UUID
    author: UserRef | None
    body: str
    created_at: dt.datetime


class ChangeProposalOut(ApiModel):
    id: uuid.UUID
    kind: ProposalKind
    status: ChangeProposalStatus
    rationale: str
    proposer: UserRef | None
    person_id: uuid.UUID | None
    person_label: str | None = None
    # a proposal about the family as a whole (ADR-0026): tradition or kinship_word
    family_subject: ReviewTarget | None = None
    target_type: ReviewTarget | None = None
    target_id: uuid.UUID | None = None
    created_at: dt.datetime
    submitted_at: dt.datetime | None
    decided_by: UserRef | None = None
    decided_at: dt.datetime | None = None
    decision_note: str | None = None
    stale_reason: str | None = None
    supersedes_id: uuid.UUID | None = None
    source_ids: list[uuid.UUID] = []
    items: list[ProposalItemOut] = []
    comments: list[CommentOut] = []
    # what the reader may do now
    can_decide: bool = False
    cannot_decide_reason: str | None = None
    can_withdraw: bool = False
    can_rebase: bool = False


class ProposalSummary(ApiModel):
    id: uuid.UUID
    kind: ProposalKind
    status: ChangeProposalStatus
    proposer: UserRef | None
    person_id: uuid.UUID | None
    person_label: str | None = None
    family_subject: ReviewTarget | None = None
    item_count: int
    created_at: dt.datetime
    submitted_at: dt.datetime | None
    decided_at: dt.datetime | None


class RevisionChange(ApiModel):
    field: str
    before: Any = None
    after: Any = None
    hidden: bool = False


class RevisionOut(ApiModel):
    id: uuid.UUID
    record_type: ReviewTarget
    record_id: uuid.UUID
    revision: int
    op: ProposalOp
    created_at: dt.datetime
    actor: UserRef | None = None
    reviewer: UserRef | None = None
    proposal_id: uuid.UUID | None = None
    changes: list[RevisionChange]
    revertible: bool = False


class RevertOut(ApiModel):
    # "applied" when the reader writes directly, "proposed" when the family reviews such changes
    outcome: Literal["applied", "proposed"]
    proposal_id: uuid.UUID | None = None


class ReviewStateOut(ApiModel):
    target_type: ReviewTarget
    target_id: uuid.UUID
    review_state: ReviewState
    review_state_at: dt.datetime | None = None


class NotificationOut(ApiModel):
    id: uuid.UUID
    kind: NotificationKind
    proposal_id: uuid.UUID | None
    # the record a "made more private" notice is about (ADR-0027 §5); None for other kinds
    subject_id: uuid.UUID | None = None
    text: str  # built when read, with the reader's current permissions
    created_at: dt.datetime
    read: bool


class NotificationsOut(ApiModel):
    items: list[NotificationOut]
    unread: int
    next_cursor: str | None = None


class NotificationsReadIn(ApiModel):
    ids: list[uuid.UUID] = Field(default=[], max_length=200)  # empty = all


class DuplicateNameIn(ApiModel):
    given_name: str | None = Field(default=None, max_length=200)
    surname: str | None = Field(default=None, max_length=200)


class DuplicateCheckIn(ApiModel):
    """The person about to be added, and who they will be linked to (ADR-0021 §8)."""

    names: list[DuplicateNameIn] = Field(min_length=1, max_length=5)
    birth_year: int | None = Field(default=None, ge=1, le=2200)
    sex_at_birth: str | None = Field(default=None, max_length=20)
    parent_ids: list[uuid.UUID] = Field(default=[], max_length=4)
    spouse_ids: list[uuid.UUID] = Field(default=[], max_length=4)
    birth_place_id: uuid.UUID | None = None
    # the anchor and anyone else already chosen: never suggested as a duplicate
    exclude_ids: list[uuid.UUID] = Field(default=[], max_length=20)


class EntryDuplicateMatch(ApiModel):
    person: PersonSummary
    score: float
    likely: bool
    reasons: list[str]


class DuplicateCheckOut(ApiModel):
    candidates: list[EntryDuplicateMatch]
