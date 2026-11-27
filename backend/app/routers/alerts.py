from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import CurrentUser, Db, require_permission
from app.schemas.common import CamelModel
from app.services import alerts as svc
from app.services.common import audit, not_found

router = APIRouter(prefix="/alerts", tags=["alerts"])

_PERIOD = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class AlertOut(CamelModel):
    id: str
    kind: str = ""
    submission_id: str | None = None
    severity: str
    title: str
    detail: str
    action: str


class DiscardResult(CamelModel):
    id: str
    discarded: bool = True


@router.get("", response_model=list[AlertOut], summary="Live data-quality and deadline alerts for the open period")
def list_alerts(db: Db, _: CurrentUser, period: str | None = _PERIOD):
    return svc.build_alerts(db, period)


@router.delete("/{alert_id}", response_model=DiscardResult, summary="Permanently discard an alert (needs alert.discard)")
def discard_alert(alert_id: str, db: Db, period: str | None = _PERIOD, user: dict = Depends(require_permission("alert.discard"))):
    alert = svc.discard(db, user, alert_id, period)
    if alert is None:
        raise not_found("Alert", alert_id)  # already resolved, already discarded, or not part of this period
    audit(db, user, "Discarded", alert_id, f"Alert discarded permanently: {alert['title']}")
    return DiscardResult(id=alert_id)
