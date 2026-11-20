from __future__ import annotations

import time

from fastapi import APIRouter, Depends, status

from app.core.deps import ADMINISTRATOR, CurrentUser, Db, require_roles
from app.repositories.facility import FacilityRepository
from app.services import facilities as fac
from app.schemas.common import DeleteResult
from app.schemas.facility import FacilityCreate, FacilityOut, FacilityUpdate
from app.services.common import audit, not_found

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=list[FacilityOut])
def list_facilities(db: Db, _: CurrentUser):
    return FacilityRepository(db).list()


@router.get("/{facility_id}", response_model=FacilityOut)
def get_facility(facility_id: str, db: Db, _: CurrentUser):
    row = FacilityRepository(db).get(facility_id)
    if row is None:
        raise not_found("Facility", facility_id)
    return row


@router.post("", response_model=FacilityOut, status_code=status.HTTP_201_CREATED)
def create_facility(body: FacilityCreate, db: Db, user: dict = Depends(require_roles(ADMINISTRATOR))):
    data = body.model_dump(by_alias=True)
    data["code"] = fac.normalise_code(data["code"])
    fac.assert_code_free(db, data["code"])
    if not data.get("id"):
        data["id"] = f"{body.code.strip().upper().replace(' ', '-')}-{int(time.time() * 1000)}"
    out = FacilityRepository(db).create(data)  # duplicate id -> 409 via global handler
    audit(db, user, "Saved", out["id"], f'Facility "{out["name"]}" created.')
    return out


@router.patch("/{facility_id}", response_model=FacilityOut)
def update_facility(facility_id: str, body: FacilityUpdate, db: Db, user: dict = Depends(require_roles(ADMINISTRATOR))):
    repo = FacilityRepository(db)
    changes = body.model_dump(by_alias=True, exclude_none=True)
    current = repo.get(facility_id)
    if current is None:
        raise not_found("Facility", facility_id)
    if "code" in changes:
        changes["code"] = fac.normalise_code(changes["code"])
        fac.assert_code_free(db, changes["code"], facility_id)
        fac.assert_code_change_allowed(db, current, changes["code"])
    if "units" in changes:
        fac.assert_units_removable(db, facility_id, changes["units"])
    out = repo.update(facility_id, changes) if changes else repo.get(facility_id)
    if out is None:
        raise not_found("Facility", facility_id)
    audit(db, user, "Saved", facility_id, f'Facility "{out["name"]}" updated.')
    return out


@router.delete("/{facility_id}", response_model=DeleteResult)
def delete_facility(facility_id: str, db: Db, user: dict = Depends(require_roles(ADMINISTRATOR))):
    if FacilityRepository(db).exists(facility_id):
        fac.assert_deletable(db, facility_id)
    if not FacilityRepository(db).delete(facility_id):
        raise not_found("Facility", facility_id)
    audit(db, user, "Deleted", facility_id, "Facility removed from master data.")
    return DeleteResult(id=facility_id, deleted=True)
