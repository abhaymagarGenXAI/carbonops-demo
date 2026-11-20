from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class FacilityBase(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=20)
    region: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    manager: str = Field(min_length=1, max_length=100)
    units: list[str] = Field(default_factory=list)
    commissioned: str = Field(min_length=1, max_length=20)
    employees: int = Field(default=0, ge=0)


class FacilityCreate(FacilityBase):
    id: str | None = Field(default=None, min_length=1, max_length=64)


class FacilityUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    region: str | None = Field(default=None, min_length=1, max_length=100)
    type: str | None = Field(default=None, min_length=1, max_length=100)
    manager: str | None = Field(default=None, min_length=1, max_length=100)
    units: list[str] | None = None
    commissioned: str | None = Field(default=None, min_length=1, max_length=20)
    employees: int | None = Field(default=None, ge=0)


class FacilityOut(CamelModel):
    id: str
    name: str
    code: str
    region: str
    type: str
    manager: str
    units: list[str] = Field(default_factory=list)
    commissioned: str
    employees: int = 0
    created_at: str | None = None
    updated_at: str | None = None
