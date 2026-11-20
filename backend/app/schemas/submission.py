from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import MONTH_PATTERN, CamelModel, ReviewDecision

# "Failed" was removed: nothing produced it. Rules that must stop bad data are "blocking" (see validation config) and
# refuse the submission outright instead of storing it.
Validation = Literal["Passed", "Warnings", "Not Run"]


class ActivityDataIn(CamelModel):
    production_volume: float = Field(ge=0)
    electricity: float = Field(ge=0)
    diesel: float = Field(ge=0)
    natural_gas: float = Field(ge=0)
    steam: float = Field(ge=0)
    water: float = Field(ge=0)
    flare_gas: float = Field(ge=0)
    methane_leak: float = Field(ge=0)
    renewable: float = Field(ge=0)
    operating_hours: float = Field(ge=0, le=744)
    remarks: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=1000)


class ActivityDataOut(CamelModel):
    production_volume: float = 0
    electricity: float = 0
    diesel: float = 0
    natural_gas: float = 0
    steam: float = 0
    water: float = 0
    flare_gas: float = 0
    methane_leak: float = 0
    renewable: float = 0
    operating_hours: float = 0
    remarks: str = ""
    notes: str = ""


class SubmissionSave(CamelModel):
    """Save a draft or submit for review. One submission exists per facility + month."""

    facility_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    month: str = Field(pattern=MONTH_PATTERN)
    status: Literal["Draft", "Submitted"]
    data: ActivityDataIn
    revision: int | None = Field(default=None, ge=0, description="Revision the client last saw; a mismatch is refused (409)")


class ReviewRequest(CamelModel):
    status: ReviewDecision
    comment: str = Field(default="", max_length=2000)
    revision: int | None = Field(default=None, ge=0, description="Revision the reviewer is looking at; a mismatch is refused (409)")


class SubmissionOut(CamelModel):
    id: str
    facility_id: str
    unit: str
    month: str
    status: str
    review_action: str = "None"
    submitted_by: str
    updated_at: str | None = None
    submitted_at: str | None = None
    reviewed_at: str | None = None
    reviewer: str = "—"
    reviewer_comments: str = ""
    validation: str = "Not Run"
    completeness: float = 0
    anomalies: list[str] = Field(default_factory=list)
    revision: int = 0
    data: ActivityDataOut
