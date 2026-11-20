from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, Db
from app.schemas.common import CamelModel
from app.services import alerts as svc

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertOut(CamelModel):
    id: str
    kind: str = ""
    submission_id: str | None = None
    severity: str
    title: str
    detail: str
    action: str


@router.get("", response_model=list[AlertOut], summary="Live data-quality and deadline alerts for the open period")
def list_alerts(db: Db, _: CurrentUser, period: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
    return svc.build_alerts(db, period)
