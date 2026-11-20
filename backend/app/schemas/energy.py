from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import MONTH_PATTERN, CamelModel

Stream = Literal["Electricity", "Diesel", "Natural Gas", "Steam", "Renewable Energy"]
EnergyValidation = Literal["Validated", "Pending", "Anomaly", "Missing"]


class EnergyRecordBase(CamelModel):
    facility_id: str = Field(min_length=1)
    month: str = Field(pattern=MONTH_PATTERN)
    stream: Stream
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1)
    meter_ref: str = ""
    invoice_ref: str = ""
    cost: float = Field(default=0, ge=0)
    validation: EnergyValidation = "Pending"
    variance: float = 0


class EnergyRecordCreate(EnergyRecordBase):
    id: str | None = Field(default=None, min_length=1, max_length=64)


class EnergyRecordUpdate(CamelModel):
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1)
    meter_ref: str | None = None
    invoice_ref: str | None = None
    cost: float | None = Field(default=None, ge=0)
    validation: EnergyValidation | None = None
    variance: float | None = None


class EnergyRecordOut(CamelModel):
    id: str
    facility_id: str
    month: str
    stream: str
    quantity: float
    unit: str
    meter_ref: str = ""
    invoice_ref: str = ""
    cost: float = 0
    validation: str
    variance: float = 0
    energy_gj: float | None = None
    submission_id: str | None = None
    submission_status: str | None = None  # Approved => counted in analytics by default
    excluded: bool = False


class EnergyReconcileRequest(CamelModel):
    """dry_run defaults to True so nothing is written unless explicitly requested."""

    month: str | None = Field(default=None, pattern=MONTH_PATTERN)
    facility_id: str | None = Field(default=None, min_length=1)
    dry_run: bool = True


class EnergyReconcileItem(CamelModel):
    id: str
    facility_id: str
    month: str
    stream: str
    action: str
    old_quantity: float | None = None
    new_quantity: float
    old_validation: str | None = None
    new_validation: str
    old_variance: float | None = None
    new_variance: float
    excluded: bool = False


class EnergyReconcileResult(CamelModel):
    dry_run: bool
    evaluated: int
    created: int
    updated: int
    unchanged: int
    skipped: list[dict[str, str]] = Field(default_factory=list)
    items: list[EnergyReconcileItem] = Field(default_factory=list)
