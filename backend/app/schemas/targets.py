from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel

Month = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class BaselineIn(CamelModel):
    start: str = Month
    end: str = Month

    @model_validator(mode="after")
    def _range(self):
        from app.services.targets_engine import month_index

        n = month_index(self.end) - month_index(self.start) + 1
        if n < 1:
            raise ValueError("Baseline end month must not be before its start month")
        if n > 12:
            raise ValueError("A baseline covers at most 12 months")
        return self


class TargetIn(CamelModel):
    scope: Literal["Total", "Scope 1", "Scope 2"]
    reduction_pct: float = Field(gt=0, le=100)
    target_year: int = Field(ge=2000, le=2100)


class TargetsIn(CamelModel):
    targets: list[TargetIn] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _unique(self):
        scopes = [t.scope for t in self.targets]
        if len(scopes) != len(set(scopes)):
            raise ValueError("Only one target per scope")
        return self


class TargetsOut(CamelModel):
    baseline: dict[str, Any] | None = None
    targets: list[dict[str, Any]] = Field(default_factory=list)
    progress: list[dict[str, Any]] = Field(default_factory=list)
    series: list[dict[str, Any]] = Field(default_factory=list)
    complete_through: str | None = None
    incomplete_months: list[str] = Field(default_factory=list)
    at_risk_tolerance_pct: float
