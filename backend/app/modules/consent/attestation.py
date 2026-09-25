"""Family-data attestation (ADR-0011).

Before a user adds people to a tree they confirm, in plain language, that they are allowed to.
This is an accountability record for the person entering data, not the relatives' own consent
(that is captured when a relative claims their profile).
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Query, status
from pydantic import Field
from sqlalchemy import select

from app.api.deps import CurrentUser, TreeCtx
from app.api.schemas import ApiModel
from app.authz.context import TreeContext
from app.core import audit
from app.core.errors import Conflict, Forbidden
from app.models import FamilyDataAttestation
from app.modules.consent import statements
from app.modules.consent.statements import StatementKind

router = APIRouter(tags=["consent"])


class StatementOut(ApiModel):
    kind: StatementKind
    version: str
    language: str
    text: str


class AttestationIn(ApiModel):
    statement_version: str = Field(min_length=1, max_length=40)
    language: str = Field(min_length=2, max_length=10)


class AttestationOut(ApiModel):
    id: uuid.UUID
    statement_version: str
    language: str
    accepted_at: dt.datetime
    withdrawn_at: dt.datetime | None


class AttestationStatus(ApiModel):
    attested: bool
    current_version: str
    attestation: AttestationOut | None


def active_attestation(ctx: TreeContext) -> FamilyDataAttestation | None:
    """The caller's active attestation for this tree, on the current wording."""
    if ctx.user_id is None:
        return None
    return ctx.db.scalar(
        select(FamilyDataAttestation)
        .where(
            FamilyDataAttestation.tree_id == ctx.tree_id,
            FamilyDataAttestation.user_id == ctx.user_id,
            FamilyDataAttestation.withdrawn_at.is_(None),
            FamilyDataAttestation.statement_version == statements.current_version(StatementKind.FAMILY_DATA),
        )
        .order_by(FamilyDataAttestation.accepted_at.desc())
        .limit(1)
    )


def require_attestation(ctx: TreeContext) -> None:
    """Refuse to add people to a tree until the caller has confirmed the family-data statement."""
    if active_attestation(ctx) is None:
        raise Forbidden(
            "Please confirm you have your family members' permission before adding them to this tree",
            code="attestation_required",
        )


def attest(ctx: TreeContext, version: str, language: str) -> FamilyDataAttestation:
    stmt = statements.verify(StatementKind.FAMILY_DATA, version, language)
    existing = active_attestation(ctx)
    if existing is not None:
        return existing
    row = FamilyDataAttestation(
        tree_id=ctx.tree_id,
        user_id=ctx.user_id,
        statement_version=stmt.version,
        language=stmt.language,
        statement_sha256=stmt.sha256,
        ip=ctx.request.ip,
        user_agent=(ctx.request.user_agent or "")[:400] or None,
        created_by=ctx.user_id,
    )
    ctx.db.add(row)
    ctx.db.flush()
    audit.log(
        ctx,
        "attestation.accepted",
        target_type="attestation",
        target_id=row.id,
        details={"version": stmt.version, "language": stmt.language},
    )
    return row


@router.get("/consent-statements/{kind}", response_model=StatementOut)
def get_statement(
    kind: StatementKind, user: CurrentUser, lang: str = Query(default="en", max_length=10)
) -> StatementOut:
    s = statements.current(kind, lang)
    return StatementOut(kind=s.kind, version=s.version, language=s.language, text=s.text)


@router.get("/trees/{tree_id}/attestation", response_model=AttestationStatus)
def get_attestation(ctx: TreeCtx) -> AttestationStatus:
    row = active_attestation(ctx)
    return AttestationStatus(
        attested=row is not None,
        current_version=statements.current_version(StatementKind.FAMILY_DATA),
        attestation=AttestationOut.model_validate(row) if row else None,
    )


@router.post(
    "/trees/{tree_id}/attestation", response_model=AttestationOut, status_code=status.HTTP_201_CREATED
)
def create_attestation(body: AttestationIn, ctx: TreeCtx) -> AttestationOut:
    return AttestationOut.model_validate(attest(ctx, body.statement_version, body.language))


@router.post("/trees/{tree_id}/attestation/withdraw", response_model=AttestationOut)
def withdraw_attestation(ctx: TreeCtx) -> AttestationOut:
    row = active_attestation(ctx)
    if row is None:
        raise Conflict("You have no active confirmation for this tree", code="not_attested")
    row.withdrawn_at = dt.datetime.now(dt.UTC)
    audit.log(ctx, "attestation.withdrawn", target_type="attestation", target_id=row.id)
    return AttestationOut.model_validate(row)
