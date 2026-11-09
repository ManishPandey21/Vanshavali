"""Who may change a shareable record's audience (ADR-0027 §1, §10).

A shareable record (a document or a tradition entry) has a content owner (§2). The rules:

* The **owner** may set any audience, and is the only one who may widen it, convert a legacy
  ``CUSTOM`` / ``PRIVATE_SELF`` record, change a ``FAMILY_BRANCH`` record's branch, or change
  anything on a record-only (``ONLY_ME`` / ``SELECTED_MEMBERS``) record.
* A **manager** of that kind of record (``document.manage`` for documents, a tree admin for
  traditions) may only *narrow* a record on a shared audience they can already see.
* A **grantee** changes nothing.

Promoting a member to any role grants no access to private records: roles never enter the private
branch of ``level_allows``.
"""

from __future__ import annotations

import uuid

from app.authz.context import TreeContext
from app.authz.privacy import narrowness
from app.core.errors import Forbidden, Unprocessable
from app.models import FamilyBranch
from app.models.enums import RECORD_ONLY_LEVELS, PrivacyLevel

# Levels whose meaning is not one of the five audiences; only the owner converts them (§1).
LEGACY_LEVELS: frozenset[PrivacyLevel] = frozenset({PrivacyLevel.CUSTOM, PrivacyLevel.PRIVATE_SELF})


def is_shared(level: PrivacyLevel | str) -> bool:
    """A level roles can see: not record-only and not a legacy level."""
    level = PrivacyLevel(level)
    return level not in RECORD_ONLY_LEVELS and level not in LEGACY_LEVELS


def require_audience_change(
    ctx: TreeContext,
    *,
    owner: bool,
    may_manage: bool,
    old_level: PrivacyLevel | str,
    new_level: PrivacyLevel | str,
    old_branch: uuid.UUID | None,
    new_branch: uuid.UUID | None,
) -> None:
    """Raise 403 unless the viewer may move a record from the old audience to the new one."""
    old_level, new_level = PrivacyLevel(old_level), PrivacyLevel(new_level)
    branch_changed = new_level == PrivacyLevel.FAMILY_BRANCH and new_branch != old_branch
    if old_level == new_level and not branch_changed:
        return
    if owner:
        return
    if may_manage and is_shared(old_level) and narrowness(new_level) > narrowness(old_level):
        return
    raise Forbidden(
        "Only the person who owns this can widen who sees it or change a private setting",
        code="not_content_owner",
    )


def require_owner_for_private(owner: bool, level: PrivacyLevel | str) -> None:
    """Changes to a record-only record are the owner's alone; grantees and roles change nothing."""
    if PrivacyLevel(level) in RECORD_ONLY_LEVELS and not owner:
        raise Forbidden("Only the person who owns this can change it", code="not_content_owner")


def check_audience_branch(ctx: TreeContext, branch_id: uuid.UUID | None) -> None:
    """An audience branch must be a branch of this tree (404 otherwise)."""
    if branch_id is None:
        return
    from app.modules.genealogy import lookup

    lookup.get_in_tree(ctx, FamilyBranch, branch_id, "Branch")


def reject_record_only(level: PrivacyLevel | None) -> PrivacyLevel | None:
    """People, field groups and other non-record data never take ``ONLY_ME`` / ``SELECTED_MEMBERS``."""
    if level is not None and PrivacyLevel(level) in RECORD_ONLY_LEVELS:
        raise Unprocessable(
            "Only documents and traditions can be shared with 'Only me' or 'Selected members'",
            code="record_only_level",
        )
    return level
