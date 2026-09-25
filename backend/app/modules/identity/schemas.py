from __future__ import annotations

import datetime as dt
import uuid

from pydantic import EmailStr, Field

from app.api.schemas import ApiModel


class RegisterIn(ApiModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=200)
    preferred_language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")


class LoginIn(ApiModel):
    email: EmailStr
    password: str = Field(max_length=256)


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    display_name: str
    preferred_language: str
    created_at: dt.datetime


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
