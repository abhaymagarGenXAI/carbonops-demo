from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, Db
from app.services import forecast as svc

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("", summary="Trend forecast of approved emissions and outlook against targets")
def get_forecast(db: Db, _: CurrentUser, horizon: int = 12):
    return svc.build(db, horizon)
