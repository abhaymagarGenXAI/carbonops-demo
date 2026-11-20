from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import SUSTAINABILITY_MANAGER, CurrentUser, Db, require_roles
from app.repositories.emission import EmissionRecordRepository
from app.schemas.emission import EmissionRecordOut, RecalculateRequest, RecalculateResult
from app.schemas.submission import ReviewRequest
from app.services import carbon, emissions as svc
from app.services.common import not_found

router = APIRouter(prefix="/emission-records", tags=["carbon accounting"])


@router.get("", response_model=list[EmissionRecordOut])
def list_emissions(
    db: Db, _: CurrentUser, facility_id: str | None = None, month: str | None = None, scope: str | None = None
):
    filters = {k: v for k, v in {"facilityId": facility_id, "month": month, "scope": scope}.items() if v}
    return EmissionRecordRepository(db).list(filters)


@router.post("/recalculate", response_model=RecalculateResult, summary="Recalculate emissions from stored activity data")
def recalculate_emissions(
    body: RecalculateRequest, db: Db, user: dict = Depends(require_roles(SUSTAINABILITY_MANAGER))
):
    return carbon.recalculate(db, user, month=body.month, facility_id=body.facility_id, dry_run=body.dry_run)


@router.get("/{emission_id}", response_model=EmissionRecordOut)
def get_emission(emission_id: str, db: Db, _: CurrentUser):
    row = EmissionRecordRepository(db).get(emission_id)
    if row is None:
        raise not_found("Emission record", emission_id)
    return row


@router.post("/{emission_id}/review", response_model=EmissionRecordOut, summary="Approve / reject a calculation")
def review_emission(
    emission_id: str, body: ReviewRequest, db: Db, user: dict = Depends(require_roles(SUSTAINABILITY_MANAGER))
):
    return svc.review_emission(db, user, emission_id, body)
