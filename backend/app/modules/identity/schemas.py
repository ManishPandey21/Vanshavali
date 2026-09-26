from __future__ import annotations

import datetime as dt
import uuid

from pydantic import EmailStr, Field, field_validator

from app.api.schemas import ApiModel


class RegisterIn(ApiModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    preferred_language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    # Where to continue after the emailed verification link (a same-site path only, e.g. an invitation).
    next: str | None = Field(default=None, max_length=500)

    @field_validator("next")
    @classmethod
    def _same_site_path(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not v.startswith("/") or v.startswith("//") or any(c == "\\" or ord(c) < 0x21 for c in v):
            raise ValueError("must be a same-site path")
        return v


class TokenIn(ApiModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(ApiModel):
    email: EmailStr


class PasswordResetConfirmIn(ApiModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=256)


class LoginIn(ApiModel):
    email: EmailStr
    password: str = Field(max_length=256)
    mfa_code: str | None = Field(default=None, max_length=10)


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    display_name: str
    preferred_language: str
    created_at: dt.datetime
    mfa_enabled: bool = False
    email_verified: bool = False
    # A temporary password must be replaced before anything else works (POST /auth/password).
    must_change_password: bool = False


class ProvidersOut(ApiModel):
    google: bool = False


class MfaSetupOut(ApiModel):
    secret: str
    otpauth_uri: str


class MfaCodeIn(ApiModel):
    code: str = Field(min_length=6, max_length=10)


class MfaDisableIn(ApiModel):
    password: str = Field(max_length=256)
    code: str = Field(min_length=6, max_length=10)


class SessionOut(ApiModel):
    id: uuid.UUID
    created_at: dt.datetime
    last_seen_at: dt.datetime
    ip: str | None
    user_agent: str | None
    current: bool = False


class PasswordChangeIn(ApiModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class ProfileUpdateIn(ApiModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    preferred_language: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")


class PasswordConfirmIn(ApiModel):
    password: str = Field(max_length=256)
