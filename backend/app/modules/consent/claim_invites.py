"""Shareable claim-your-profile invites (ADR-0011), e.g. sent over WhatsApp.

The link is a single-use bearer token in the URL fragment. Accepting it only files a profile claim
with the relative's own consent; a tree admin still approves the claim before any access is given.

The link holder can also answer "this isn't me" (the link is cancelled, nothing else changes) or
"this is me, remove me" (the profile is hidden from everyone but tree admins at once, and an admin
erases it or restores it). A forwarded link can therefore never erase anyone on its own.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from fastapi import APIRouter, status
from pydantic import Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, TreeCtx
from app.api.schemas import ApiModel, Message
from app.authz.permissions import Permission
from app.core import audit
from app.core.config import get_settings
from app.core.db import bind_tree
from app.core.errors import ApiError, Conflict, Forbidden, NotFound, Unprocessable
from app.core.ratelimit import enforce
from app.core.security import new_token, token_hash
from app.models import Person, ProfileClaim, ProfileClaimInvite, Tree, User
from app.models.enums import ClaimKind, ClaimStatus, PrivacyLevel, ProfileStatus, Role
from app.modules.consent import statements
from app.modules.consent.statements import StatementKind
from app.modules.genealogy import lookup

CLAIM_INVITE_TTL_DAYS = 7

router = APIRouter(tags=["consent"])

InviteState = Literal["active", "used", "declined", "expired", "revoked"]

# Levels that already hide a profile from everyone but tree admins (and its claimant).
_HIDDEN_LEVELS = {PrivacyLevel.PRIVATE_TREE_ADMINS, PrivacyLevel.PRIVATE_SELF}


class ClaimInviteCreate(ApiModel):
    offered_role: Literal["VIEWER", "CONTRIBUTOR"] = "VIEWER"


class ClaimInviteOut(ApiModel):
    id: uuid.UUID
    person_id: uuid.UUID
    offered_role: Role
    expires_at: dt.datetime
    created_at: dt.datetime
    created_by: uuid.UUID | None
    used_at: dt.datetime | None
    revoked_at: dt.datetime | None
    state: InviteState = "active"
    # Tree-side projection only. Creation responses keep these null so the bearer-link response
    # does not grow a second source of person or review data.
    person_name: str | None = None
    claim_status: ClaimStatus | None = None
    claim_kind: ClaimKind | None = None


class ClaimInviteCreated(ClaimInviteOut):
    url: str
    token: str


class ClaimInvitePreview(ApiModel):
    tree_name: str
    person_name: str
    invited_by: str | None
    offered_role: Role
    expires_at: dt.datetime
    state: InviteState
    claim_id: uuid.UUID | None = None
    claim_kind: ClaimKind | None = None


class ClaimInviteAccept(ApiModel):
    consent_version: str = Field(min_length=1, max_length=40)
    language: str = Field(min_length=2, max_length=10)
    confirm_adult: bool
    message: str | None = Field(default=None, max_length=2000)


class RemovalRequestIn(ApiModel):
    confirm_is_me: bool
    message: str | None = Field(default=None, max_length=2000)


class ClaimSubmitted(ApiModel):
    claim_id: uuid.UUID
    kind: ClaimKind = ClaimKind.CLAIM
    status: ClaimStatus
    tree_name: str
    person_name: str


def _state(inv: ProfileClaimInvite) -> InviteState:
    if inv.revoked_at is not None:
        return "revoked"
    if inv.declined_at is not None:
        return "declined"
    if inv.used_at is not None:
        return "used"
    if inv.expires_at < dt.datetime.now(dt.UTC):
        return "expired"
    return "active"


def _out(
    inv: ProfileClaimInvite,
    *,
    person_name: str | None = None,
    claim_status: ClaimStatus | None = None,
    claim_kind: ClaimKind | None = None,
) -> ClaimInviteOut:
    return ClaimInviteOut.model_validate(inv).model_copy(
        update={
            "state": _state(inv),
            "person_name": person_name,
            "claim_status": claim_status,
            "claim_kind": claim_kind,
        }
    )


def claim_url(token: str) -> str:
    # Fragment, not path: never sent to servers, proxies, logs, Referer or link-preview crawlers.
    return f"{get_settings().public_base_url.rstrip('/')}/claim#{token}"


# ------------------------------------------------------------ tree side (members)
@router.post(
    "/trees/{tree_id}/people/{person_id}/claim-invites",
    response_model=ClaimInviteCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_claim_invite(person_id: uuid.UUID, body: ClaimInviteCreate, ctx: TreeCtx) -> ClaimInviteCreated:
    subject = lookup.get_person_subject(ctx, person_id)
    person = subject.person
    ctx.require(Permission.PERSON_WRITE, person_id=person.id)
    role = Role(body.offered_role)
    if role != Role.VIEWER and not ctx.is_admin:
        raise Forbidden("Only tree admins can invite relatives as contributors")
    if person.claimed_by_user_id is not None:
        raise Conflict("This profile has already been claimed", code="already_claimed")
    if pending_removal(ctx.db, ctx.tree_id, person.id):
        raise Conflict("This person has asked to be removed from the tree", code="removal_pending")
    if person.profile_status == ProfileStatus.DECEASED or not subject.is_protected:
        raise Unprocessable("Only living relatives can claim a profile", code="not_living")
    if subject.is_minor:
        raise Unprocessable(
            "Children cannot claim a profile. A parent or guardian manages it.", code="minor_profile"
        )
    enforce(f"claim-invite:create:{ctx.user_id}", 30, 3600)
    token = new_token()
    inv = ProfileClaimInvite(
        tree_id=ctx.tree_id,
        person_id=person.id,
        token_hash=token_hash(token),
        offered_role=role,
        branch_id=ctx.branch_scope,
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=CLAIM_INVITE_TTL_DAYS),
        created_by=ctx.user_id,
    )
    ctx.db.add(inv)
    ctx.db.flush()
    audit.log(
        ctx,
        "profile.claim_invite_created",
        target_type="person",
        target_id=person.id,
        details={"role": role.value},
    )
    return ClaimInviteCreated(**_out(inv).model_dump(), url=claim_url(token), token=token)


@router.get("/trees/{tree_id}/claim-invites", response_model=list[ClaimInviteOut])
def list_claim_invites(ctx: TreeCtx, person_id: uuid.UUID | None = None) -> list[ClaimInviteOut]:
    q = select(ProfileClaimInvite).where(ProfileClaimInvite.tree_id == ctx.tree_id)
    if not ctx.is_admin:
        q = q.where(ProfileClaimInvite.created_by == ctx.user_id)
    if person_id is not None:
        q = q.where(ProfileClaimInvite.person_id == person_id)
    rows = list(ctx.db.scalars(q.order_by(ProfileClaimInvite.created_at.desc())))
    visible = lookup.visible_subjects(ctx, [r.person_id for r in rows])
    visible_rows = [r for r in rows if r.person_id in visible]
    claims = {
        invite_id: (claim_status, claim_kind)
        for invite_id, claim_status, claim_kind in ctx.db.execute(
            select(ProfileClaim.invite_id, ProfileClaim.status, ProfileClaim.kind).where(
                ProfileClaim.tree_id == ctx.tree_id,
                ProfileClaim.invite_id.in_([r.id for r in visible_rows]),
            )
        )
        if invite_id is not None
    }
    return [
        _out(
            row,
            person_name=visible[row.person_id].person.preferred_display_name,
            claim_status=claims.get(row.id, (None, None))[0],
            claim_kind=claims.get(row.id, (None, None))[1],
        )
        for row in visible_rows
    ]


@router.delete("/trees/{tree_id}/claim-invites/{invite_id}", response_model=Message)
def revoke_claim_invite(invite_id: uuid.UUID, ctx: TreeCtx) -> Message:
    inv = lookup.get_in_tree(ctx, ProfileClaimInvite, invite_id, "Invite")
    if not ctx.is_admin and inv.created_by != ctx.user_id:
        raise NotFound("Invite not found")
    if _state(inv) != "active":
        raise Conflict("Only an active invitation can be revoked", code="invite_not_active")
    inv.revoked_at = dt.datetime.now(dt.UTC)
    audit.log(ctx, "profile.claim_invite_revoked", target_type="person", target_id=inv.person_id)
    return Message(message="Invite revoked")


def pending_removal(db: DbDep, tree_id: uuid.UUID, person_id: uuid.UUID) -> bool:
    """Whether the person has an unreviewed "remove me" request (which freezes new claims and links)."""
    return (
        db.scalar(
            select(ProfileClaim.id).where(
                ProfileClaim.tree_id == tree_id,
                ProfileClaim.person_id == person_id,
                ProfileClaim.kind == ClaimKind.REMOVAL,
                ProfileClaim.status == ClaimStatus.REQUESTED,
            )
        )
        is not None
    )


# ------------------------------------------------------------ link holder side
def _find(db: DbDep, token: str, *, lock: bool = False) -> ProfileClaimInvite:
    q = select(ProfileClaimInvite).where(ProfileClaimInvite.token_hash == token_hash(token))
    if lock:
        q = q.with_for_update()
    inv = db.scalar(q)
    if inv is None or inv.revoked_at is not None:
        raise NotFound("Invite not found")
    # The link holder is not a member yet: the matching 256-bit token is what scopes this request to
    # the invite's tree, so bind it for row-level security (ADR-0002 §7) before reading tree data.
    bind_tree(db, inv.tree_id)
    return inv


def _live_person(db: DbDep, inv: ProfileClaimInvite) -> Person:
    person = db.scalar(
        select(Person).where(
            Person.tree_id == inv.tree_id, Person.id == inv.person_id, Person.deleted_at.is_(None)
        )
    )
    tree = db.get(Tree, inv.tree_id)
    if person is None or tree is None or tree.deleted_at is not None:
        raise NotFound("Invite not found")
    return person


def _narrow_linked_records(db: DbDep, tree_id: uuid.UUID, person_id: uuid.UUID) -> None:
    """A hidden profile narrows the records linked to it at once, like any privacy change
    (ADR-0027 §5). Done as the system: the link holder is not a member and gains nothing; owners are
    told their record was made more private, never why or by whom. Declining the request restores
    the profile but never widens a record again; its owner decides."""
    from app.authz.context import TreeContext
    from app.modules.sharing.core import enforce_person_ceiling

    tree = db.get(Tree, tree_id)
    if tree is None:  # _live_person checked it
        return
    db.flush()
    system = TreeContext(
        db=db, tree=tree, user=None, membership=None, roles=frozenset(), permissions=frozenset()
    )
    enforce_person_ceiling(system, person_id)


def _gone(inv: ProfileClaimInvite, user: User) -> None:
    """Used (by someone else) or expired links reveal nothing about the tree or the person."""
    state = _state(inv)
    if state == "expired":
        raise ApiError("This invite link has expired", code="invite_expired", status_code=410)
    # After "this isn't me" the link shows nothing to anyone, including whoever declined it.
    if state == "declined" or (state == "used" and inv.used_by != user.id):
        raise ApiError("This invite link has already been used", code="invite_used", status_code=410)


@router.get("/claim-invites/{token}", response_model=ClaimInvitePreview)
def preview_claim_invite(token: str, user: CurrentUser, db: DbDep) -> ClaimInvitePreview:
    enforce(f"claim-invite:open:{user.id}", 30, 60)
    inv = _find(db, token)
    _gone(inv, user)
    person = _live_person(db, inv)
    tree = db.get(Tree, inv.tree_id)
    inviter = db.get(User, inv.created_by) if inv.created_by else None
    claim = None
    if inv.used_by == user.id:
        claim = db.scalar(select(ProfileClaim).where(ProfileClaim.invite_id == inv.id))
    return ClaimInvitePreview(
        tree_name=tree.name if tree else "",
        person_name=person.preferred_display_name,
        invited_by=inviter.display_name if inviter else None,
        offered_role=inv.offered_role,
        expires_at=inv.expires_at,
        state=_state(inv),
        claim_id=claim.id if claim else None,
        claim_kind=claim.kind if claim else None,
    )


@router.post(
    "/claim-invites/{token}/accept", response_model=ClaimSubmitted, status_code=status.HTTP_201_CREATED
)
def accept_claim_invite(token: str, body: ClaimInviteAccept, user: CurrentUser, db: DbDep) -> ClaimSubmitted:
    enforce(f"claim-invite:open:{user.id}", 30, 60)
    inv = _find(db, token, lock=True)
    _gone(inv, user)
    if inv.used_at is not None:
        raise Conflict("You have already used this invite", code="invite_used")
    if not body.confirm_adult:
        raise Unprocessable("You must be 18 or older to claim a profile yourself", code="adult_required")
    stmt = statements.verify(StatementKind.PROFILE_CLAIM, body.consent_version, body.language)
    person = _live_person(db, inv)
    if person.claimed_by_user_id is not None:
        raise Conflict("This profile has already been claimed", code="already_claimed")
    if pending_removal(db, inv.tree_id, person.id):
        raise Conflict("This person has asked to be removed from the tree", code="removal_pending")
    already_linked = db.scalar(
        select(Person.id).where(
            Person.tree_id == inv.tree_id, Person.claimed_by_user_id == user.id, Person.deleted_at.is_(None)
        )
    )
    if already_linked is not None:
        raise Conflict("You have already claimed a profile in this tree", code="already_linked")
    now = dt.datetime.now(dt.UTC)
    claim = ProfileClaim(
        tree_id=inv.tree_id,
        person_id=person.id,
        user_id=user.id,
        message=body.message,
        invite_id=inv.id,
        consent_version=stmt.version,
        consent_language=stmt.language,
        consent_sha256=stmt.sha256,
        consent_at=now,
        created_by=user.id,
    )
    db.add(claim)
    inv.used_at = now
    inv.used_by = user.id
    db.flush()
    audit.record(
        db,
        action="profile.claim_requested",
        actor_user_id=user.id,
        tree_id=inv.tree_id,
        target_type="person",
        target_id=person.id,
        details={"via": "invite"},
    )
    tree = db.get(Tree, inv.tree_id)
    return ClaimSubmitted(
        claim_id=claim.id,
        status=claim.status,
        tree_name=tree.name if tree else "",
        person_name=person.preferred_display_name,
    )


def _use(inv: ProfileClaimInvite, user: User) -> dt.datetime:
    if inv.used_at is not None:
        raise Conflict("You have already used this invite", code="invite_used")
    now = dt.datetime.now(dt.UTC)
    inv.used_at = now
    inv.used_by = user.id
    return now


@router.post("/claim-invites/{token}/decline", response_model=Message)
def decline_claim_invite(token: str, user: CurrentUser, db: DbDep) -> Message:
    """Answer "this isn't me": cancel the link. No person data is read back or changed."""
    enforce(f"claim-invite:open:{user.id}", 30, 60)
    inv = _find(db, token, lock=True)
    _gone(inv, user)
    inv.declined_at = _use(inv, user)
    audit.record(
        db,
        action="profile.claim_invite_declined",
        actor_user_id=user.id,
        tree_id=inv.tree_id,
        target_type="person",
        target_id=inv.person_id,
        details={"reason": "not_me"},
    )
    return Message(message="Thanks for letting us know. This link no longer works.")


@router.post(
    "/claim-invites/{token}/request-removal",
    response_model=ClaimSubmitted,
    status_code=status.HTTP_201_CREATED,
)
def request_removal(token: str, body: RemovalRequestIn, user: CurrentUser, db: DbDep) -> ClaimSubmitted:
    """Answer "this is me, remove me": hide the profile now and ask a tree admin to erase it.

    The link is a bearer token that may have been forwarded, so it never erases anything by itself:
    hiding is immediate and reversible, erasure needs an admin (ADR-0011).
    """
    enforce(f"claim-invite:open:{user.id}", 30, 60)
    inv = _find(db, token, lock=True)
    _gone(inv, user)
    if not body.confirm_is_me:
        raise Unprocessable("Please confirm that this profile is about you", code="confirmation_required")
    person = _live_person(db, inv)
    if person.claimed_by_user_id is not None:
        # a claimed profile is managed by its owner, never by whoever holds an old link
        raise Conflict("This profile has already been claimed", code="already_claimed")
    now = _use(inv, user)
    restore = None
    if person.privacy_level not in _HIDDEN_LEVELS:
        restore = person.privacy_level
        person.privacy_level = PrivacyLevel.PRIVATE_TREE_ADMINS
    claim = ProfileClaim(
        tree_id=inv.tree_id,
        person_id=person.id,
        user_id=user.id,
        kind=ClaimKind.REMOVAL,
        message=body.message,
        invite_id=inv.id,
        restore_privacy_level=restore,
        created_by=user.id,
    )
    db.add(claim)
    if restore is not None:
        _narrow_linked_records(db, inv.tree_id, person.id)
    # nobody else can claim the profile through another link while the request is open
    for other in db.scalars(
        select(ProfileClaimInvite).where(
            ProfileClaimInvite.tree_id == inv.tree_id,
            ProfileClaimInvite.person_id == person.id,
            ProfileClaimInvite.id != inv.id,
            ProfileClaimInvite.used_at.is_(None),
            ProfileClaimInvite.revoked_at.is_(None),
        )
    ):
        other.revoked_at = now
    db.flush()
    audit.record(
        db,
        action="profile.removal_requested",
        actor_user_id=user.id,
        tree_id=inv.tree_id,
        target_type="person",
        target_id=person.id,
        details={"via": "invite", "hidden": restore is not None},
    )
    tree = db.get(Tree, inv.tree_id)
    return ClaimSubmitted(
        claim_id=claim.id,
        kind=claim.kind,
        status=claim.status,
        tree_name=tree.name if tree else "",
        person_name=person.preferred_display_name,
    )
