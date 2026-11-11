"""Visibility & Sharing for documents (ADR-0027): the document adapter over ``app.modules.sharing``.

Documents add what is specific to files: a separate *download* right (``allow_download`` and
``download`` grants), the vault rule, and people linked through ``document_link``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.models import Document, DocumentLink, Event, EventMedia
from app.models.enums import DocumentLinkTarget, GrantResource, NotificationKind, RecordPrivacyLevel
from app.modules.documents import access
from app.modules.sharing import core
from app.modules.sharing.core import (  # noqa: F401  (re-exported for callers)
    CHOOSABLE,
    Cap,
    Proposal,
    caps_for_people,
    ceiling_out,
    narrowest,
    within,
)
from app.modules.sharing.schemas import SharingOut, SharingUpdate


class DocumentRecord(core.RecordAdapter):
    resource = GrantResource.DOCUMENT
    audit_type = "document"
    narrowed_notice = NotificationKind.DOCUMENT_NARROWED
    supports_download = True
    record: Document

    def audience_branch(self) -> uuid.UUID | None:
        return self.record.audience_branch_id

    def allow_download(self) -> bool:
        return self.record.allow_download

    def linked_people(self, ctx: TreeContext) -> list[uuid.UUID]:
        return linked_people(ctx, self.id)

    def extra_caps(self, ctx: TreeContext) -> list[Cap]:
        """A photo in an event's album is never more visible than the event (ADR-0027 §5.3)."""
        return [c for e in albums_of(ctx, self.id) if (c := core.event_cap(ctx, e)) is not None]

    def _copy(self, p: Proposal) -> Document:
        """An unsaved copy of the document carrying the proposed settings, for evaluation only."""
        d = self.record
        return Document(
            id=d.id,
            tree_id=d.tree_id,
            category=d.category,
            storage_class=d.storage_class,
            privacy_level=p.privacy_level,
            owner_membership_id=d.owner_membership_id,
            audience_branch_id=p.audience_branch_id,
            allow_download=p.allow_download,
            created_by=d.created_by,
        )

    def can_view(self, mctx: TreeContext, p: Proposal) -> bool:
        return access.can_view_document(mctx, self._copy(p))

    def can_download(self, mctx: TreeContext, p: Proposal) -> bool:
        return access.can_download(mctx, self._copy(p))

    def manager_may_narrow(self, ctx: TreeContext) -> bool:
        return ctx.has(Permission.DOCUMENT_MANAGE)

    def store(self, ctx: TreeContext, p: Proposal) -> None:
        self.record.privacy_level = p.privacy_level
        self.record.audience_branch_id = p.audience_branch_id
        self.record.allow_download = p.allow_download


def linked_people(ctx: TreeContext, doc_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        ctx.db.scalars(
            select(DocumentLink.target_id).where(
                DocumentLink.tree_id == ctx.tree_id,
                DocumentLink.document_id == doc_id,
                DocumentLink.target_type == DocumentLinkTarget.PERSON,
            )
        )
    )


def albums_of(ctx: TreeContext, doc_id: uuid.UUID) -> list[Event]:
    return list(
        ctx.db.scalars(
            select(Event).where(
                Event.tree_id == ctx.tree_id,
                Event.id.in_(
                    select(EventMedia.event_id).where(
                        EventMedia.tree_id == ctx.tree_id, EventMedia.document_id == doc_id
                    )
                ),
            )
        )
    )


def records_in_album(ctx: TreeContext, event_id: uuid.UUID) -> list[DocumentRecord]:
    docs = ctx.db.scalars(
        select(Document).where(
            Document.tree_id == ctx.tree_id,
            Document.id.in_(
                select(EventMedia.document_id).where(
                    EventMedia.tree_id == ctx.tree_id, EventMedia.event_id == event_id
                )
            ),
        )
    ).all()
    return [DocumentRecord(d) for d in docs]


def records_linked_to(ctx: TreeContext, person_id: uuid.UUID) -> list[DocumentRecord]:
    docs = ctx.db.scalars(
        select(Document).where(
            Document.tree_id == ctx.tree_id,
            Document.id.in_(
                select(DocumentLink.document_id).where(
                    DocumentLink.tree_id == ctx.tree_id,
                    DocumentLink.target_type == DocumentLinkTarget.PERSON,
                    DocumentLink.target_id == person_id,
                )
            ),
        )
    ).all()
    return [DocumentRecord(d) for d in docs]


# ---------------------------------------------------------------- the API used by the document module
def can_edit(ctx: TreeContext, doc: Document) -> bool:
    return DocumentRecord(doc).can_edit(ctx)


def current(ctx: TreeContext, doc: Document) -> Proposal:
    return DocumentRecord(doc).current(ctx)


def apply(ctx: TreeContext, doc: Document, new: Proposal, *, confirm_wider: bool) -> None:
    core.apply(ctx, DocumentRecord(doc), new, confirm_wider=confirm_wider)


def enforce_ceiling(ctx: TreeContext, doc: Document, *, reason: str) -> bool:
    return core.enforce_ceiling(ctx, DocumentRecord(doc), reason=reason)


def enforce_person_ceiling(ctx: TreeContext, person_id: uuid.UUID) -> int:
    return core.enforce_person_ceiling(ctx, person_id)


def sharing_out(ctx: TreeContext, doc: Document) -> SharingOut:
    return core.sharing_out(ctx, DocumentRecord(doc))


def preview(ctx: TreeContext, document_id: uuid.UUID, body: SharingUpdate) -> SharingOut:
    rec = DocumentRecord(access.get_document(ctx, document_id))
    core.require_editable(ctx, rec)
    return core.sharing_out(ctx, rec, core.proposal(ctx, rec, body))


def update(ctx: TreeContext, document_id: uuid.UUID, body: SharingUpdate) -> SharingOut:
    rec = DocumentRecord(access.get_document(ctx, document_id))
    core.require_editable(ctx, rec)
    core.apply(ctx, rec, core.proposal(ctx, rec, body), confirm_wider=body.confirm_wider)
    return core.sharing_out(ctx, rec)


__all__ = ["RecordPrivacyLevel"]
