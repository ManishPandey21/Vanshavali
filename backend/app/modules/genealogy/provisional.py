"""Provisional people (ADR-0020 §4, amended 2026-11-05).

A provisional person is someone Smart Add created because the user chose "unknown for now" for a
step on the path (for example the mother, when adding "Mama" to someone whose mother is not
recorded yet). Three things are kept apart:

* **Origin**: ``person.is_provisional`` records *how the person was created*. It is never cleared
  automatically: adding a name does not change where a record came from.
* **Profile details**: a provisional person *needs details* while they have no name record.
* **Verification**: a provisional person is *unverified* until every relationship recorded for them
  carries evidence beyond a bare user assertion, using the existing evidence status
  (``FAMILY_RECOLLECTION``, ``SOURCED`` or ``CORROBORATED``). A name never verifies anything.

Visibility uses the existing privacy engine: a provisional person is created at ``CUSTOM`` privacy
(tree admins and explicit grants) with a view grant for the user who created them. A provisional
person who still needs details or is unverified ("pending") and whom the viewer cannot see is
*concealed*: views leave them out entirely, without the anonymous "private relative" placeholder
used for other hidden people, so their existence cannot be discovered. Default exports leave out
every pending provisional person, whoever exports.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import select

from app.authz.context import TreeContext
from app.models import AccessGrant, NameRecord, Person, Relationship
from app.models.enums import EvidenceStatus, GrantPermission, GrantResource
from app.modules.genealogy import lookup

# evidence that counts as more than one user's say-so (existing EvidenceStatus values)
VERIFYING_EVIDENCE = frozenset(
    {EvidenceStatus.FAMILY_RECOLLECTION, EvidenceStatus.SOURCED, EvidenceStatus.CORROBORATED}
)


class ProvisionalState(StrEnum):
    NEEDS_DETAILS = "needs_details"  # no name yet
    UNVERIFIED = "unverified"  # named, but a relationship has no supporting evidence
    VERIFIED = "verified"  # named and every relationship has supporting evidence


def states(ctx: TreeContext) -> dict[uuid.UUID, ProvisionalState]:
    """State of every live provisional person in the tree (few by nature: unfinished records).

    Cached on the request context; call :func:`forget` after writing one.
    """
    if ctx._provisional_states is not None:
        return ctx._provisional_states
    ids = list(
        ctx.db.scalars(
            select(Person.id).where(
                Person.tree_id == ctx.tree_id, Person.is_provisional.is_(True), Person.deleted_at.is_(None)
            )
        )
    )
    out: dict[uuid.UUID, ProvisionalState] = {}
    if ids:
        named = set(
            ctx.db.scalars(
                select(NameRecord.person_id).where(
                    NameRecord.tree_id == ctx.tree_id, NameRecord.person_id.in_(ids)
                )
            )
        )
        evidence: dict[uuid.UUID, list[EvidenceStatus]] = {pid: [] for pid in ids}
        for a, b, status in ctx.db.execute(
            select(Relationship.person_a_id, Relationship.person_b_id, Relationship.evidence_status).where(
                Relationship.tree_id == ctx.tree_id,
                Relationship.person_a_id.in_(ids) | Relationship.person_b_id.in_(ids),
            )
        ).all():
            for pid in (a, b):
                if pid in evidence:
                    evidence[pid].append(EvidenceStatus(status))
        for pid in ids:
            if pid not in named:
                out[pid] = ProvisionalState.NEEDS_DETAILS
            elif evidence[pid] and all(e in VERIFYING_EVIDENCE for e in evidence[pid]):
                out[pid] = ProvisionalState.VERIFIED
            else:
                out[pid] = ProvisionalState.UNVERIFIED
    ctx._provisional_states = out
    return out


def pending_ids(ctx: TreeContext) -> frozenset[uuid.UUID]:
    """Provisional people who still need details or are unverified (left out of default exports)."""
    return frozenset(pid for pid, s in states(ctx).items() if s != ProvisionalState.VERIFIED)


def concealed_ids(ctx: TreeContext) -> frozenset[uuid.UUID]:
    """Pending provisional people this viewer cannot see: never shown, counted or placeheld."""
    if ctx._concealed is None:
        pending = pending_ids(ctx)
        visible = set(lookup.visible_subjects(ctx, pending)) if pending else set()
        ctx._concealed = frozenset(pending - visible)
    return ctx._concealed


def forget(ctx: TreeContext) -> None:
    """Drop the cached states after a write that can change them."""
    ctx._provisional_states = None
    ctx._concealed = None


def share_with_creator(ctx: TreeContext, person: Person) -> None:
    """Let the user who created a provisional person keep seeing (and so completing) them."""
    if ctx.user_id is None:
        return
    ctx.db.add(
        AccessGrant(
            tree_id=ctx.tree_id,
            user_id=ctx.user_id,
            resource_type=GrantResource.PERSON,
            resource_id=person.id,
            permission=GrantPermission.VIEW,
            created_by=ctx.user_id,
        )
    )
    ctx.db.flush()
    ctx.remember_grant(GrantResource.PERSON, person.id, GrantPermission.VIEW)
    forget(ctx)


def revoke_creator_grants(ctx: TreeContext, person_ids: list[uuid.UUID]) -> None:
    """Undo of a Smart Add: the creator's grants on the people it created go with them."""
    if not person_ids:
        return
    for g in ctx.db.scalars(
        select(AccessGrant).where(
            AccessGrant.tree_id == ctx.tree_id,
            AccessGrant.resource_type == GrantResource.PERSON,
            AccessGrant.resource_id.in_(person_ids),
            AccessGrant.created_by == ctx.user_id,
            AccessGrant.user_id == ctx.user_id,
        )
    ):
        ctx.db.delete(g)
    ctx.db.flush()
    forget(ctx)
