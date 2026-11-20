"""Password hashing + JWT helpers (no FastAPI imports -> trivially unit-testable)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised for any invalid / expired / wrong-type token."""


# --------------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:  # malformed hash
        return False


# ------------------------------------------------------------------------- JWT
def _encode(claims: dict[str, Any]) -> str:
    s = get_settings()
    return jwt.encode(claims, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def create_access_token(*, user_id: str, role: str, now: datetime | None = None) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    exp = now + timedelta(minutes=s.access_token_expire_minutes)
    token = _encode(
        {"sub": user_id, "role": role, "type": "access", "iat": now, "exp": exp, "jti": uuid.uuid4().hex}
    )
    return token, s.access_token_expire_minutes * 60


def create_refresh_token(*, user_id: str, now: datetime | None = None) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). The jti is persisted so tokens can be rotated/revoked."""
    s = get_settings()
    now = now or datetime.now(timezone.utc)
    exp = now + timedelta(days=s.refresh_token_expire_days)
    jti = uuid.uuid4().hex
    token = _encode({"sub": user_id, "type": "refresh", "iat": now, "exp": exp, "jti": jti})
    return token, jti, exp


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    s = get_settings()
    try:
        claims = jwt.decode(
            token,
            s.jwt_secret_key,
            algorithms=[s.jwt_algorithm],  # never trust the header's alg
            options={"require": ["exp", "sub", "type", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if claims.get("type") != expected_type:
        raise TokenError("wrong token type")
    return claims
