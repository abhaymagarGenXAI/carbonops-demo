"""Authentication use-cases. HTTP concerns (cookies, status codes) live in routers/auth.py."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pymongo.database import Database

from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.utils.time import as_aware, utcnow

# Two browser tabs can refresh with the same cookie at the same moment. Within this window a
# just-rotated token is answered with a new *access* token only (no new refresh token) instead
# of being treated as theft.
REUSE_GRACE_SECONDS = 10


class AuthError(Exception):
    pass


@lru_cache
def _dummy_hash() -> str:
    # Used to burn the same bcrypt time for unknown e-mails (prevents user enumeration by timing).
    return hash_password("not-a-real-password")


def authenticate(db: Database, email: str, password: str) -> dict[str, Any] | None:
    """Returns the raw user document on success, None on bad credentials."""
    user = UserRepository(db).get_raw_by_email(email)
    if user is None:
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.get("passwordHash", "")):
        return None
    return user


def issue_session(db: Database, user: dict[str, Any]) -> dict[str, Any]:
    access, expires_in = create_access_token(user_id=user["userId"], role=user["appRole"])
    refresh, jti, exp = create_refresh_token(user_id=user["userId"])
    RefreshTokenRepository(db).issue(jti=jti, user_id=user["userId"], expires_at=exp)
    UserRepository(db).col.update_one({"userId": user["userId"]}, {"$set": {"lastLogin": utcnow()}})
    return {"access": access, "expires_in": expires_in, "refresh": refresh, "refresh_exp": exp}


def rotate_refresh_token(db: Database, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate + rotate a refresh token. Returns (session, raw_user).
    session['refresh'] is None when only a new access token was issued (grace window)."""
    try:
        claims = decode_token(token, "refresh")
    except TokenError as exc:
        raise AuthError("invalid refresh token") from exc

    tokens = RefreshTokenRepository(db)
    record = tokens.find(claims["jti"])
    if record is None:
        raise AuthError("unknown refresh token")

    user = UserRepository(db).get_raw(claims["sub"])
    if user is None or user.get("status") != "Active":
        tokens.revoke_all_for_user(claims["sub"])
        raise AuthError("user inactive")

    new_refresh, new_jti, new_exp = create_refresh_token(user_id=user["userId"])
    if tokens.claim(claims["jti"], replaced_by=new_jti):
        tokens.issue(jti=new_jti, user_id=user["userId"], expires_at=new_exp)
        access, expires_in = create_access_token(user_id=user["userId"], role=user["appRole"])
        return {"access": access, "expires_in": expires_in, "refresh": new_refresh, "refresh_exp": new_exp}, user

    # Token was already used. Benign race (grace window) or replay of a stolen token?
    revoked_at = record.get("revokedAt")
    if revoked_at and record.get("replacedBy") and (utcnow() - as_aware(revoked_at)).total_seconds() <= REUSE_GRACE_SECONDS:
        access, expires_in = create_access_token(user_id=user["userId"], role=user["appRole"])
        return {"access": access, "expires_in": expires_in, "refresh": None, "refresh_exp": None}, user

    tokens.revoke_all_for_user(user["userId"])  # reuse detected: kill every session of this user
    raise AuthError("refresh token reuse detected")


def logout(db: Database, token: str | None) -> None:
    if not token:
        return
    try:
        claims = decode_token(token, "refresh")
    except TokenError:
        return
    RefreshTokenRepository(db).revoke(claims["jti"])


def change_password(db: Database, user_raw: dict[str, Any], current: str, new: str) -> None:
    if not verify_password(current, user_raw.get("passwordHash", "")):
        raise AuthError("current password is incorrect")
    UserRepository(db).col.update_one(
        {"userId": user_raw["userId"]}, {"$set": {"passwordHash": hash_password(new), "updatedAt": utcnow()}}
    )
    RefreshTokenRepository(db).revoke_all_for_user(user_raw["userId"])
