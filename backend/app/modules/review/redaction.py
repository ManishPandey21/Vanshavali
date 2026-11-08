"""Field-level redaction for revision history and proposal diffs (ADR-0021 §3, §4).

Values in history and proposals are shown only when the reader may see the person *and* the
field's group (ADR-0006). Privacy settings, and records carrying their own privacy level, show
values only to privacy managers. A reader who cannot see a changed field cannot decide a proposal.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import FieldGroup, Subject, can_view_field
from app.models import ChangeProposalItem, RecordRevision
from app.models.enums import EventType, ProposalOp, ReviewTarget
from app.modules.genealogy import lookup
from app.modules.heritage.service import ATTRIBUTE_GROUP
from app.modules.review.revisions import MODEL_FOR, _fields, _json

PRIVACY_FIELDS = frozenset({"privacy_level", "field_privacy"})
PERSON_GROUPS = {
    "contact_info": FieldGroup.CONTACT,
    "residential_address": FieldGroup.ADDRESS,
    "notes": FieldGroup.NOTES,
    "gender_identity": FieldGroup.GENDER_IDENTITY,
}
BIRTH_GROUPS = {
    "date": FieldGroup.BIRTH_DATE_FULL,
    "time": FieldGroup.BIRTH_TIME,
    "timezone_id": FieldGroup.BIRTH_TIME,
    "utc_offset_minutes": FieldGroup.BIRTH_TIME,
    "place_id": FieldGroup.BIRTH_PLACE_DETAIL,
    "place_as_recorded": FieldGroup.BIRTH_PLACE_DETAIL,
    "latitude": FieldGroup.BIRTH_PLACE_DETAIL,
    "longitude": FieldGroup.BIRTH_PLACE_DETAIL,
}
ASSERTION_VALUE_FIELDS = frozenset({"value_text", "value_json", "place_id", "notes", "value_status"})


def group_for(t: ReviewTarget, field: str, meta: dict[str, Any]) -> str | None:
    """The field group a field belongs to; None = visible to whoever may see the person."""
    if t == ReviewTarget.PERSON:
        return PERSON_GROUPS.get(field)
    if t == ReviewTarget.EVENT:
        etype = meta.get("type")
        if etype == EventType.BIRTH.value:
            return BIRTH_GROUPS.get(field)
        if etype == EventType.RESIDENCE.value:
            return FieldGroup.ADDRESS
        return None
    if t == ReviewTarget.ASSERTION and field in ASSERTION_VALUE_FIELDS:
        return ATTRIBUTE_GROUP.get(meta.get("attribute") or "", FieldGroup.HERITAGE)
    return None


# records of the family as a whole (ADR-0026): readable as a whole or not at all
FAMILY_TARGETS = frozenset({ReviewTarget.TRADITION, ReviewTarget.KINSHIP_WORD})


def _family_record_hidden(ctx: TreeContext, t: ReviewTarget, record: Any | None) -> bool:
    if t == ReviewTarget.TRADITION:
        from app.modules.traditions.service import may_read

        return record is None or not may_read(ctx, record)
    return not ctx.is_member  # a family word is readable by every member


def is_hidden(
    ctx: TreeContext, t: ReviewTarget, field: str, meta: dict[str, Any], subject: Subject | None
) -> bool:
    if subject is None:
        return True  # the reader may not see the person at all
    if field in PRIVACY_FIELDS or (meta.get("privacy_level") is not None and t != ReviewTarget.PERSON):
        return not ctx.has(Permission.PRIVACY_MANAGE)
    group = group_for(t, field, meta)
    return group is not None and not can_view_field(ctx, subject, group)


def _subject(ctx: TreeContext, person_ids: list[uuid.UUID | None]) -> Subject | None:
    """The subject for field checks: every person concerned must be visible (first one decides groups)."""
    ids = [p for p in person_ids if p]
    if not ids:
        return None
    visible = lookup.visible_subjects(ctx, ids)
    if any(p not in visible for p in ids):
        return None
    return visible[ids[0]]


def _current(ctx: TreeContext, t: ReviewTarget, rid: uuid.UUID | None) -> Any | None:
    if rid is None:
        return None
    return ctx.db.get(MODEL_FOR[t], rid)


def _meta(record: Any | None, patch: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for k in ("type", "attribute", "privacy_level"):
        v = patch.get(k)
        if v is None and record is not None:
            v = getattr(record, k, None)
        if v is not None:
            meta[k] = _json(v)
    return meta


def _people(item: ChangeProposalItem, record: Any | None) -> list[uuid.UUID | None]:
    if item.target_type == ReviewTarget.RELATIONSHIP:
        if record is not None:
            return [record.person_a_id, record.person_b_id]
        return (
            [uuid.UUID(item.patch["person_a_id"]), uuid.UUID(item.patch["person_b_id"])] if item.patch else []
        )
    if item.target_type == ReviewTarget.EVENT and item.op == ProposalOp.CREATE and item.patch:
        return [uuid.UUID(p["person_id"]) for p in item.patch.get("participants", [])]
    return [item.person_id]


def diff_item(ctx: TreeContext, item: ChangeProposalItem) -> tuple[list[dict[str, Any]], bool]:
    """Changes of one item against the record *now* (never a cached copy), and whether it is outdated."""
    record = _current(ctx, item.target_type, item.target_id)
    outdated = item.op != ProposalOp.CREATE and (
        record is None or getattr(record, "deleted_at", None) is not None
    )
    if record is not None:
        key = f"{item.target_type.value}:{record.id}"
        if key in item.base_revisions and item.base_revisions[key] != record.revision:
            outdated = True
    family_hidden = (
        _family_record_hidden(ctx, item.target_type, record) if item.target_type in FAMILY_TARGETS else None
    )
    subject = _subject(ctx, _people(item, record))
    meta = _meta(record, item.patch)
    if item.op == ProposalOp.DELETE:
        fields = (
            {k: (_json(getattr(record, k)), None) for k in _fields(record) if getattr(record, k) is not None}
            if record is not None
            else {}
        )
    else:
        fields = {
            k: (_json(getattr(record, k, None)) if record is not None else None, v)
            for k, v in item.patch.items()
        }
    changes = []
    for field, (cur, new) in sorted(fields.items()):
        if item.op == ProposalOp.UPDATE and cur == new:
            continue
        hidden = (
            family_hidden
            if family_hidden is not None
            else is_hidden(ctx, item.target_type, field, meta, subject)
        )
        changes.append(
            {
                "field": field,
                "current": None if hidden else cur,
                "proposed": None if hidden else new,
                "hidden": hidden,
            }
        )
    return changes, outdated


def item_has_hidden(ctx: TreeContext, item: ChangeProposalItem) -> bool:
    changes, _ = diff_item(ctx, item)
    return any(c["hidden"] for c in changes)


def revision_has_hidden(ctx: TreeContext, rev: RecordRevision, people: list[uuid.UUID]) -> bool:
    if rev.record_type in FAMILY_TARGETS:
        return _family_record_hidden(ctx, rev.record_type, _current(ctx, rev.record_type, rev.record_id))
    subject = _subject(ctx, list(people))
    meta: dict[str, Any] = {}
    for src in (rev.before, rev.after):
        for k in ("type", "attribute", "privacy_level"):
            if src.get(k) is not None:
                meta[k] = src[k]
    record = _current(ctx, rev.record_type, rev.record_id)
    meta = _meta(record, {}) | meta
    return any(is_hidden(ctx, rev.record_type, f, meta, subject) for f in set(rev.before) | set(rev.after))
