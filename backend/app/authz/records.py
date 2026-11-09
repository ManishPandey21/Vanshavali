"""Who may change a tradition entry's audience (ADR-0027 §1, §10).

Documents have their own, richer rules in ``documents.sharing`` (ceilings, a server-computed
audience). Tradition entries use these, with the same meaning:

* The **owner** may set any audience, and is the only one who may widen it, convert a legacy
  ``CUSTOM`` / ``PRIVATE_SELF`` entry, change a ``FAMILY_BRANCH`` entry's branch, or change anything
  on a private (``ONLY_ME`` / ``SELECTED_MEMBERS``) entry.
* A **tree admin** may only *narrow* an entry on a shared audience they can already see.
* A **grantee** changes nothing.

Promoting a member to any role grants no access to private records: roles never enter
``record_allows``'s private branch.
"""

from __future__ import annotations

import uuid

from app.authz.privacy import RECORD_RANK, is_private_record_level
from app.core.errors import Forbidden
from app.models.enums import RecordPrivacyLevel

# Levels whose meaning is not one of the five audiences; only the owner converts them (§1).
LEGACY_LEVELS: frozenset[RecordPrivacyLevel] = frozenset(
    {RecordPrivacyLevel.CUSTOM, RecordPrivacyLevel.PRIVATE_SELF}
)


def is_shared(level: RecordPrivacyLevel | str) -> bool:
    """A level roles can see: not private and not a legacy level."""
    return not is_private_record_level(level) and RecordPrivacyLevel(level) not in LEGACY_LEVELS


def require_audience_change(
    *,
    owner: bool,
    may_manage: bool,
    old_level: RecordPrivacyLevel | str,
    new_level: RecordPrivacyLevel | str,
    old_branch: uuid.UUID | None,
    new_branch: uuid.UUID | None,
) -> None:
    """Raise 403 unless the viewer may move an entry from the old audience to the new one."""
    old_level, new_level = RecordPrivacyLevel(old_level), RecordPrivacyLevel(new_level)
    branch_changed = new_level == RecordPrivacyLevel.FAMILY_BRANCH and new_branch != old_branch
    if old_level == new_level and not branch_changed:
        return
    if owner:
        return
    if may_manage and is_shared(old_level) and RECORD_RANK[new_level] > RECORD_RANK[old_level]:
        return
    raise Forbidden(
        "Only the person who owns this can widen who sees it or change a private setting",
        code="not_content_owner",
    )


def require_owner_for_private(owner: bool, level: RecordPrivacyLevel | str) -> None:
    """Changes to a private entry are its owner's alone; grantees and roles change nothing."""
    if is_private_record_level(level) and not owner:
        raise Forbidden("Only the person who owns this can change it", code="not_content_owner")
