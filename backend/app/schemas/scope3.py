from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


class Scope3EntryIn(CamelModel):
    month: str = Field(pattern=MONTH)
    category: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=200, description="Name of the Scope 3 emission factor to apply")
    activity_value: float = Field(gt=0, le=1e12)
    facility_id: str | None = Field(default=None, min_length=1)
    description: str = Field(default="", max_length=300)


class Scope3ReviewIn(CamelModel):
    decision: str = Field(pattern=r"^(Approve|Reject)$")
    comment: str = Field(default="", max_length=500)


class Scope3EntryOut(CamelModel):
    id: str
    month: str
    category: str
    source: str
    facility_id: str | None = None
    description: str = ""
    activity_value: float
    unit: str
    method: str
    factor: float
    factor_unit: str
    factor_ref: str
    factor_id: str
    co2e: float = Field(alias="co2e")
    formula: str
    calc_note: str = ""
    status: str
    created_by: str
    created_by_id: str
    reviewer: str | None = None
    review_comment: str | None = None
    reviewed_at: str | None = None
