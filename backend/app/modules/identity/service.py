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
from app.core.errors import ApiError, Conflict, Forbidden, Unauthorized, Unprocessable
from app.core.ratelimit import enforce
from app.core.security import (
    DUMMY_HASH,
    hash_password,
    new_token,
    password_problems,
    token_hash,
    verify_password,
)
from app.models import AuthToken, AuthTokenPurpose, User, UserSession
from app.modules.identity import emails


def normalise_email(email: str) -> str:
    return email.strip().lower()


REGISTER_ACCEPTED = "If this email can be registered, we've sent a link to it. Check your inbox to continue."
EMAIL_SENT_IF_ACCOUNT = "If an account uses this email, we've sent a link to it. Check your inbox."
TOKEN_INVALID = "This link is invalid or has expired. Request a new one."  # noqa: S105 - user-facing message, not a secret


def register(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    language: str,
    info: RequestInfo,
    next_path: str | None = None,
) -> None:
    """Start registration without revealing whether the email already has an account (SEC-12).

    The response is identical either way and the password is always hashed so timing matches:
    a new email gets an unverified account plus a verification link; an existing account's owner
    gets a "someone tried to register with your email" notice instead.
    """
    email = normalise_email(email)
    enforce(f"register:{info.ip}", get_settings().register_rate_limit_per_minute)
    problems = password_problems(password)
    if problems:
        raise Unprocessable("; ".join(problems), code="weak_password")
    password_hash = hash_password(password)
    enforce(f"register-email:{email}", 5, 3600)
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        emails.send_existing_account_notice(
            existing.email, existing.display_name, existing.preferred_language
        )
        audit.record(
            db,
            action="user.register_existing_email",
            actor_user_id=None,
            target_type="user",
            target_id=existing.id,
            ip=info.ip,
            user_agent=info.user_agent,
        )
        return
    user = User(
        email=email,
        password_hash=password_hash,
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
    token = issue_token(db, user.id, AuthTokenPurpose.VERIFY_EMAIL)
    emails.send_verification(user.email, user.display_name, user.preferred_language, token, next_path)


# ------------------------------------------------------------------ emailed single-use tokens


def _token_ttl(purpose: AuthTokenPurpose) -> dt.timedelta:
    s = get_settings()
    if purpose is AuthTokenPurpose.PASSWORD_RESET:
        return dt.timedelta(minutes=s.password_reset_ttl_minutes)
    return dt.timedelta(hours=s.email_verify_ttl_hours)


def invalidate_tokens(db: Session, user_id: uuid.UUID, purpose: AuthTokenPurpose | None = None) -> None:
    """Mark the user's outstanding tokens (of one purpose, or all) as used."""
    stmt = update(AuthToken).where(AuthToken.user_id == user_id, AuthToken.used_at.is_(None))
    if purpose is not None:
        stmt = stmt.where(AuthToken.purpose == purpose)
    db.execute(stmt.values(used_at=dt.datetime.now(dt.UTC)))


def issue_token(db: Session, user_id: uuid.UUID, purpose: AuthTokenPurpose) -> str:
    """Create a single-use token (only its SHA-256 is stored); earlier ones of the same purpose die."""
    invalidate_tokens(db, user_id, purpose)
    token = new_token()
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_hash(token),
            expires_at=dt.datetime.now(dt.UTC) + _token_ttl(purpose),
        )
    )
    db.flush()
    return token


def _consume_token(db: Session, token: str, purpose: AuthTokenPurpose) -> tuple[AuthToken, User]:
    """Look up a live token and its active user (locked), or raise one generic error."""
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token)).with_for_update())
    now = dt.datetime.now(dt.UTC)
    if row is None or row.purpose != purpose or row.used_at is not None or row.expires_at <= now:
        raise ApiError(TOKEN_INVALID, code="token_invalid", status_code=400)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ApiError(TOKEN_INVALID, code="token_invalid", status_code=400)
    # a password change after the link was issued kills it (belt and braces with invalidate_tokens)
    if purpose is AuthTokenPurpose.PASSWORD_RESET and row.created_at < user.password_changed_at:
        raise ApiError(TOKEN_INVALID, code="token_invalid", status_code=400)
    return row, user


def verify_email(db: Session, token: str, info: RequestInfo) -> User:
    enforce(f"token-ip:{info.ip}", get_settings().token_rate_limit_per_minute)
    row, user = _consume_token(db, token, AuthTokenPurpose.VERIFY_EMAIL)
    now = dt.datetime.now(dt.UTC)
    row.used_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
    invalidate_tokens(db, user.id, AuthTokenPurpose.VERIFY_EMAIL)
    audit.record(
        db,
        action="user.email_verified",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        ip=info.ip,
        user_agent=info.user_agent,
    )
    return user


def resend_verification(db: Session, email: str, info: RequestInfo) -> None:
    """Always answers the same; only an active, unverified account gets a fresh link."""
    email = normalise_email(email)
    enforce(f"resend-ip:{info.ip}", 10)
    enforce(f"resend-email:{email}", 3, 3600)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or user.email_verified_at is not None:
        return
    token = issue_token(db, user.id, AuthTokenPurpose.VERIFY_EMAIL)
    emails.send_verification(user.email, user.display_name, user.preferred_language, token)


def request_password_reset(db: Session, email: str, info: RequestInfo) -> None:
    """Always answers the same; only an active account gets a reset link."""
    email = normalise_email(email)
    enforce(f"reset-ip:{info.ip}", 10)
    enforce(f"reset-email:{email}", 5, 3600)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return
    token = issue_token(db, user.id, AuthTokenPurpose.PASSWORD_RESET)
    emails.send_password_reset(user.email, user.display_name, user.preferred_language, token)
    audit.record(
        db,
        action="user.password_reset_requested",
        actor_user_id=None,
        target_type="user",
        target_id=user.id,
        ip=info.ip,
        user_agent=info.user_agent,
    )


def confirm_password_reset(db: Session, token: str, new_password: str, info: RequestInfo) -> User:
    enforce(f"token-ip:{info.ip}", get_settings().token_rate_limit_per_minute)
    row, user = _consume_token(db, token, AuthTokenPurpose.PASSWORD_RESET)
    problems = password_problems(new_password)
    if problems:
        raise Unprocessable("; ".join(problems), code="weak_password")
    now = dt.datetime.now(dt.UTC)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = now
    user.must_change_password = False  # the reset replaced the temporary password
    if user.email_verified_at is None:
        user.email_verified_at = now  # the reset link proves control of the mailbox
    row.used_at = now
    invalidate_tokens(db, user.id, AuthTokenPurpose.PASSWORD_RESET)
    revoked = revoke_all(db, user.id)
    audit.record(
        db,
        action="user.password_reset",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"sessions_revoked": revoked},
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
    if user.email_verified_at is None:
        # Only after the correct password, so this reveals nothing to someone guessing emails.
        raise Forbidden(
            "Please confirm your email address first. We can send you a new link.",
            code="email_not_verified",
        )
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
    if user.mfa_secret_enc is None:
        raise ApiError("Two-factor authentication is not set up", code="mfa_not_started", status_code=400)
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


def start_session(
    db: Session, user: User, response: Response, info: RequestInfo, *, method: str | None = None
) -> UserSession:
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
        details={"method": method} if method else None,
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
    if user.must_change_password and new == current:
        raise Unprocessable("Choose a password different from the temporary one", code="password_reused")
    was_forced = user.must_change_password
    user.password_hash = hash_password(new)
    user.password_changed_at = dt.datetime.now(dt.UTC)
    user.must_change_password = False
    revoke_all(db, user.id, except_session=current_session)
    invalidate_tokens(db, user.id, AuthTokenPurpose.PASSWORD_RESET)
    audit.record(
        db,
        action="user.password_changed",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"forced": True} if was_forced else None,
    )


def close_account(db: Session, user: User, password: str) -> None:
    from sqlalchemy import func

    from app.core.db import bind_tree, unbind_tree
    from app.models import TreeMembership
    from app.models.enums import Role
    from app.modules.trees.nominations import on_member_leaving
    from app.modules.trees.service import audit_cascaded_grants

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
        bind_tree(db, m.tree_id)  # access_grant is row-level secured: scope the count to this tree
        on_member_leaving(db, m.tree_id, m, user.id)
        audit_cascaded_grants(db, tree_id=m.tree_id, membership_id=m.id, actor_user_id=user.id)
        db.delete(m)  # the membership's grants go with it (ON DELETE CASCADE, ADR-0027 §3)
    if memberships:
        unbind_tree(db)
    revoke_all(db, user.id)
    invalidate_tokens(db, user.id)
    user.is_active = False
    user.mfa_secret_enc = None
    user.mfa_enabled_at = None
    user.email = f"closed+{user.id}@closed.invalid"
    user.display_name = "Closed account"
    audit.record(
        db, action="user.account_closed", actor_user_id=user.id, target_type="user", target_id=user.id
    )
