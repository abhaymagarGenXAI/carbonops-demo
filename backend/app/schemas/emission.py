from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class EmissionComment(CamelModel):
    by: str
    at: str
    text: str


class EmissionRecordOut(CamelModel):
    id: str
    facility_id: str
    month: str
    source: str
    activity_value: float
    unit: str
    factor: float
    factor_unit: str
    factor_ref: str
    scope: str
    co2e: float = Field(alias="co2e")
    prev_co2e: float = Field(alias="prevCo2e")
    calc_status: str
    review_status: str
    comments: list[EmissionComment] = Field(default_factory=list)
    # calculation trace (absent on legacy records until a recalculation links them)
    factor_id: str | None = None
    submission_id: str | None = None
    formula: str | None = None
    calc_note: str | None = None
    calculated_at: str | None = None


class EmissionFactorBase(CamelModel):
    source: str = Field(min_length=1, max_length=200)
    scope: str = Field(pattern=r"^Scope [123]$")
    value: float = Field(gt=0)
    unit: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    valid_from: str = Field(min_length=1)
    status: str = Field(pattern=r"^(Active|Superseded)$")
    category: str | None = Field(default=None, max_length=80)  # Scope 3 category the factor belongs to


class EmissionFactorCreate(EmissionFactorBase):
    id: str | None = None


class EmissionFactorUpdate(CamelModel):
    source: str | None = Field(default=None, min_length=1, max_length=200)
    scope: str | None = Field(default=None, pattern=r"^Scope [123]$")
    value: float | None = Field(default=None, gt=0)
    unit: str | None = None
    reference: str | None = None
    valid_from: str | None = None
    status: str | None = Field(default=None, pattern=r"^(Active|Superseded)$")
    category: str | None = Field(default=None, max_length=80)


class EmissionFactorOut(EmissionFactorBase):
    id: str


class RecalculateRequest(CamelModel):
    """dry_run defaults to True so nothing is written unless explicitly requested."""
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    facility_id: str | None = Field(default=None, min_length=1)
    dry_run: bool = True


class RecalculateItem(CamelModel):
    id: str
    facility_id: str
    month: str
    source: str
    action: str
    old_co2e: float | None = Field(default=None, alias="oldCo2e")
    new_co2e: float = Field(alias="newCo2e")
    old_factor: float | None = None
    new_factor: float
    factor_id: str
    reason: str


class RecalculateSkip(CamelModel):
    target: str
    reason: str


class RecalculateResult(CamelModel):
    dry_run: bool
    evaluated: int
    created: int
    updated: int
    trace_linked: int
    unchanged: int
    skipped: list[RecalculateSkip] = Field(default_factory=list)
    items: list[RecalculateItem] = Field(default_factory=list)
