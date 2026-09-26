"""Consent ledger (PRS §31) and claim-your-profile workflow (PRS §29)."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, status
from pydantic import Field
from sqlalchemy import select

from app.api.deps import TreeCtx
from app.api.schemas import ApiModel
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Conflict, Forbidden
from app.models import ConsentRecord, ProfileClaim, ProfileClaimInvite, TreeMembership, User
from app.models.enums import ClaimKind, ClaimStatus, ConsentBasis, PrivacyLevel
from app.modules.genealogy import lookup

router = APIRouter(prefix="/trees/{tree_id}", tags=["consent"])


class ConsentIn(ApiModel):
    granted_by_name: str = Field(min_length=1, max_length=200)
    authority_basis: ConsentBasis
    purpose: str = Field(min_length=1, max_length=300)
    data_categories: list[str] = Field(min_length=1, max_length=30)
    expires_at: dt.datetime | None = None
    evidence_document_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ConsentOut(ApiModel):
    id: uuid.UUID
    subject_person_id: uuid.UUID
    granted_by_user_id: uuid.UUID | None
    granted_by_name: str
    authority_basis: ConsentBasis
    purpose: str
    data_categories: list[str]
    granted_at: dt.datetime
    expires_at: dt.datetime | None
    withdrawn_at: dt.datetime | None
    evidence_document_id: uuid.UUID | None
    notes: str | None
    active: bool = True


def _consent_out(c: ConsentRecord) -> ConsentOut:
    now = dt.datetime.now(dt.UTC)
    active = c.withdrawn_at is None and (c.expires_at is None or c.expires_at > now)
    return ConsentOut.model_validate(c).model_copy(update={"active": active})


def _can_manage_consent(ctx, person) -> bool:  # type: ignore[no-untyped-def]
    return ctx.has(Permission.PRIVACY_MANAGE) or (
        ctx.user is not None and person.claimed_by_user_id == ctx.user.id
    )


@router.get("/people/{person_id}/consents", response_model=list[ConsentOut])
def list_consents(person_id: uuid.UUID, ctx: TreeCtx) -> list[ConsentOut]:
    person = lookup.get_person(ctx, person_id)
    if not _can_manage_consent(ctx, person):
        raise Forbidden()
    rows = ctx.db.scalars(
        select(ConsentRecord)
        .where(ConsentRecord.tree_id == ctx.tree_id, ConsentRecord.subject_person_id == person.id)
        .order_by(ConsentRecord.granted_at.desc())
    )
    return [_consent_out(c) for c in rows]


@router.post("/people/{person_id}/consents", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
def record_consent(person_id: uuid.UUID, body: ConsentIn, ctx: TreeCtx) -> ConsentOut:
    person = lookup.get_person(ctx, person_id)
    if not _can_manage_consent(ctx, person):
        raise Forbidden()
    if body.evidence_document_id:
        from app.models import Document

        lookup.get_in_tree(ctx, Document, body.evidence_document_id, "Document")
    c = ConsentRecord(
        tree_id=ctx.tree_id,
        subject_person_id=person.id,
        granted_by_user_id=ctx.user_id,
        created_by=ctx.user_id,
        **body.model_dump(),
    )
    ctx.db.add(c)
    ctx.db.flush()
    audit.log(
        ctx,
        "consent.granted",
        target_type="person",
        target_id=person.id,
        details={
            "purpose": body.purpose,
            "basis": body.authority_basis.value,
            "categories": body.data_categories,
        },
    )
    return _consent_out(c)


@router.post("/consents/{consent_id}/withdraw", response_model=ConsentOut)
def withdraw_consent(consent_id: uuid.UUID, ctx: TreeCtx) -> ConsentOut:
    c = lookup.get_in_tree(ctx, ConsentRecord, consent_id, "Consent")
    person = lookup.get_person(ctx, c.subject_person_id)
    if not _can_manage_consent(ctx, person):
        raise Forbidden()
    if c.withdrawn_at is not None:
        raise Conflict("Consent already withdrawn")
    c.withdrawn_at = dt.datetime.now(dt.UTC)
    audit.log(
        ctx, "consent.withdrawn", target_type="person", target_id=person.id, details={"purpose": c.purpose}
    )
    return _consent_out(c)


# ------------------------------------------------------------------ claims
class ClaimIn(ApiModel):
    message: str | None = Field(default=None, max_length=2000)


class ClaimReview(ApiModel):
    note: str | None = Field(default=None, max_length=2000)


class ClaimOut(ApiModel):
    id: uuid.UUID
    person_id: uuid.UUID
    user_id: uuid.UUID
    kind: ClaimKind = ClaimKind.CLAIM
    status: ClaimStatus
    message: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: dt.datetime | None
    review_note: str | None
    created_at: dt.datetime
    via_invite: bool = False
    # Only filled for tree admins, who need to know who is asking before approving.
    claimant_name: str | None = None
    claimant_email: str | None = None


def _claim_out(c: ProfileClaim, claimant: User | None = None) -> ClaimOut:
    out = ClaimOut.model_validate(c).model_copy(update={"via_invite": c.invite_id is not None})
    if claimant is not None:
        out = out.model_copy(
            update={"claimant_name": claimant.display_name, "claimant_email": claimant.email}
        )
    return out


@router.post("/people/{person_id}/claims", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
def request_claim(person_id: uuid.UUID, body: ClaimIn, ctx: TreeCtx) -> ClaimOut:
    person = lookup.get_person(ctx, person_id)
    if person.claimed_by_user_id is not None:
        raise Conflict("This profile has already been claimed", code="already_claimed")
    open_claim = ctx.db.scalar(
        select(ProfileClaim).where(
            ProfileClaim.tree_id == ctx.tree_id,
            ProfileClaim.person_id == person.id,
            ProfileClaim.user_id == ctx.user_id,
            ProfileClaim.status == ClaimStatus.REQUESTED,
        )
    )
    if open_claim:
        raise Conflict("You already have a pending claim for this profile", code="claim_pending")
    from app.modules.consent.claim_invites import pending_removal

    if pending_removal(ctx.db, ctx.tree_id, person.id):
        raise Conflict("This person has asked to be removed from the tree", code="removal_pending")
    claim = ProfileClaim(
        tree_id=ctx.tree_id,
        person_id=person.id,
        user_id=ctx.user_id,
        message=body.message,
        created_by=ctx.user_id,
    )
    ctx.db.add(claim)
    ctx.db.flush()
    audit.log(ctx, "profile.claim_requested", target_type="person", target_id=person.id)
    return _claim_out(claim)


@router.get("/claims", response_model=list[ClaimOut])
def list_claims(ctx: TreeCtx, status_filter: ClaimStatus | None = None) -> list[ClaimOut]:
    q = (
        select(ProfileClaim, User)
        .join(User, User.id == ProfileClaim.user_id)
        .where(ProfileClaim.tree_id == ctx.tree_id)
    )
    admin = ctx.has(Permission.MEMBERS_MANAGE) and ctx.is_admin
    if not admin:
        q = q.where(ProfileClaim.user_id == ctx.user_id)
    if status_filter:
        q = q.where(ProfileClaim.status == status_filter)
    rows = ctx.db.execute(q.order_by(ProfileClaim.created_at.desc())).all()
    return [_claim_out(c, u if admin else None) for c, u in rows]


def _complete_invited_claim(ctx, claim: ProfileClaim, person, membership: TreeMembership | None) -> None:  # type: ignore[no-untyped-def]
    """ADR-0011: an approved invite claim brings a non-member in and records their own consent."""
    invite = ctx.db.scalar(
        select(ProfileClaimInvite).where(
            ProfileClaimInvite.tree_id == ctx.tree_id, ProfileClaimInvite.id == claim.invite_id
        )
    )
    if membership is None and invite is not None:
        membership = TreeMembership(
            tree_id=ctx.tree_id,
            user_id=claim.user_id,
            roles=[invite.offered_role.value],
            branch_id=invite.branch_id,
            linked_person_id=person.id,
            created_by=invite.created_by,
        )
        ctx.db.add(membership)
        ctx.db.flush()
        audit.log(
            ctx,
            "member.joined",
            target_type="membership",
            target_id=membership.id,
            details={"roles": list(membership.roles), "via": "claim_invite"},
        )
    if claim.consent_version and claim.consent_at:
        claimant = ctx.db.get(User, claim.user_id)
        consent = ConsentRecord(
            tree_id=ctx.tree_id,
            subject_person_id=person.id,
            granted_by_user_id=claim.user_id,
            granted_by_name=claimant.display_name if claimant else "Profile owner",
            authority_basis=ConsentBasis.SELF,
            purpose="Keep my profile in this private family tree",
            data_categories=["names", "relationships", "life_events"],
            granted_at=claim.consent_at,
            notes=f"Profile claim statement {claim.consent_version} ({claim.consent_language}), "
            f"sha256 {claim.consent_sha256}",
            created_by=claim.user_id,
        )
        ctx.db.add(consent)
        ctx.db.flush()
        audit.log(
            ctx,
            "consent.granted",
            target_type="person",
            target_id=person.id,
            details={"purpose": consent.purpose, "basis": ConsentBasis.SELF.value, "via": "claim_invite"},
        )


def _review_removal(ctx, claim: ProfileClaim, person, approve: bool) -> None:  # type: ignore[no-untyped-def]
    """ADR-0011: approving a "remove me" request erases the profile; declining it restores visibility."""
    from app.modules.genealogy import service as genealogy

    if approve:
        genealogy.erase_person(ctx, person.id, "Removal requested by the person through a claim link")
        claim.message = None  # it may hold personal details, and the profile is now erased
    elif claim.restore_privacy_level is not None and person.privacy_level == PrivacyLevel.PRIVATE_TREE_ADMINS:
        person.privacy_level = claim.restore_privacy_level
    audit.log(
        ctx,
        "profile.removal_approved" if approve else "profile.removal_rejected",
        target_type="person",
        target_id=person.id,
    )


def _review(ctx, claim_id: uuid.UUID, approve: bool, note: str | None) -> ProfileClaim:  # type: ignore[no-untyped-def]
    if not ctx.is_admin:
        raise Forbidden("Only tree admins can review profile claims")
    claim = lookup.get_in_tree(ctx, ProfileClaim, claim_id, "Claim")
    if claim.status != ClaimStatus.REQUESTED:
        raise Conflict("Claim has already been reviewed")
    person = lookup.get_person(ctx, claim.person_id)
    claim.status = ClaimStatus.APPROVED if approve else ClaimStatus.REJECTED
    claim.reviewed_by = ctx.user_id
    claim.reviewed_at = dt.datetime.now(dt.UTC)
    claim.review_note = note
    if claim.kind == ClaimKind.REMOVAL:
        _review_removal(ctx, claim, person, approve)
        return claim
    if approve:
        if person.claimed_by_user_id is not None:
            raise Conflict("This profile has already been claimed", code="already_claimed")
        person.claimed_by_user_id = claim.user_id
        # Claiming links the profile; it does NOT widen an existing member's roles (PRS §29).
        m = ctx.db.scalar(
            select(TreeMembership).where(
                TreeMembership.tree_id == ctx.tree_id, TreeMembership.user_id == claim.user_id
            )
        )
        if m is not None and m.linked_person_id is None:
            m.linked_person_id = person.id
        if claim.invite_id is not None:
            _complete_invited_claim(ctx, claim, person, m)
    audit.log(
        ctx,
        "profile.claim_approved" if approve else "profile.claim_rejected",
        target_type="person",
        target_id=person.id,
    )
    return claim


@router.post("/claims/{claim_id}/approve", response_model=ClaimOut)
def approve_claim(claim_id: uuid.UUID, body: ClaimReview, ctx: TreeCtx) -> ClaimOut:
    return _claim_out(_review(ctx, claim_id, True, body.note))


@router.post("/claims/{claim_id}/reject", response_model=ClaimOut)
def reject_claim(claim_id: uuid.UUID, body: ClaimReview, ctx: TreeCtx) -> ClaimOut:
    return _claim_out(_review(ctx, claim_id, False, body.note))
