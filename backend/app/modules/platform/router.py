"""Super Admin master-data console API (ADR-0028). Increment 1: the authorisation gate only.

Every handler depends on ``MasterDataAdmin`` (or ``MasterDataAdminWrite``): anyone without the
capability gets 404, a holder without a fresh two-step session 403 ``admin_mfa_required``, and a write
without a recent step-up 403 ``admin_step_up_required``. Handlers never bind a tree.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter

from app.api.deps import MasterDataAdmin
from app.authz import platform
from app.modules.platform.schemas import ConsoleSessionOut

router = APIRouter(prefix="/admin/master-data", tags=["master-data-admin"])


@router.get("/session", response_model=ConsoleSessionOut)
def console_session(ctx: MasterDataAdmin) -> ConsoleSessionOut:
    """The caller's capabilities and when their two-step session and step-up run out."""
    mfa_until = platform.session_mfa_valid_until(ctx.user, ctx.session)
    step_up = platform.step_up_valid_until(ctx.session)
    now = dt.datetime.now(dt.UTC)
    return ConsoleSessionOut(
        capabilities=sorted(c.value for c in platform.capabilities(ctx.db, ctx.user)),
        mfa_valid_until=mfa_until or now,
        step_up_valid_until=step_up if step_up is not None and step_up > now else None,
    )
