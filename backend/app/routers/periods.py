from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import Field

from app.core.deps import SUSTAINABILITY_MANAGER, CurrentUser, Db, require_roles
from app.schemas.common import DATE_PATTERN, CamelModel
from app.services import periods as svc

router = APIRouter(prefix="/reporting-periods", tags=["reporting periods"])


class PeriodOut(CamelModel):
    id: str
    period: str
    status: str
    submission_due: str
    approval_due: str
    locked_on: str = "—"


class OpenNextRequest(CamelModel):
    submission_due: str | None = Field(default=None, pattern=DATE_PATTERN)
    approval_due: str | None = Field(default=None, pattern=DATE_PATTERN)


class StatusRequest(CamelModel):
    status: Literal["In Review", "Locked"]


@router.get("", response_model=list[PeriodOut])
def list_periods(db: Db, _: CurrentUser):
    return svc.list_periods(db)


@router.post("", response_model=PeriodOut, status_code=status.HTTP_201_CREATED, summary="Open the next reporting period")
def open_next(body: OpenNextRequest, db: Db, user: dict = Depends(require_roles(SUSTAINABILITY_MANAGER))):
    return svc.open_next_period(db, user, submission_due=body.submission_due, approval_due=body.approval_due)


@router.post("/{period}/status", response_model=PeriodOut, summary="Move a period to In Review or Locked")
def set_status(period: str, body: StatusRequest, db: Db, user: dict = Depends(require_roles(SUSTAINABILITY_MANAGER))):
    return svc.set_status(db, user, period, body.status)
