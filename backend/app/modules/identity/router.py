from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, optional_user, request_info
from app.api.schemas import Message
from app.core import audit
from app.core.errors import Unauthorized
from app.models import UserSession
from app.modules.identity import service
from app.modules.identity.schemas import (
    LoginIn,
    PasswordChangeIn,
    ProfileUpdateIn,
    RegisterIn,
    SessionOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, response: Response, db: DbDep) -> UserOut:
    info = request_info(request)
    user = service.register(
        db,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        language=body.preferred_language,
        info=info,
    )
    service.start_session(db, user, response, info)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: DbDep) -> UserOut:
    info = request_info(request)
    user = service.authenticate(db, email=body.email, password=body.password, info=info)
    service.start_session(db, user, response, info)
    return UserOut.model_validate(user)


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
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdateIn, user: CurrentUser, db: DbDep) -> UserOut:
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.preferred_language is not None:
        user.preferred_language = body.preferred_language
    return UserOut.model_validate(user)


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
