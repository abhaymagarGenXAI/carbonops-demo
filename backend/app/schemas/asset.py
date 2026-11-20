from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel

AssetStatus = Literal["Operational", "Under Maintenance", "Shutdown", "Standby"]


class AssetBase(CamelModel):
    facility_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1)
    type: str = Field(min_length=1)
    status: AssetStatus
    energy_source: str = Field(min_length=1)
    operating_hours: float = Field(default=0, ge=0)
    engineer: str = Field(min_length=1)
    last_inspection: str = Field(min_length=1)
    carbon_category: str = Field(min_length=1)
    emission_source_type: str = Field(min_length=1)
    capacity: str = Field(min_length=1)


class AssetCreate(AssetBase):
    id: str | None = Field(default=None, min_length=1, max_length=64)


class AssetUpdate(CamelModel):
    facility_id: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1)
    type: str | None = Field(default=None, min_length=1)
    status: AssetStatus | None = None
    energy_source: str | None = Field(default=None, min_length=1)
    operating_hours: float | None = Field(default=None, ge=0)
    engineer: str | None = Field(default=None, min_length=1)
    last_inspection: str | None = Field(default=None, min_length=1)
    carbon_category: str | None = Field(default=None, min_length=1)
    emission_source_type: str | None = Field(default=None, min_length=1)
    capacity: str | None = Field(default=None, min_length=1)


class AssetOut(CamelModel):
    # Output is deliberately tolerant (status: str) so legacy documents never cause a 500.
    id: str
    facility_id: str
    name: str
    unit: str
    type: str
    status: str
    energy_source: str
    operating_hours: float = 0
    engineer: str
    last_inspection: str
    carbon_category: str
    emission_source_type: str
    capacity: str
    created_at: str | None = None
    updated_at: str | None = None
