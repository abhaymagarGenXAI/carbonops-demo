from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, Db, require_permission
from app.repositories.energy import EnergyRecordRepository
from app.repositories.facility import FacilityRepository
from app.services import facilities as fac_svc
from app.schemas.common import DeleteResult
from app.repositories.submission import SubmissionRepository
from app.schemas.energy import (
    EnergyReconcileRequest, EnergyReconcileResult, EnergyRecordCreate, EnergyRecordOut, EnergyRecordUpdate,
)
from app.services import energy as svc
from app.services.common import audit, conflict, not_found

router = APIRouter(prefix="/energy-records", tags=["energy"])


@router.get("", response_model=list[EnergyRecordOut])
def list_energy(
    db: Db, _: CurrentUser, facility_id: str | None = None, month: str | None = None, stream: str | None = None
):
    filters = {k: v for k, v in {"facilityId": facility_id, "month": month, "stream": stream}.items() if v}
    return EnergyRecordRepository(db).list_visible(filters)


@router.post("/reconcile", response_model=EnergyReconcileResult, summary="Recompute energy records from submissions")
def reconcile_energy(
    body: EnergyReconcileRequest, db: Db, user: dict = Depends(require_permission("energy.reconcile"))
):
    return svc.reconcile(db, user, month=body.month, facility_id=body.facility_id, dry_run=body.dry_run)


@router.get("/{record_id}", response_model=EnergyRecordOut)
def get_energy(record_id: str, db: Db, _: CurrentUser):
    row = EnergyRecordRepository(db).get(record_id)
    if row is None:
        raise not_found("Energy record", record_id)
    return row


@router.post("", response_model=EnergyRecordOut, status_code=status.HTTP_201_CREATED)
def create_energy(body: EnergyRecordCreate, db: Db, user: dict = Depends(require_permission("energy.edit"))):
    facility = FacilityRepository(db).get(body.facility_id)
    if facility is None:
        raise not_found("Facility", body.facility_id)
    fac_svc.assert_active(db, body.facility_id)
    if SubmissionRepository(db).get_by_facility_month(body.facility_id, body.month):
        raise conflict(f"A submission exists for {body.month}; energy quantities are derived from it and cannot be added separately")
    data = body.model_dump(by_alias=True)
    if not data.get("id"):
        data["id"] = f"EN-{facility['code']}-{body.stream[:3].upper()}-{body.month.replace('-', '')}"
    out = EnergyRecordRepository(db).create(data)
    audit(db, user, "Saved", out["id"], f"{body.stream} record for {body.month} created.")
    return out


@router.patch("/{record_id}", response_model=EnergyRecordOut)
def update_energy(
    record_id: str, body: EnergyRecordUpdate, db: Db, user: dict = Depends(require_permission("energy.edit"))
):
    repo = EnergyRecordRepository(db)
    changes = body.model_dump(by_alias=True, exclude_none=True)
    current = repo.get(record_id)
    if current is None:
        raise not_found("Energy record", record_id)
    svc.guard_derived_edit(current, changes)
    out = repo.update(record_id, changes) if changes else current
    assert out is not None
    audit(db, user, "Saved", record_id, "Energy record updated.")
    return out


@router.delete("/{record_id}", response_model=DeleteResult)
def delete_energy(record_id: str, db: Db, user: dict = Depends(require_permission("energy.edit"))):
    repo = EnergyRecordRepository(db)
    current = repo.get(record_id)
    if current is None:
        raise not_found("Energy record", record_id)
    if current.get("submissionId"):
        raise conflict(f"{record_id} is derived from submission {current['submissionId']} and cannot be deleted")
    repo.delete(record_id)
    audit(db, user, "Deleted", record_id, "Energy record removed.")
    return DeleteResult(id=record_id, deleted=True)
