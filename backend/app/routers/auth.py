from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.core.config import get_settings
from app.core.deps import CurrentUser, Db
from app.repositories.user import UserRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.schemas.user import UserOut
from app.services import auth as auth_service
from app.services.common import audit
from app.utils.time import as_aware

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_path() -> str:
    return f"{get_settings().api_prefix}/auth"  # the browser only sends it to /auth/* endpoints


def _set_refresh_cookie(response: Response, token: str, expires_at) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.refresh_cookie_name,
        value=token,
        httponly=True,  # not readable from JS => not stealable via XSS
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        expires=as_aware(expires_at),
        path=_cookie_path(),
    )


def _clear_refresh_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        s.refresh_cookie_name, path=_cookie_path(), secure=s.cookie_secure, httponly=True, samesite=s.cookie_samesite
    )


def _token_response(db, session: dict[str, Any], user_raw: dict[str, Any]) -> TokenResponse:
    user_public = UserRepository(db).to_public(user_raw)
    return TokenResponse(
        access_token=session["access"], expires_in=session["expires_in"], user=UserOut.model_validate(user_public)
    )


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for an access token")
def login(body: LoginRequest, response: Response, db: Db):
    user = auth_service.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if user.get("status") != "Active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is suspended")
    session = auth_service.issue_session(db, user)
    _set_refresh_cookie(response, session["refresh"], session["refresh_exp"])
    return _token_response(db, session, user)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the refresh cookie, get a new access token")
def refresh(
    response: Response,
    db: Db,
    refresh_cookie: Annotated[str | None, Cookie(alias=get_settings().refresh_cookie_name)] = None,
):
    if not refresh_cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        session, user = auth_service.rotate_refresh_token(db, refresh_cookie)
    except auth_service.AuthError:
        _clear_refresh_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again")
    if session["refresh"]:
        _set_refresh_cookie(response, session["refresh"], session["refresh_exp"])
    return _token_response(db, session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the refresh token and clear the cookie")
def logout(
    response: Response,
    db: Db,
    refresh_cookie: Annotated[str | None, Cookie(alias=get_settings().refresh_cookie_name)] = None,
):
    auth_service.logout(db, refresh_cookie)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserOut, summary="The currently authenticated user")
def me(user: CurrentUser):
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, response: Response, user: CurrentUser, db: Db):
    raw = UserRepository(db).get_raw(user["id"])
    try:
        auth_service.change_password(db, raw or {}, body.current_password, body.new_password)
    except auth_service.AuthError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    _clear_refresh_cookie(response)  # all sessions were revoked; force a fresh login
    audit(db, user, "Updated", user["id"], "Password changed; all sessions revoked.")
