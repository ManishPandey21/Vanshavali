"""A person's revision history, redacted for the reader (ADR-0021 §3).

History holds values, so it is read like the facts themselves:

* the reader must be able to see the person (404 otherwise, as for the profile);
* a field whose group the reader may not see is listed as changed, without values (a viewer
  who may only see a birth year learns "date changed", not the dates);
* a relationship's history shows only if the reader can see both people;
* privacy settings, and anything carrying its own privacy level, show values to privacy managers
  only.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select

from app.authz.context import TreeContext
from app.authz.privacy import Subject
from app.models import EventParticipant, RecordRevision, TreeMembership, User
from app.models.enums import ProposalOp, ReviewTarget
from app.modules.genealogy import lookup
from app.modules.review import redaction


def _event_ids(ctx: TreeContext, person_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        ctx.db.scalars(
            select(EventParticipant.event_id).where(
                EventParticipant.tree_id == ctx.tree_id, EventParticipant.person_id == person_id
            )
        )
    )


def _record_meta(revs: list[RecordRevision]) -> dict[uuid.UUID, dict[str, Any]]:
    """Per record: event type, attribute, privacy level, from any revision of it (create has all)."""
    meta: dict[uuid.UUID, dict[str, Any]] = {}
    for r in sorted(revs, key=lambda x: x.revision):
        m = meta.setdefault(r.record_id, {})
        for src in (r.before, r.after):
            for k in ("type", "attribute", "privacy_level"):
                if k in src and src[k] is not None:
                    m[k] = src[k]
    return meta


def _changes(
    ctx: TreeContext, rev: RecordRevision, subject: Subject, meta: dict[str, Any]
) -> list[dict[str, Any]]:
    out = []
    for field in sorted(set(rev.before) | set(rev.after)):
        hidden = redaction.is_hidden(ctx, rev.record_type, field, meta, subject)
        out.append(
            {
                "field": field,
                "before": None if hidden else rev.before.get(field),
                "after": None if hidden else rev.after.get(field),
                "hidden": hidden,
            }
        )
    return out


def _actors(ctx: TreeContext, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display names of tree members who made changes (only members' names, never other users')."""
    if not ids:
        return {}
    rows = ctx.db.execute(
        select(User.id, User.display_name)
        .join(TreeMembership, TreeMembership.user_id == User.id)
        .where(TreeMembership.tree_id == ctx.tree_id, User.id.in_(ids))
    ).all()
    return {row[0]: row[1] for row in rows}


def person_history(
    ctx: TreeContext, person_id: uuid.UUID, offset: int, limit: int
) -> tuple[list[dict[str, Any]], bool]:
    subject = lookup.get_person_subject(ctx, person_id)  # 404 when the reader may not see them
    ev_ids = _event_ids(ctx, person_id)
    conds = [RecordRevision.person_id == person_id, RecordRevision.person_b_id == person_id]
    if ev_ids:
        conds.append(RecordRevision.record_id.in_(ev_ids))
    revs = list(
        ctx.db.scalars(
            select(RecordRevision)
            .where(RecordRevision.tree_id == ctx.tree_id, or_(*conds))
            .order_by(RecordRevision.created_at.desc(), RecordRevision.id.desc())
        )
    )
    # a relationship's history only when the reader can see both people
    others = {
        r.person_b_id if r.person_id == person_id else r.person_id
        for r in revs
        if r.record_type == ReviewTarget.RELATIONSHIP
    }
    visible = lookup.visible_subjects(ctx, {o for o in others if o})
    revs = [
        r
        for r in revs
        if r.record_type != ReviewTarget.RELATIONSHIP
        or all(p is None or p == person_id or p in visible for p in (r.person_id, r.person_b_id))
    ]
    page = revs[offset : offset + limit]
    meta = _record_meta(
        list(
            ctx.db.scalars(
                select(RecordRevision).where(
                    RecordRevision.tree_id == ctx.tree_id,
                    RecordRevision.record_id.in_({r.record_id for r in page}),
                )
            )
        )
        if page
        else []
    )
    names = _actors(ctx, {u for r in page for u in (r.actor_id, r.reviewer_id) if u})
    items = [
        {
            "id": r.id,
            "record_type": r.record_type,
            "record_id": r.record_id,
            "revision": r.revision,
            "op": r.op,
            "created_at": r.created_at,
            "actor": {"id": r.actor_id, "display_name": names.get(r.actor_id)} if r.actor_id else None,
            "reviewer": {"id": r.reviewer_id, "display_name": names.get(r.reviewer_id)}
            if r.reviewer_id
            else None,
            "proposal_id": r.proposal_id,
            "changes": _changes(ctx, r, subject, meta.get(r.record_id, {})),
            "revertible": r.op == ProposalOp.UPDATE,
        }
        for r in page
    ]
    return items, len(revs) > offset + limit


def get_revision(ctx: TreeContext, revision_id: uuid.UUID) -> RecordRevision:
    return lookup.get_in_tree(ctx, RecordRevision, revision_id, "Revision")
