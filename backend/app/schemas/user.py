from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserOut(CamelModel):
    id: str
    name: str
    email: str
    role: str  # display role, e.g. "Facility Engineer"
    app_role: str  # name of the user's role (mirrors the Role master's roleName; custom roles are allowed)
    role_id: str | None = None  # Role master link
    role_code: str | None = None
    facility: str  # legacy display text, derived from facility_ids
    facility_ids: list[str] = []  # assigned facilities (informational: every facility is visible to every role)
    permissions: list[str] = []  # permission codes granted by the user's role (drives what the UI offers)
    status: str
    last_login: str = "—"


class UserCreate(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    role: str = Field(min_length=1)  # job title
    app_role: str | None = None  # role by name (legacy) ...
    role_id: str | None = None  # ... or by id (preferred; required for custom roles with duplicate-looking names)
    facility: str = "All Facilities"
    facility_ids: list[str] = []
    password: str = Field(min_length=12, max_length=72)

    @model_validator(mode="after")
    def _needs_role(self):
        if not self.role_id and not self.app_role:
            raise ValueError("a role is required (roleId)")
        return self


class UserUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = None
    app_role: str | None = None
    role_id: str | None = None
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)
    facility: str | None = None
    status: Literal["Active", "Suspended"] | None = None


class PasswordResetIn(CamelModel):
    new_password: str = Field(min_length=12, max_length=72)


class UserAccessIn(CamelModel):
    """Role + facility assignment from the Administrator screen."""
    role_id: str = Field(min_length=1)
    facility_ids: list[str] = []


class RoleOut(CamelModel):
    id: str
    code: str
    name: str
    description: str = ""
    is_system: bool
    is_locked: bool = False  # the Administrator role: always holds every permission, cannot be edited or deleted
    all_facilities: bool
    is_active: bool
    members: int
    permissions: list[str]


class PermissionOut(CamelModel):
    code: str
    module: str
    description: str = ""


class RoleCreate(CamelModel):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default="", max_length=240)
    permissions: list[str] = []


class RoleUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=240)


class RolePermissionsIn(CamelModel):
    permissions: list[str]
