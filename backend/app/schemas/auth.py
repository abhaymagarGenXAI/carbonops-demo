from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.user import EMAIL_PATTERN, UserOut


class LoginRequest(CamelModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(CamelModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=12, max_length=72)
