from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import DATE_PATTERN, CamelModel

InitStatus = Literal["Planned", "In Progress", "On Hold", "Completed"]
Timeline = Literal["On Track", "At Risk", "Delayed", "Complete"]
Priority = Literal["Critical", "High", "Medium", "Low"]


class Milestone(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    date: str = Field(pattern=DATE_PATTERN)
    done: bool = False


class InitiativeCreate(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1)
    owner: str = Field(default="Unassigned", max_length=100)
    facility_id: str = Field(min_length=1)
    expected_reduction: float = Field(gt=0)
    investment: float = Field(ge=0)
    annual_savings: float = Field(default=0, ge=0)
    start_date: str = Field(pattern=DATE_PATTERN)
    end_date: str = Field(pattern=DATE_PATTERN)
    priority: Priority = "High"
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:  # ISO dates compare lexicographically
            raise ValueError("endDate must not be before startDate")
        return self


class InitiativeUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    type: str | None = None
    owner: str | None = None
    facility_id: str | None = None
    status: InitStatus | None = None
    expected_reduction: float | None = Field(default=None, gt=0)
    actual_reduction: float | None = Field(default=None, ge=0)
    investment: float | None = Field(default=None, ge=0)
    annual_savings: float | None = Field(default=None, ge=0)
    completion: float | None = Field(default=None, ge=0, le=100)
    start_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    end_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    timeline: Timeline | None = None
    priority: Priority | None = None
    dependencies: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    milestones: list[Milestone] | None = Field(default=None, max_length=20)


class AdvanceRequest(CamelModel):
    step: int = Field(default=10, ge=1, le=100)


class InitiativeOut(CamelModel):
    id: str
    name: str
    type: str
    owner: str
    facility_id: str
    status: str
    expected_reduction: float
    actual_reduction: float
    investment: float
    annual_savings: float = 0
    roi: float
    annual_cost: float | None = None
    macc_cost: float | None = None
    payback_years: float | None = None
    completion: float
    start_date: str
    end_date: str
    timeline: str
    priority: str
    dependencies: str = ""
    notes: str = ""
    milestones: list[Milestone] = Field(default_factory=list)


class AssumptionsIn(CamelModel):
    carbon_value_per_tonne: float = Field(ge=0, le=1e7)
    discount_rate_pct: float = Field(ge=0, le=30)
    lifetime_years: int = Field(ge=1, le=40)


class AssumptionsOut(AssumptionsIn):
    pass
