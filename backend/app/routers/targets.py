from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, Db, require_permission
from app.schemas.targets import BaselineIn, TargetsIn, TargetsOut
from app.services import targets as svc

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=TargetsOut, summary="Baseline, targets and progress vs approved emissions")
def get_targets(db: Db, _: CurrentUser):
    return svc.get_targets(db)


@router.put("/baseline", response_model=TargetsOut, summary="Freeze a baseline from approved emissions")
def put_baseline(body: BaselineIn, db: Db, user: dict = Depends(require_permission("target.manage"))):
    return svc.set_baseline(db, user, body.start, body.end)


@router.put("", response_model=TargetsOut, summary="Replace the reduction targets")
def put_targets(body: TargetsIn, db: Db, user: dict = Depends(require_permission("target.manage"))):
    return svc.set_targets(db, user, [t.model_dump(by_alias=True) for t in body.targets])
