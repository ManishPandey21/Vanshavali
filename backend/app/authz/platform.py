"""Platform capabilities (ADR-0025): what a system admin may do outside any family tree.

Kept apart from the tree permission matrix on purpose. ``is_system_admin`` is consulted only here,
and nothing here reads or grants tree data: a system admin still has no implicit tree access
(ADR-0006 §6, threat T12). Deny by default: a capability not listed is refused.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.errors import ApiError, NotFound
from app.models import User


class PlatformCapability(StrEnum):
    # curate the *global* master-data catalogues (ADR-0018 vocabularies); never tree entries
    MASTER_DATA_ADMIN = "platform.master_data.admin"


_SYSTEM_ADMIN_CAPABILITIES: frozenset[PlatformCapability] = frozenset({PlatformCapability.MASTER_DATA_ADMIN})


def capabilities(user: User) -> frozenset[PlatformCapability]:
    """The platform capabilities a user holds right now (empty for everyone but system admins)."""
    if not user.is_system_admin or not user.is_active:
        return frozenset()
    return _SYSTEM_ADMIN_CAPABILITIES


def require_platform(user: User, capability: PlatformCapability) -> None:
    """Refuse unless ``user`` holds ``capability`` *and* has two-factor sign-in turned on.

    Ordinary accounts get 404, so the admin surface is not advertised to them. A system admin
    without MFA gets 403 ``admin_mfa_required``: a global catalogue is shown to every family, so a
    stolen password alone must not be enough to change it (ADR-0025 §2).
    """
    if capability not in capabilities(user):
        raise NotFound("Not found")
    if user.mfa_enabled_at is None:
        raise ApiError(
            "Turn on two-step sign-in (authenticator app) in your account before managing master data.",
            code="admin_mfa_required",
            status_code=403,
        )
