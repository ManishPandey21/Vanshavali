"""Important life events: tree-wide listing and event photo albums (ADR-0015).

Events and photos stay in their existing homes (``event``, the document vault). This module adds
the album (``event_media``) and a privacy-filtered, tree-wide event listing. Every photo keeps the
vault's own access rules; an album entry is shown only when both the event and the photo are
visible to the viewer.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import _RANK
from app.core import audit
from app.core.dates import GenealogicalDate, date_to_json
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.filetypes import validate_upload
from app.models import Document, DocumentLink, Event, EventMedia, EventParticipant, Person
from app.models.enums import (
    CitationTarget,
    DocumentCategory,
    DocumentLinkTarget,
    EventSignificance,
    LifeEventCategory,
    PrivacyLevel,
    RecordPrivacyLevel,
)
from app.modules.documents import access
from app.modules.documents import service as documents
from app.modules.documents.schemas import DocumentLinkIn
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import EventOut
from app.modules.genealogy.serialize import Serializer, citation_counts, date_display, media_summary
from app.modules.genealogy.service import get_event_checked
from app.modules.lifeevents.schemas import (
    EventMediaLinkIn,
    EventMediaOut,
    EventMediaUpdate,
    TaggedPerson,
)
from app.modules.sharing import core

MAX_PHOTOS_PER_EVENT = 200


# ---------------------------------------------------------------- tree-wide listing
@dataclass
class EventFilters:
    person_id: uuid.UUID | None = None
    categories: list[LifeEventCategory] | None = None
    significance: list[EventSignificance] | None = None
    from_year: int | None = None
    to_year: int | None = None
    geotagged: bool | None = None
    important_only: bool = False
    q: str | None = None


def serialize_events(ctx: TreeContext, events: list[Event]) -> list[EventOut]:
    """Privacy-filtered EventOut for a batch of events (order kept, invisible ones dropped)."""
    if not events:
        return []
    ids = {e.id for e in events}
    parts: dict[uuid.UUID, list[EventParticipant]] = defaultdict(list)
    for p in ctx.db.scalars(
        select(EventParticipant).where(
            EventParticipant.tree_id == ctx.tree_id, EventParticipant.event_id.in_(ids)
        )
    ):
        parts[p.event_id].append(p)
    subjects = lookup.visible_subjects(ctx, {p.person_id for ps in parts.values() for p in ps})
    ser = Serializer(ctx)
    counts = citation_counts(ctx, CitationTarget.EVENT, ids)
    media = media_summary(ctx, ids)
    out = []
    for e in events:
        if not parts.get(e.id):
            continue  # an event nobody takes part in is not shown
        eo = ser.event_out(e, parts[e.id], subjects, counts, media)
        if eo is not None:
            out.append(eo)
    return out


def _event_query(ctx: TreeContext, f: EventFilters):  # type: ignore[no-untyped-def]
    stmt = select(Event).where(Event.tree_id == ctx.tree_id)
    if f.person_id is not None:
        lookup.get_person(ctx, f.person_id)
        stmt = stmt.where(
            Event.id.in_(
                select(EventParticipant.event_id).where(
                    EventParticipant.tree_id == ctx.tree_id, EventParticipant.person_id == f.person_id
                )
            )
        )
    if f.categories:
        stmt = stmt.where(Event.category.in_(f.categories))
    if f.significance:
        stmt = stmt.where(Event.significance.in_(f.significance))
    if f.important_only:
        stmt = stmt.where((Event.significance != EventSignificance.STANDARD) | Event.category.is_not(None))
    if f.from_year is not None:
        stmt = stmt.where(func.extract("year", Event.date_sort_to) >= f.from_year)
    if f.to_year is not None:
        stmt = stmt.where(func.extract("year", Event.date_sort_from) <= f.to_year)
    if f.geotagged is True:
        stmt = stmt.where(Event.latitude.is_not(None) | Event.place_id.is_not(None))
    elif f.geotagged is False:
        stmt = stmt.where(Event.latitude.is_(None), Event.place_id.is_(None))
    if f.q:
        like = f"%{documents._escape_like(f.q)}%"
        stmt = stmt.where(Event.title.ilike(like, escape="\\") | Event.description.ilike(like, escape="\\"))
    return stmt.order_by(Event.date_sort_from.asc().nulls_last(), Event.id)


def list_events(ctx: TreeContext, f: EventFilters, offset: int, limit: int) -> tuple[list[EventOut], bool]:
    """Visible events in chronological order. Paging counts visible rows only (no hidden-row leaks)."""
    stmt = _event_query(ctx, f)
    visible: list[EventOut] = []
    seen, scan, chunk = 0, 0, max(limit * 3, 100)
    while len(visible) < limit + 1:
        rows = list(ctx.db.scalars(stmt.offset(scan).limit(chunk)))
        scan += len(rows)
        for eo in serialize_events(ctx, rows):
            if seen >= offset:
                visible.append(eo)
            seen += 1
            if len(visible) >= limit + 1:
                break
        if len(rows) < chunk:
            break
    return visible[:limit], len(visible) > limit


# ---------------------------------------------------------------- album
def _require_album_write(ctx: TreeContext, event_id: uuid.UUID) -> tuple[Event, uuid.UUID | None]:
    e, principal = get_event_checked(ctx, event_id)
    ctx.require(Permission.PERSON_WRITE, person_id=principal)
    return e, principal


def _strictest(*levels: PrivacyLevel | None) -> PrivacyLevel:
    """The most restrictive of the given levels (CUSTOM ranks with admins-only)."""
    best = PrivacyLevel.TREE_MEMBERS
    best_rank = -1
    for lv in levels:
        if lv is None:
            continue
        rank = 4 if lv == PrivacyLevel.CUSTOM else _RANK[PrivacyLevel(lv)]
        if rank > best_rank:
            best, best_rank = PrivacyLevel(lv), rank
    return best


def inherited_privacy(ctx: TreeContext, e: Event, principal: uuid.UUID | None) -> PrivacyLevel:
    """Default privacy for a new event photo: the strictest of the tree default, the event's own
    level and its principal person's level (privacy inheritance, ADR-0015)."""
    person_level = None
    if principal is not None:
        person_level = ctx.db.scalar(
            select(Person.privacy_level).where(Person.tree_id == ctx.tree_id, Person.id == principal)
        )
    return _strictest(PrivacyLevel(ctx.tree.default_person_privacy), e.privacy_level, person_level)


def _tag_people(ctx: TreeContext, doc: Document, person_ids: list[uuid.UUID]) -> None:
    for pid in dict.fromkeys(person_ids):
        exists = ctx.db.scalar(
            select(DocumentLink.id).where(
                DocumentLink.tree_id == ctx.tree_id,
                DocumentLink.document_id == doc.id,
                DocumentLink.target_type == DocumentLinkTarget.PERSON,
                DocumentLink.target_id == pid,
            )
        )
        if exists is None:
            documents._add_link(
                ctx, doc, DocumentLinkIn(target_type=DocumentLinkTarget.PERSON, target_id=pid)
            )


def _set_cover(ctx: TreeContext, event_id: uuid.UUID, media_id: uuid.UUID) -> None:
    ctx.db.execute(
        update(EventMedia)
        .where(EventMedia.tree_id == ctx.tree_id, EventMedia.event_id == event_id, EventMedia.id != media_id)
        .values(is_cover=False)
    )
    ctx.db.flush()


def _count(ctx: TreeContext, event_id: uuid.UUID) -> int:
    return int(
        ctx.db.scalar(
            select(func.count())
            .select_from(EventMedia)
            .where(EventMedia.tree_id == ctx.tree_id, EventMedia.event_id == event_id)
        )
        or 0
    )


def _add_media(
    ctx: TreeContext,
    e: Event,
    doc: Document,
    *,
    caption: str | None,
    taken_date: GenealogicalDate | None,
    is_cover: bool,
) -> EventMedia:
    if _count(ctx, e.id) >= MAX_PHOTOS_PER_EVENT:
        raise Unprocessable(f"An event album holds at most {MAX_PHOTOS_PER_EVENT} photos", code="album_full")
    exists = ctx.db.scalar(
        select(EventMedia.id).where(
            EventMedia.tree_id == ctx.tree_id, EventMedia.event_id == e.id, EventMedia.document_id == doc.id
        )
    )
    if exists is not None:
        raise Conflict("This photo is already in the event's album", code="duplicate_media")
    m = EventMedia(
        tree_id=ctx.tree_id,
        event_id=e.id,
        document_id=doc.id,
        caption=(caption or "").strip() or None,
        taken_date=date_to_json(taken_date),
        is_cover=False,
        sort_order=_count(ctx, e.id),
        created_by=ctx.user_id,
    )
    ctx.db.add(m)
    ctx.db.flush()
    first = m.sort_order == 0
    if is_cover or first:
        _set_cover(ctx, e.id, m.id)
        m.is_cover = True
        ctx.db.flush()
    # the photo is also linked to the event in the vault ("documents about this event")
    linked = ctx.db.scalar(
        select(DocumentLink.id).where(
            DocumentLink.tree_id == ctx.tree_id,
            DocumentLink.document_id == doc.id,
            DocumentLink.target_type == DocumentLinkTarget.EVENT,
            DocumentLink.target_id == e.id,
        )
    )
    if linked is None:
        documents._add_link(ctx, doc, DocumentLinkIn(target_type=DocumentLinkTarget.EVENT, target_id=e.id))
    audit.log(
        ctx,
        "event.photo_added",
        target_type="event",
        target_id=e.id,
        details={"document_id": str(doc.id), "cover": m.is_cover},
    )
    return m


def _album_photo_sharing(
    ctx: TreeContext,
    e: Event,
    principal: uuid.UUID | None,
    person_ids: list[uuid.UUID],
    privacy_level: RecordPrivacyLevel | PrivacyLevel | None,
    audience_branch_id: uuid.UUID | None,
    allow_download: bool | None,
) -> tuple[RecordPrivacyLevel, uuid.UUID | None, bool]:
    """Who sees a new album photo (ADR-0027 §5, §9; ADR-0015).

    The ceiling is the event and every protected person in the photo (the principal included).
    Without a choice: Only me (no download) when a protected living person is in it; otherwise
    ADR-0015's inheritance (the strictest of the tree default, the event and its principal).
    """
    people = list(dict.fromkeys([*([principal] if principal else []), *person_ids]))
    person_caps = core.caps_for_people(ctx, people)
    caps = person_caps + [c for c in [core.event_cap(ctx, e)] if c is not None]
    if privacy_level is not None:
        level = RecordPrivacyLevel(privacy_level)
        if level == RecordPrivacyLevel.PUBLIC_DECEASED_ONLY:
            raise Unprocessable("Records cannot be public", code="public_not_supported")
        branch = audience_branch_id if level == RecordPrivacyLevel.FAMILY_BRANCH else None
        if not core.within(level, branch, caps):
            # never looser than its event and the people in it: a photo of a private event stays private
            raise Unprocessable(
                "A photo cannot be more visible than its event and people", code="privacy_too_open"
            )
        downloadable = (not person_caps) if allow_download is None else allow_download
        return level, branch, downloadable
    if person_caps:
        return RecordPrivacyLevel.ONLY_ME, None, False if allow_download is None else allow_download
    level = RecordPrivacyLevel(inherited_privacy(ctx, e, principal))
    branch = None
    if not core.within(level, None, caps):
        level, branch = core.narrowest(caps)
    return level, branch, True if allow_download is None else allow_download


def upload_photo(
    ctx: TreeContext,
    event_id: uuid.UUID,
    *,
    data: bytes,
    filename: str | None,
    title: str | None,
    caption: str | None,
    taken_date: GenealogicalDate | None,
    is_cover: bool,
    person_ids: list[uuid.UUID],
    privacy_level: RecordPrivacyLevel | PrivacyLevel | None,
    audience_branch_id: uuid.UUID | None = None,
    allow_download: bool | None = None,
) -> EventMedia:
    e, principal = _require_album_write(ctx, event_id)
    for pid in person_ids:
        lookup.get_person(ctx, pid)  # 404 for hidden or unknown people, before anything is stored
    sniffed = validate_upload(data)
    if not sniffed.mime.startswith("image/"):
        raise Unprocessable("Only images can be added to an event's photos", code="not_an_image")
    level, branch, downloadable = _album_photo_sharing(
        ctx, e, principal, person_ids, privacy_level, audience_branch_id, allow_download
    )
    doc = documents.upload(
        ctx,
        data=data,
        filename=filename,
        category=DocumentCategory.PHOTO,
        title=(title or caption or e.title or filename or "Photo")[:400],
        description=caption,
        privacy_level=level,
        document_date=taken_date,
        audience_branch_id=branch,
        allow_download=downloadable,
    )
    m = _add_media(ctx, e, doc, caption=caption, taken_date=taken_date, is_cover=is_cover)
    if principal is not None and principal not in person_ids:
        person_ids = [principal, *person_ids]
    _tag_people(ctx, doc, person_ids)
    documents.schedule_processing(ctx, doc)  # thumbnails and previews (commits)
    return m


def link_photo(ctx: TreeContext, event_id: uuid.UUID, body: EventMediaLinkIn) -> EventMedia:
    e, _principal = _require_album_write(ctx, event_id)
    doc = access.get_document(ctx, body.document_id)
    if doc.category != DocumentCategory.PHOTO or not doc.mime_type.startswith("image/"):
        raise Unprocessable("Only photos can be added to an event's photos", code="not_an_image")
    for pid in body.person_ids:
        lookup.get_person(ctx, pid)
    cap = core.event_cap(ctx, e)
    if cap is not None and not core.within(doc.privacy_level, doc.audience_branch_id, [cap]):
        # adding a photo to an album never narrows someone's photo silently: its owner narrows it first
        raise Unprocessable(
            "This photo is shared more widely than the event; make it more private first",
            code="privacy_too_open",
        )
    m = _add_media(ctx, e, doc, caption=body.caption, taken_date=body.taken_date, is_cover=body.is_cover)
    _tag_people(ctx, doc, body.person_ids)
    return m


def _get_media(ctx: TreeContext, event_id: uuid.UUID, media_id: uuid.UUID) -> EventMedia:
    m = ctx.db.scalar(
        select(EventMedia).where(
            EventMedia.tree_id == ctx.tree_id, EventMedia.id == media_id, EventMedia.event_id == event_id
        )
    )
    if m is None:
        raise NotFound("Photo not found")
    access.get_document(ctx, m.document_id)  # hidden photo → 404
    return m


def update_media(
    ctx: TreeContext, event_id: uuid.UUID, media_id: uuid.UUID, body: EventMediaUpdate
) -> EventMedia:
    _require_album_write(ctx, event_id)
    m = _get_media(ctx, event_id, media_id)
    fields = body.model_fields_set
    if "caption" in fields:
        m.caption = (body.caption or "").strip() or None
    if "taken_date" in fields:
        m.taken_date = date_to_json(body.taken_date)
    if body.sort_order is not None:
        m.sort_order = body.sort_order
    if body.is_cover is True:
        _set_cover(ctx, event_id, m.id)
        m.is_cover = True
    elif body.is_cover is False:
        m.is_cover = False
    if body.add_person_ids:
        for pid in body.add_person_ids:
            lookup.get_person(ctx, pid)
        _tag_people(ctx, access.get_document(ctx, m.document_id), body.add_person_ids)
    m.updated_by = ctx.user_id
    ctx.db.flush()
    audit.log(
        ctx,
        "event.photo_changed",
        target_type="event",
        target_id=event_id,
        details={"fields": sorted(fields)},
    )
    return m


def remove_media(ctx: TreeContext, event_id: uuid.UUID, media_id: uuid.UUID) -> None:
    """Take a photo out of the album. The photo stays in the vault (with its person tags)."""
    _require_album_write(ctx, event_id)
    m = _get_media(ctx, event_id, media_id)
    ctx.db.execute(
        delete(DocumentLink).where(
            DocumentLink.tree_id == ctx.tree_id,
            DocumentLink.document_id == m.document_id,
            DocumentLink.target_type == DocumentLinkTarget.EVENT,
            DocumentLink.target_id == event_id,
        )
    )
    was_cover = m.is_cover
    ctx.db.delete(m)
    ctx.db.flush()
    if was_cover:
        nxt = ctx.db.scalar(
            select(EventMedia)
            .where(EventMedia.tree_id == ctx.tree_id, EventMedia.event_id == event_id)
            .order_by(EventMedia.sort_order, EventMedia.created_at)
            .limit(1)
        )
        if nxt is not None:
            nxt.is_cover = True
    audit.log(
        ctx,
        "event.photo_removed",
        target_type="event",
        target_id=event_id,
        details={"document_id": str(m.document_id)},
    )


def album(ctx: TreeContext, event_id: uuid.UUID) -> list[EventMediaOut]:
    get_event_checked(ctx, event_id)
    rows = ctx.db.execute(
        select(EventMedia, Document)
        .join(Document, (Document.id == EventMedia.document_id) & (Document.tree_id == EventMedia.tree_id))
        .where(
            EventMedia.tree_id == ctx.tree_id, EventMedia.event_id == event_id, Document.deleted_at.is_(None)
        )
        .order_by(EventMedia.sort_order, EventMedia.created_at)
    ).all()
    pairs = [(m, d) for m, d in rows if access.can_view_document(ctx, d)]
    return media_out(ctx, pairs)


def media_out(ctx: TreeContext, pairs: list[tuple[EventMedia, Document]]) -> list[EventMediaOut]:
    if not pairs:
        return []
    doc_ids = [d.id for _, d in pairs]
    links = documents.links_for(ctx, doc_ids)
    person_ids = {
        lk.target_id for ls in links.values() for lk in ls if lk.target_type == DocumentLinkTarget.PERSON
    }
    visible = lookup.visible_subjects(ctx, person_ids)
    out = []
    for m, d in pairs:
        people = [
            TaggedPerson(
                person_id=lk.target_id, display_name=visible[lk.target_id].person.preferred_display_name
            )
            for lk in links[d.id]
            if lk.target_type == DocumentLinkTarget.PERSON and lk.target_id in visible
        ]
        out.append(
            EventMediaOut(
                id=m.id,
                event_id=m.event_id,
                document_id=d.id,
                caption=m.caption,
                taken_date=m.taken_date,
                taken_date_display=date_display(m.taken_date),
                is_cover=m.is_cover,
                sort_order=m.sort_order,
                created_at=m.created_at,
                document=documents.document_out(ctx, d, links[d.id]),
                people=people,
            )
        )
    return out


def person_photos(ctx: TreeContext, person_id: uuid.UUID) -> list[EventMediaOut]:
    """Album photos from the person's events (for the person's Photos tab)."""
    lookup.get_person(ctx, person_id)
    event_ids = select(EventParticipant.event_id).where(
        EventParticipant.tree_id == ctx.tree_id, EventParticipant.person_id == person_id
    )
    events = list(ctx.db.scalars(select(Event).where(Event.tree_id == ctx.tree_id, Event.id.in_(event_ids))))
    visible_events = {eo.id for eo in serialize_events(ctx, events)}
    if not visible_events:
        return []
    rows = ctx.db.execute(
        select(EventMedia, Document)
        .join(Document, (Document.id == EventMedia.document_id) & (Document.tree_id == EventMedia.tree_id))
        .where(
            EventMedia.tree_id == ctx.tree_id,
            EventMedia.event_id.in_(visible_events),
            Document.deleted_at.is_(None),
        )
        .order_by(EventMedia.created_at)
    ).all()
    return media_out(ctx, [(m, d) for m, d in rows if access.can_view_document(ctx, d)])
