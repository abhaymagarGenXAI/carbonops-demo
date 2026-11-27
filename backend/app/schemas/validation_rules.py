from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import CamelModel

LimitField = Literal["electricity", "diesel", "naturalGas", "steam", "flareGas", "methaneLeak"]


class LimitIn(CamelModel):
    field: LimitField
    max: float = Field(gt=0, le=1e12)
    enabled: bool = True
    block: bool = False


class ValidationRulesIn(CamelModel):
    spike_enabled: bool = True
    spike_pct: float = Field(default=30, ge=1, le=500)
    high_pct: float = Field(default=50, ge=1, le=1000)
    history_months: int = Field(default=3, ge=1, le=12)
    spike_block_high: bool = False
    zero_enabled: bool = True
    zero_block: bool = False
    limits: list[LimitIn] = Field(default_factory=list, max_length=12)
    inspection_interval_days: int = Field(default=150, ge=30, le=730)
    energy_variance_pct: float = Field(default=14.0, gt=0, le=500)

    @model_validator(mode="after")
    def _consistent(self):
        if self.high_pct < self.spike_pct:
            raise ValueError("highPct must be at least spikePct")
        fields = [l.field for l in self.limits]
        if len(fields) != len(set(fields)):
            raise ValueError("Only one control limit per field is allowed")
        return self


class ValidationRulesOut(ValidationRulesIn):
    pass
