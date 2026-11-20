from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import AppRole, CamelModel

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserOut(CamelModel):
    id: str
    name: str
    email: str
    role: str  # display role, e.g. "Facility Engineer"
    app_role: AppRole  # authorization role used by the UI + API
    facility: str
    status: str
    last_login: str = "—"


class UserCreate(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    role: str = Field(min_length=1)
    app_role: AppRole
    facility: str = "All Facilities"
    password: str = Field(min_length=12, max_length=72)


class UserUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = None
    app_role: AppRole | None = None
    facility: str | None = None
    status: Literal["Active", "Suspended"] | None = None
