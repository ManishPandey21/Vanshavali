from __future__ import annotations

import datetime as dt

from app.api.schemas import ApiModel


class ConsoleSessionOut(ApiModel):
    """What the console needs to know about the caller's session (ADR-0028 §7)."""

    capabilities: list[str]
    # the session stops counting as two-step verified at this time; sign in again after it
    mfa_valid_until: dt.datetime
    # writes need a step-up (POST /auth/step-up) before this time; null = none yet or expired
    step_up_valid_until: dt.datetime | None
