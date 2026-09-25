from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, optional_user, request_info
from app.api.schemas import Message
from app.core import audit
from app.core.errors import Unauthorized
from app.models import User, UserSession
from app.modules.identity import service
from app.modules.identity.schemas import (
    EmailIn,
    LoginIn,
    MfaCodeIn,
    MfaDisableIn,
    MfaSetupOut,
    PasswordChangeIn,
    PasswordConfirmIn,
    PasswordResetConfirmIn,
    ProfileUpdateIn,
    RegisterIn,
    SessionOut,
    TokenIn,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user).model_copy(
        update={
            "mfa_enabled": user.mfa_enabled_at is not None,
            "email_verified": user.email_verified_at is not None,
        }
    )


@router.post("/register", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def register(body: RegisterIn, request: Request, db: DbDep) -> Message:
    """Always answers 202 with the same body, whether or not the email has an account (SEC-12).

    A new email gets a verification link; an existing account's owner gets a notice instead.
    Nobody is signed in until the link is opened (``POST /auth/verify-email``).
    """
    service.register(
        db,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        language=body.preferred_language,
        info=request_info(request),
        next_path=body.next,
    )
    return Message(message=service.REGISTER_ACCEPTED)


@router.post("/verify-email", response_model=UserOut)
def verify_email(body: TokenIn, request: Request, response: Response, db: DbDep) -> UserOut:
    """Consume a verification link (single use), mark the email verified and sign the user in."""
    info = request_info(request)
    user = service.verify_email(db, body.token, info)
    service.start_session(db, user, response, info)
    return _user_out(user)


@router.post("/resend-verification", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def resend_verification(body: EmailIn, request: Request, db: DbDep) -> Message:
    service.resend_verification(db, body.email, request_info(request))
    return Message(message=service.EMAIL_SENT_IF_ACCOUNT)


@router.post("/password-reset/request", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def password_reset_request(body: EmailIn, request: Request, db: DbDep) -> Message:
    service.request_password_reset(db, body.email, request_info(request))
    return Message(message=service.EMAIL_SENT_IF_ACCOUNT)


@router.post("/password-reset/confirm", response_model=Message)
def password_reset_confirm(
    body: PasswordResetConfirmIn, request: Request, response: Response, db: DbDep
) -> Message:
    """Set a new password from a reset link; every session is revoked, so the user signs in again."""
    service.confirm_password_reset(db, body.token, body.new_password, request_info(request))
    service.clear_auth_cookies(response)
    return Message(message="Your password has been reset. Sign in with your new password.")


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: DbDep) -> UserOut:
    info = request_info(request)
    user = service.authenticate(
        db, email=body.email, password=body.password, info=info, mfa_code=body.mfa_code
    )
    service.start_session(db, user, response, info)
    return _user_out(user)


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, db: DbDep, user: CurrentUser) -> Message:
    sid = getattr(request.state, "session_id", None)
    if sid:
        service.revoke_session(db, sid)
    service.clear_auth_cookies(response)
    audit.record(db, action="user.logout", actor_user_id=user.id, target_type="user", target_id=user.id)
    return Message(message="Signed out")


@router.get("/me", response_model=UserOut)
def me(request: Request, db: DbDep) -> UserOut:
    user = optional_user(request, db)
    if user is None:
        raise Unauthorized()
    return _user_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdateIn, user: CurrentUser, db: DbDep) -> UserOut:
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.preferred_language is not None:
        user.preferred_language = body.preferred_language
    return _user_out(user)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(request: Request, user: CurrentUser, db: DbDep) -> list[SessionOut]:
    now = dt.datetime.now(dt.UTC)
    rows = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.absolute_expires_at > now,
        )
        .order_by(UserSession.created_at.desc())
    ).all()
    sid = getattr(request.state, "session_id", None)
    return [SessionOut.model_validate(s).model_copy(update={"current": s.id == sid}) for s in rows]


@router.post("/sessions/revoke-others", response_model=Message)
def revoke_others(request: Request, user: CurrentUser, db: DbDep) -> Message:
    n = service.revoke_all(db, user.id, except_session=getattr(request.state, "session_id", None))
    audit.record(
        db,
        action="user.sessions_revoked",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"count": n},
    )
    return Message(message=f"Revoked {n} other session(s)")


@router.post("/password", response_model=Message)
def change_password(body: PasswordChangeIn, request: Request, user: CurrentUser, db: DbDep) -> Message:
    service.change_password(
        db, user, body.current_password, body.new_password, getattr(request.state, "session_id", None)
    )
    return Message(message="Password changed; other sessions were signed out")


@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(user: CurrentUser, db: DbDep) -> MfaSetupOut:
    secret, uri = service.mfa_begin(db, user)
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable", response_model=UserOut)
def mfa_enable(body: MfaCodeIn, user: CurrentUser, db: DbDep) -> UserOut:
    service.mfa_enable(db, user, body.code)
    return _user_out(user)


@router.post("/mfa/disable", response_model=UserOut)
def mfa_disable(body: MfaDisableIn, user: CurrentUser, db: DbDep) -> UserOut:
    service.mfa_disable(db, user, body.password, body.code)
    return _user_out(user)


class CloseAccountIn(PasswordConfirmIn):
    pass


@router.post("/close-account", response_model=Message)
def close_account(
    body: CloseAccountIn, request: Request, response: Response, user: CurrentUser, db: DbDep
) -> Message:
    """Close the account (PRS §54): deactivate, sign out everywhere, leave all trees.

    Refused while the user is the only owner of a tree (transfer ownership or delete the tree first).
    Family data the user added stays with the tree (it belongs to the family archive).
    """
    service.close_account(db, user, body.password)
    service.clear_auth_cookies(response)
    return Message(message="Account closed")
