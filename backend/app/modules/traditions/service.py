"""Family traditions archive (ADR-0026 §7): ritual guides, customs, songs, recipes and stories.

* An entry has its own privacy level; linking a living person never widens it, and public
  (deceased-only) trees never show traditions.
* Anyone with family.write may add an entry. Editing someone else's entry follows the tree's
  review policy like every "all" change (ADR-0021); only the author and admins may withdraw it or
  change who can read it.
* Every change is kept in the revision history (the same flush hook as people and facts).
* Text is plain text with light formatting; it is never stored or rendered as HTML.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import exists, select

from app.authz import records
from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import is_private_record_level, is_record_owner, record_allows
from app.core import audit
from app.core.errors import Forbidden, NotFound
from app.core.textnorm import detect_script, search_key
from app.models import (
    FamilyBranch,
    Place,
    RecordRevision,
    TraditionEntry,
    TraditionLink,
    TreeMembership,
    User,
)
from app.models.enums import (
    GrantResource,
    RecordPrivacyLevel,
    ReviewTarget,
    TraditionKind,
    TraditionLinkTarget,
)
from app.modules.genealogy import lookup
from app.modules.review import policy as review_policy
from app.modules.traditions.schemas import (
    TraditionEntryIn,
    TraditionEntryUpdate,
    TraditionLinkIn,
    TraditionLinkOut,
    TraditionOut,
    TraditionRevisionOut,
    TraditionSummaryOut,
)

EXCERPT = 240
SEARCH_BODY = 20_000


# ---------------------------------------------------------------- reading
def _is_author(ctx: TreeContext, e: TraditionEntry) -> bool:
    return ctx.user_id is not None and e.created_by == ctx.user_id


def is_owner(ctx: TreeContext, e: TraditionEntry) -> bool:
    """The viewer is the entry's content owner (ADR-0027 §2)."""
    return is_record_owner(ctx, e.owner_membership_id)


def _may_withdraw(ctx: TreeContext, e: TraditionEntry) -> bool:
    if is_private_record_level(e.privacy_level):
        return is_owner(ctx, e)  # a private entry is its owner's alone (ADR-0027 §10)
    return _is_author(ctx, e) or is_owner(ctx, e) or ctx.is_admin


def may_read(ctx: TreeContext, e: TraditionEntry) -> bool:
    """The entry's own privacy level, for members only; never on a public view.

    Evaluated by ``record_allows`` like any shareable record (ADR-0027 §1, A9), with the entry's
    ``branch_id`` as its audience branch and tradition grants. Legacy levels keep their old meaning
    here: ``PRIVATE_SELF`` is the author (or content owner) only, and the author still reads any
    entry that is not private.
    """
    if ctx.public or not ctx.is_member or e.withdrawn_at is not None:
        return False
    level = RecordPrivacyLevel(e.privacy_level)
    if not is_private_record_level(level) and _is_author(ctx, e):
        return True
    if level == RecordPrivacyLevel.PRIVATE_SELF:
        return is_owner(ctx, e)
    return record_allows(
        ctx,
        level,
        owner_membership_id=e.owner_membership_id,
        audience_branch_id=e.branch_id,
        grant=(GrantResource.TRADITION, e.id),
    )


def get_entry(ctx: TreeContext, entry_id: uuid.UUID) -> TraditionEntry:
    e = ctx.db.get(TraditionEntry, entry_id)
    if e is None or e.tree_id != ctx.tree_id or not may_read(ctx, e):
        raise NotFound("Tradition not found")
    return e


def _names(ctx: TreeContext, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display names of tree members only."""
    if not ids:
        return {}
    rows = ctx.db.execute(
        select(User.id, User.display_name)
        .join(TreeMembership, TreeMembership.user_id == User.id)
        .where(TreeMembership.tree_id == ctx.tree_id, User.id.in_(ids))
    ).all()
    return {r[0]: r[1] for r in rows}


def _excerpt(body: str) -> str:
    flat = " ".join(body.split())
    return flat if len(flat) <= EXCERPT else flat[: EXCERPT - 1].rstrip() + "…"


def _summary(e: TraditionEntry, names: dict[uuid.UUID, str]) -> TraditionSummaryOut:
    return TraditionSummaryOut(
        id=e.id,
        kind=e.kind,
        title=e.title,
        excerpt=_excerpt(e.body),
        language=e.language,
        script=e.script,
        branch_id=e.branch_id,
        privacy_level=e.privacy_level,
        author_name=names.get(e.created_by) if e.created_by else None,
        updated_at=e.updated_at,
    )


def _visible_links(ctx: TreeContext, links: list[TraditionLink]) -> list[TraditionLinkOut]:
    """Only links to what the reader can see; a hidden person is left out, never named."""
    people = [link.target_id for link in links if link.target_type == TraditionLinkTarget.PERSON]
    visible = lookup.visible_subjects(ctx, people) if people else {}
    out = []
    for link in links:
        label: str | None = None
        if link.target_type == TraditionLinkTarget.PERSON:
            subj = visible.get(link.target_id)
            label = subj.person.preferred_display_name if subj is not None else None
        elif link.target_type == TraditionLinkTarget.EVENT:
            label = _event_label(ctx, link.target_id)
        else:
            place = ctx.db.get(Place, link.target_id)
            label = place.canonical_name if place is not None and place.tree_id == ctx.tree_id else None
        if label is not None:
            out.append(TraditionLinkOut(target_type=link.target_type, target_id=link.target_id, label=label))
    return out


def _event_label(ctx: TreeContext, event_id: uuid.UUID) -> str | None:
    from app.modules.genealogy.service import get_event_checked

    try:
        e, _principal = get_event_checked(ctx, event_id)
    except NotFound:
        return None
    return e.title or e.type.value.replace("_", " ")


def _links_of(ctx: TreeContext, entry_id: uuid.UUID) -> list[TraditionLink]:
    return list(
        ctx.db.scalars(
            select(TraditionLink)
            .where(TraditionLink.tree_id == ctx.tree_id, TraditionLink.tradition_id == entry_id)
            .order_by(TraditionLink.created_at)
        )
    )


def needs_review_to_edit(ctx: TreeContext, e: TraditionEntry) -> bool:
    return not (_is_author(ctx, e) or is_owner(ctx, e)) and review_policy.needs_review(ctx, "all", [], [e])


def entry_out(ctx: TreeContext, e: TraditionEntry) -> TraditionOut:
    names = _names(ctx, {e.created_by} if e.created_by else set())
    can_write = ctx.has(Permission.FAMILY_WRITE)
    can_edit = can_write and (not is_private_record_level(e.privacy_level) or is_owner(ctx, e))
    return TraditionOut(
        **_summary(e, names).model_dump(),
        body=e.body,
        links=_visible_links(ctx, _links_of(ctx, e.id)),
        revision=e.revision,
        review_state=e.review_state,
        created_at=e.created_at,
        created_by=e.created_by,
        can_edit=can_edit,
        edit_needs_review=can_edit and needs_review_to_edit(ctx, e),
        can_withdraw=_may_withdraw(ctx, e),
        owner_membership_id=e.owner_membership_id,
        is_owner=is_owner(ctx, e),
    )


def list_entries(
    ctx: TreeContext,
    *,
    kind: TraditionKind | None,
    person_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    q: str,
    offset: int,
    limit: int,
) -> tuple[list[TraditionSummaryOut], bool]:
    ctx.require(Permission.TREE_READ)
    if ctx.public or not ctx.is_member:
        raise NotFound("Tree not found")
    stmt = select(TraditionEntry).where(
        TraditionEntry.tree_id == ctx.tree_id, TraditionEntry.withdrawn_at.is_(None)
    )
    if kind is not None:
        stmt = stmt.where(TraditionEntry.kind == kind)
    if branch_id is not None:
        stmt = stmt.where(TraditionEntry.branch_id == branch_id)
    if person_id is not None:
        lookup.get_person(ctx, person_id)  # 404 for a person the reader cannot see
        stmt = stmt.where(
            exists().where(
                TraditionLink.tree_id == ctx.tree_id,
                TraditionLink.tradition_id == TraditionEntry.id,
                TraditionLink.target_type == TraditionLinkTarget.PERSON,
                TraditionLink.target_id == person_id,
            )
        )
    key = search_key(q) if q.strip() else ""
    if key:
        stmt = stmt.where(TraditionEntry.search_text.contains(key))
    rows = [
        e
        for e in ctx.db.scalars(stmt.order_by(TraditionEntry.updated_at.desc(), TraditionEntry.id.desc()))
        if may_read(ctx, e)
    ]
    page = rows[offset : offset + limit]
    names = _names(ctx, {e.created_by for e in page if e.created_by})
    return [_summary(e, names) for e in page], len(rows) > offset + limit


# ---------------------------------------------------------------- writing
def _check_branch(ctx: TreeContext, branch_id: uuid.UUID | None) -> None:
    if branch_id is not None:
        lookup.get_in_tree(ctx, FamilyBranch, branch_id, "Branch")


def _check_link(ctx: TreeContext, link: TraditionLinkIn) -> None:
    """A link may name only what the writer can see in this tree (404 otherwise)."""
    if link.target_type == TraditionLinkTarget.PERSON:
        lookup.get_person(ctx, link.target_id)
    elif link.target_type == TraditionLinkTarget.EVENT:
        from app.modules.genealogy.service import get_event_checked

        get_event_checked(ctx, link.target_id)
    else:
        lookup.get_place(ctx, link.target_id)


def _set_links(ctx: TreeContext, e: TraditionEntry, links: list[TraditionLinkIn]) -> None:
    wanted = {(w.target_type, w.target_id) for w in links}
    for w in links:
        _check_link(ctx, w)
    existing = _links_of(ctx, e.id)
    have = {(x.target_type, x.target_id) for x in existing}
    for x in existing:
        # a link the writer cannot see stays: nobody removes what they cannot see
        if (x.target_type, x.target_id) not in wanted and _link_visible(ctx, x):
            ctx.db.delete(x)
    for t, tid in wanted - have:
        ctx.db.add(
            TraditionLink(
                tree_id=ctx.tree_id, tradition_id=e.id, target_type=t, target_id=tid, created_by=ctx.user_id
            )
        )


def _link_visible(ctx: TreeContext, link: TraditionLink) -> bool:
    try:
        _check_link(ctx, TraditionLinkIn(target_type=link.target_type, target_id=link.target_id))
        return True
    except NotFound:
        return False


def _index(e: TraditionEntry) -> None:
    e.search_text = search_key(e.title, e.body[:SEARCH_BODY])
    if e.script is None and e.body:
        e.script = detect_script(e.title + " " + e.body[:2000])


def create_entry(ctx: TreeContext, body: TraditionEntryIn) -> TraditionEntry:
    ctx.require(Permission.FAMILY_WRITE)
    if ctx.public or not ctx.is_member:
        raise NotFound("Tree not found")
    _check_branch(ctx, body.branch_id)
    e = TraditionEntry(
        tree_id=ctx.tree_id,
        kind=body.kind,
        title=body.title,
        body=body.body,
        language=body.language,
        script=body.script,
        branch_id=body.branch_id,
        privacy_level=body.privacy_level,
        created_by=ctx.user_id,
        owner_membership_id=ctx.membership_id,
    )
    _index(e)
    ctx.db.add(e)
    ctx.db.flush()
    _set_links(ctx, e, body.links)
    ctx.db.flush()
    # the text is family data: audit the fact, not the words
    audit.log(
        ctx, "tradition.created", target_type="tradition", target_id=e.id, details={"kind": e.kind.value}
    )
    return e


def update_entry(ctx: TreeContext, entry_id: uuid.UUID, body: TraditionEntryUpdate) -> TraditionEntry:
    e = get_entry(ctx, entry_id)
    ctx.require(Permission.FAMILY_WRITE)
    owner = is_owner(ctx, e)
    records.require_owner_for_private(owner, e.privacy_level)  # grantees change nothing (§10)
    if not (_is_author(ctx, e) or owner):
        review_policy.require_direct(ctx, "all", [], [e])
    fields = body.model_fields_set - {"links"}
    new_level = (
        body.privacy_level
        if "privacy_level" in fields and body.privacy_level is not None
        else e.privacy_level
    )
    new_branch = body.branch_id if "branch_id" in fields else e.branch_id
    if "branch_id" in fields:
        _check_branch(ctx, body.branch_id)
    records.require_audience_change(
        owner=owner,
        may_manage=ctx.is_admin,
        old_level=e.privacy_level,
        new_level=new_level,
        old_branch=e.branch_id,
        new_branch=new_branch,
    )
    old_level = e.privacy_level
    for f in fields:
        value = getattr(body, f)
        if value is None and f in ("kind", "title", "body", "privacy_level"):
            continue  # required fields are never cleared
        setattr(e, f, value)
    if fields & {"title", "body"}:
        _index(e)
    if body.links is not None:
        _set_links(ctx, e, body.links)
    e.updated_by = ctx.user_id
    e.updated_at = dt.datetime.now(dt.UTC)
    ctx.db.flush()
    audit.log(
        ctx,
        "tradition.changed",
        target_type="tradition",
        target_id=e.id,
        details={"fields": sorted(body.model_fields_set)},
    )
    if e.privacy_level != old_level:
        audit.log(
            ctx,
            "record.visibility_changed",
            target_type="tradition",
            target_id=e.id,
            details={
                "from": RecordPrivacyLevel(old_level).value,
                "to": RecordPrivacyLevel(e.privacy_level).value,
            },
        )
    return e


def withdraw_entry(ctx: TreeContext, entry_id: uuid.UUID) -> None:
    e = get_entry(ctx, entry_id)
    if not _may_withdraw(ctx, e):
        raise Forbidden("Only the author or a tree admin can withdraw this")
    e.withdrawn_at = dt.datetime.now(dt.UTC)
    e.updated_by = ctx.user_id
    ctx.db.flush()
    audit.log(ctx, "tradition.withdrawn", target_type="tradition", target_id=e.id)


# ---------------------------------------------------------------- history
def history(ctx: TreeContext, entry_id: uuid.UUID) -> list[TraditionRevisionOut]:
    """The entry's revisions; readable by whoever may read the entry now."""
    e = get_entry(ctx, entry_id)
    revs = list(
        ctx.db.scalars(
            select(RecordRevision)
            .where(
                RecordRevision.tree_id == ctx.tree_id,
                RecordRevision.record_type == ReviewTarget.TRADITION,
                RecordRevision.record_id == e.id,
            )
            .order_by(RecordRevision.revision.desc(), RecordRevision.created_at.desc())
        )
    )
    names = _names(ctx, {u for r in revs for u in (r.actor_id, r.reviewer_id) if u})
    return [
        TraditionRevisionOut(
            id=r.id,
            revision=r.revision,
            op=r.op.value,
            created_at=r.created_at,
            actor_name=names.get(r.actor_id) if r.actor_id else None,
            reviewer_name=names.get(r.reviewer_id) if r.reviewer_id else None,
            proposal_id=r.proposal_id,
            changed=sorted(set(r.before) | set(r.after)),
            before=r.before,
            after=r.after,
        )
        for r in revs
    ]


# ---------------------------------------------------------------- export (ADR-0026 §7)
def export_entries(ctx: TreeContext, visible_people: set[uuid.UUID]) -> list[dict[str, Any]]:
    """Entries the exporter may read, with links only to people in the export."""
    out = []
    rows = ctx.db.scalars(
        select(TraditionEntry)
        .where(TraditionEntry.tree_id == ctx.tree_id, TraditionEntry.withdrawn_at.is_(None))
        .order_by(TraditionEntry.created_at)
    )
    for e in rows:
        if not may_read(ctx, e):
            continue
        links = [
            {"target_type": link.target_type.value, "target_id": str(link.target_id)}
            for link in _links_of(ctx, e.id)
            if link.target_type != TraditionLinkTarget.PERSON or link.target_id in visible_people
        ]
        out.append(
            {
                "id": str(e.id),
                "kind": e.kind.value,
                "title": e.title,
                "body": e.body,
                "language": e.language,
                "script": e.script,
                "branch_id": str(e.branch_id) if e.branch_id else None,
                "privacy_level": e.privacy_level.value,
                "links": links,
                "created_at": e.created_at.isoformat(),
                "updated_at": e.updated_at.isoformat(),
            }
        )
    return out
