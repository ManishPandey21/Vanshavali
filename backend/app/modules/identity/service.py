from __future__ import annotations

import base64
import datetime as dt
import uuid

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.authz.context import RequestInfo
from app.core import audit, storage, totp
from app.core.config import get_settings
from app.core.errors import ApiError, Conflict, Unauthorized, Unprocessable
from app.core.ratelimit import enforce
from app.core.security import (
    DUMMY_HASH,
    hash_password,
    new_token,
    password_problems,
    token_hash,
    verify_password,
)
from app.models import User, UserSession


def normalise_email(email: str) -> str:
    return email.strip().lower()


def register(
    db: Session, *, email: str, password: str, display_name: str, language: str, info: RequestInfo
) -> User:
    enforce(f"register:{info.ip}", 20)
    problems = password_problems(password)
    if problems:
        raise Unprocessable("; ".join(problems), code="weak_password")
    email = normalise_email(email)
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("An account with this email already exists", code="email_taken")
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        preferred_language=language,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.registered",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=info.ip,
        user_agent=info.user_agent,
    )
    return user


def authenticate(
    db: Session, *, email: str, password: str, info: RequestInfo, mfa_code: str | None = None
) -> User:
    email = normalise_email(email)
    limit = get_settings().login_rate_limit_per_minute
    enforce(f"login-ip:{info.ip}", limit * 3)
    enforce(f"login-email:{email}", limit)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(DUMMY_HASH, password)  # equalise timing
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    if not verify_password(user.password_hash, password) or not user.is_active:
        audit.record_detached(
            action="user.login_failed",
            actor_user_id=user.id,
            target_type="user",
            target_id=user.id,
            ip=info.ip,
            user_agent=info.user_agent,
        )
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    if user.mfa_enabled_at is not None:
        if not mfa_code:
            raise Unauthorized("Enter the 6-digit code from your authenticator app", code="mfa_required")
        enforce(f"mfa:{user.id}", 10)
        if not totp.verify(mfa_secret(user), mfa_code):
            audit.record_detached(
                action="user.mfa_failed",
                actor_user_id=user.id,
                target_type="user",
                target_id=user.id,
                ip=info.ip,
                user_agent=info.user_agent,
            )
            raise Unauthorized("Invalid authentication code", code="mfa_invalid")
    return user


def mfa_secret(user: User) -> str:
    assert user.mfa_secret_enc is not None
    return storage.decrypt(base64.b64decode(user.mfa_secret_enc), aad=f"mfa:{user.id}").decode()


def mfa_begin(db: Session, user: User) -> tuple[str, str]:
    if user.mfa_enabled_at is not None:
        raise Conflict("Two-factor authentication is already enabled", code="mfa_already_enabled")
    secret = totp.new_secret()
    user.mfa_secret_enc = base64.b64encode(
        storage.encrypt(secret.encode(), "SYSTEM", aad=f"mfa:{user.id}")
    ).decode()
    return secret, totp.otpauth_uri(secret, user.email)


def mfa_enable(db: Session, user: User, code: str) -> None:
    if user.mfa_secret_enc is None:
        raise ApiError("Start MFA setup first", code="mfa_not_started", status_code=400)
    if not totp.verify(mfa_secret(user), code):
        raise ApiError("Invalid authentication code", code="mfa_invalid", status_code=400)
    user.mfa_enabled_at = dt.datetime.now(dt.UTC)
    audit.record(db, action="user.mfa_enabled", actor_user_id=user.id, target_type="user", target_id=user.id)


def mfa_disable(db: Session, user: User, password: str, code: str) -> None:
    if user.mfa_enabled_at is None:
        raise ApiError("Two-factor authentication is not enabled", code="mfa_not_enabled", status_code=400)
    if not verify_password(user.password_hash, password) or not totp.verify(mfa_secret(user), code):
        raise ApiError("Password or code is incorrect", code="invalid_credentials", status_code=400)
    user.mfa_enabled_at = None
    user.mfa_secret_enc = None
    audit.record(db, action="user.mfa_disabled", actor_user_id=user.id, target_type="user", target_id=user.id)


def start_session(db: Session, user: User, response: Response, info: RequestInfo) -> UserSession:
    s = get_settings()
    now = dt.datetime.now(dt.UTC)
    token = new_token()
    sess = UserSession(
        user_id=user.id,
        token_hash=token_hash(token),
        idle_expires_at=now + dt.timedelta(days=s.session_idle_days),
        absolute_expires_at=now + dt.timedelta(days=s.session_absolute_days),
        ip=info.ip,
        user_agent=(info.user_agent or "")[:400] or None,
    )
    db.add(sess)
    db.flush()
    set_auth_cookies(response, token)
    audit.record(
        db,
        action="user.login",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=info.ip,
        user_agent=info.user_agent,
    )
    return sess


def set_auth_cookies(response: Response, token: str) -> None:
    s = get_settings()
    max_age = s.session_absolute_days * 86400
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        s.csrf_cookie_name,
        new_token(),
        max_age=max_age,
        httponly=False,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/")
    response.delete_cookie(s.csrf_cookie_name, path="/")


def revoke_session(db: Session, session_id: uuid.UUID) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=dt.datetime.now(dt.UTC))
    )


def revoke_all(db: Session, user_id: uuid.UUID, *, except_session: uuid.UUID | None = None) -> int:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_session is not None:
        stmt = stmt.where(UserSession.id != except_session)
    result = db.execute(stmt.values(revoked_at=dt.datetime.now(dt.UTC)))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def change_password(
    db: Session, user: User, current: str, new: str, current_session: uuid.UUID | None
) -> None:
    if not verify_password(user.password_hash, current):
        raise ApiError("Current password is incorrect", code="invalid_credentials", status_code=400)
    problems = password_problems(new)
    if problems:
        raise Unprocessable("; ".join(problems), code="weak_password")
    user.password_hash = hash_password(new)
    user.password_changed_at = dt.datetime.now(dt.UTC)
    revoke_all(db, user.id, except_session=current_session)
    audit.record(
        db, action="user.password_changed", actor_user_id=user.id, target_type="user", target_id=user.id
    )


def close_account(db: Session, user: User, password: str) -> None:
    from sqlalchemy import func

    from app.models import TreeMembership
    from app.models.enums import Role

    if not verify_password(user.password_hash, password):
        raise ApiError("Password is incorrect", code="invalid_credentials", status_code=400)
    memberships = db.scalars(select(TreeMembership).where(TreeMembership.user_id == user.id)).all()
    for m in memberships:
        if Role.OWNER.value in m.roles:
            owners = db.scalar(
                select(func.count())
                .select_from(TreeMembership)
                .where(TreeMembership.tree_id == m.tree_id, TreeMembership.roles.contains([Role.OWNER.value]))
            )
            if (owners or 0) <= 1:
                raise Conflict(
                    "You are the only owner of a family tree. Transfer ownership or delete the tree first.",
                    code="sole_owner",
                    details={"tree_id": str(m.tree_id)},
                )
    for m in memberships:
        audit.record(
            db,
            action="member.left",
            actor_user_id=user.id,
            tree_id=m.tree_id,
            target_type="membership",
            target_id=m.id,
        )
        db.delete(m)
    revoke_all(db, user.id)
    user.is_active = False
    user.mfa_secret_enc = None
    user.mfa_enabled_at = None
    user.email = f"closed+{user.id}@closed.invalid"
    user.display_name = "Closed account"
    audit.record(
        db, action="user.account_closed", actor_user_id=user.id, target_type="user", target_id=user.id
    )
