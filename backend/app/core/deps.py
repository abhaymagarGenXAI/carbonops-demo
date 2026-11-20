from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.database import Database

from app.core.security import TokenError, decode_token
from app.db.client import get_database
from app.repositories.user import UserRepository

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token from POST /auth/login")


def get_db() -> Database:
    return get_database()


Db = Annotated[Database, Depends(get_db)]


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Db,
) -> dict[str, Any]:
    """Loads the live user record for the token's subject, so suspending a user or changing
    their role takes effect on the very next request (not when their token expires)."""
    claims = getattr(request.state, "auth_claims", None)  # set by AccessTokenMiddleware
    if claims is None:
        if creds is None:
            raise _unauthorized()
        try:
            claims = decode_token(creds.credentials, "access")
        except TokenError as exc:
            raise _unauthorized("Invalid or expired access token") from exc

    user = UserRepository(db).get(claims["sub"])
    if user is None or user.get("status") != "Active":
        raise _unauthorized("Account not found or suspended")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def require_roles(*roles: str):
    """Administrator is always allowed (superuser); everyone else must hold one of `roles`."""
    allowed = set(roles) | {"Administrator"}

    def checker(user: CurrentUser) -> dict[str, Any]:
        if user["appRole"] not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user['appRole']}' is not permitted to perform this action",
            )
        return user

    return checker


# Role constants matching the UI's three roles
PLANT_ENGINEER = "Plant Engineer"
SUSTAINABILITY_MANAGER = "Sustainability Manager"
ADMINISTRATOR = "Administrator"
