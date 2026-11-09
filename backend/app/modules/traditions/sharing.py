"""Visibility & Sharing for family traditions (ADR-0027, increment 2).

A tradition entry is a shareable record: Only me, Selected members, Selected branch (its
``branch_id``) or All family members, never public. Entries are text, so there is no separate
download right. People linked to an entry cap its audience like people tagged in a document.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import is_record_owner, record_allows
from app.models import TraditionEntry, TraditionLink
from app.models.enums import GrantResource, RecordPrivacyLevel, TraditionLinkTarget
from app.modules.sharing import core
from app.modules.sharing.core import Proposal
from app.modules.sharing.schemas import SharingOut, SharingUpdate


def entry_allows(
    ctx: TreeContext,
    e: TraditionEntry,
    level: RecordPrivacyLevel | str | None = None,
    branch_id: uuid.UUID | None = None,
) -> bool:
    """Can the viewer read ``e`` (at its own level, or at a proposed one)?"""
    if ctx.public or not ctx.is_member or e.withdrawn_at is not None:
        return False
    proposed = level is not None
    effective = RecordPrivacyLevel(level) if level is not None else RecordPrivacyLevel(e.privacy_level)
    branch = branch_id if proposed else e.branch_id
    return record_allows(
        ctx,
        effective,
        owner_membership_id=e.owner_membership_id,
        audience_branch_id=branch if effective == RecordPrivacyLevel.FAMILY_BRANCH else None,
        grant=(GrantResource.TRADITION, e.id),
    )


def entry_audience_allows(ctx: TreeContext, e: TraditionEntry) -> bool:
    """Is the viewer in the entry's audience, withdrawn or not? For the audit log, which keeps
    showing a withdrawn entry's history to those it was shared with (ADR-0027 §11)."""
    if ctx.public or not ctx.is_member:
        return False
    return record_allows(
        ctx,
        RecordPrivacyLevel(e.privacy_level),
        owner_membership_id=e.owner_membership_id,
        audience_branch_id=e.branch_id if e.privacy_level == RecordPrivacyLevel.FAMILY_BRANCH else None,
        grant=(GrantResource.TRADITION, e.id),
    )


class TraditionRecord(core.RecordAdapter):
    resource = GrantResource.TRADITION
    audit_type = "tradition"
    supports_download = False
    record: TraditionEntry

    def audience_branch(self) -> uuid.UUID | None:
        return self.record.branch_id if self.level == RecordPrivacyLevel.FAMILY_BRANCH else None

    def allow_download(self) -> bool:
        return False

    def linked_people(self, ctx: TreeContext) -> list[uuid.UUID]:
        return list(
            ctx.db.scalars(
                select(TraditionLink.target_id).where(
                    TraditionLink.tree_id == ctx.tree_id,
                    TraditionLink.tradition_id == self.id,
                    TraditionLink.target_type == TraditionLinkTarget.PERSON,
                )
            )
        )

    def can_view(self, mctx: TreeContext, p: Proposal) -> bool:
        return entry_allows(mctx, self.record, p.privacy_level, p.audience_branch_id)

    def manager_may_narrow(self, ctx: TreeContext) -> bool:
        return ctx.is_admin  # the old rule: the author or a tree admin decides who may read it

    def store(self, ctx: TreeContext, p: Proposal) -> None:
        self.record.privacy_level = p.privacy_level
        if p.privacy_level == RecordPrivacyLevel.FAMILY_BRANCH and p.audience_branch_id is not None:
            self.record.branch_id = p.audience_branch_id  # the entry's branch is its audience


def is_owner(ctx: TreeContext, e: TraditionEntry) -> bool:
    return is_record_owner(ctx, e.owner_membership_id)


def records_linked_to(ctx: TreeContext, person_id: uuid.UUID) -> list[TraditionRecord]:
    entries = ctx.db.scalars(
        select(TraditionEntry).where(
            TraditionEntry.tree_id == ctx.tree_id,
            TraditionEntry.id.in_(
                select(TraditionLink.tradition_id).where(
                    TraditionLink.tree_id == ctx.tree_id,
                    TraditionLink.target_type == TraditionLinkTarget.PERSON,
                    TraditionLink.target_id == person_id,
                )
            ),
        )
    ).all()
    return [TraditionRecord(e) for e in entries]


def sharing_out(ctx: TreeContext, e: TraditionEntry) -> SharingOut:
    return core.sharing_out(ctx, TraditionRecord(e))


def preview(ctx: TreeContext, e: TraditionEntry, body: SharingUpdate) -> SharingOut:
    rec = TraditionRecord(e)
    core.require_editable(ctx, rec)
    return core.sharing_out(ctx, rec, core.proposal(ctx, rec, body))


def update(ctx: TreeContext, e: TraditionEntry, body: SharingUpdate) -> SharingOut:
    rec = TraditionRecord(e)
    core.require_editable(ctx, rec)
    core.apply(ctx, rec, core.proposal(ctx, rec, body), confirm_wider=body.confirm_wider)
    return core.sharing_out(ctx, rec)
