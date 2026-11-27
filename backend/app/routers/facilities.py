from __future__ import annotations

import time

from fastapi import APIRouter, Depends, status

from app.core.deps import CurrentUser, Db, require_permission
from app.repositories.facility import FacilityRepository
from app.services import iam, masters
from app.services import facilities as fac
from app.schemas.facility import FacilityCreate, FacilityOut, FacilityUpdate, ProductionUnitCreate
from app.utils.time import utcnow
from app.services.common import audit, conflict, not_found, unprocessable

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
def create_facility(body: FacilityCreate, db: Db, user: dict = Depends(require_permission("facility.manage"))):
    data = body.model_dump(by_alias=True)
    data["code"] = fac.normalise_code(data["code"])
    fac.assert_code_free(db, data["code"])
    if not data.get("id"):
        data["id"] = f"{body.code.strip().upper().replace(' ', '-')}-{int(time.time() * 1000)}"
    out = FacilityRepository(db).create(data)  # duplicate id -> 409 via global handler
    masters.sync_units(db, out["id"], out.get("units") or [])
    audit(db, user, "Saved", out["id"], f'Facility "{out["name"]}" created.')
    return out


@router.patch("/{facility_id}", response_model=FacilityOut)
def update_facility(facility_id: str, body: FacilityUpdate, db: Db, user: dict = Depends(require_permission("facility.manage"))):
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
    if "units" in changes:
        masters.sync_units(db, facility_id, changes["units"])
    if "name" in changes:
        iam.refresh_facility_labels(db, facility_id)
    audit(db, user, "Saved", facility_id, f'Facility "{out["name"]}" updated.')
    return out


@router.post("/{facility_id}/units", response_model=FacilityOut, status_code=status.HTTP_201_CREATED,
             summary="Add a production unit to a facility (Administrator)")
def add_production_unit(facility_id: str, body: ProductionUnitCreate, db: Db, user: dict = Depends(require_permission("facility.manage"))):
    repo = FacilityRepository(db)
    current = repo.get(facility_id)
    if current is None:
        raise not_found("Facility", facility_id)
    fac.assert_active(db, facility_id)
    name = " ".join(body.name.split())
    if "," in name:
        raise unprocessable("A unit name cannot contain a comma")
    units = list(current.get("units") or [])
    if name.lower() in {u.lower() for u in units}:
        raise conflict(f'"{name}" already exists in {current["name"]}')
    out = repo.update(facility_id, {"units": [*units, name]})
    masters.sync_units(db, facility_id, [*units, name], prune=False)
    audit(db, user, "Saved", facility_id, f'Production unit "{name}" added to {current["name"]}.')
    return out


@router.post("/{facility_id}/deactivate", response_model=FacilityOut, summary="Hide a facility from data entry and dropdowns; its history is kept")
def deactivate_facility(facility_id: str, db: Db, user: dict = Depends(require_permission("facility.manage"))):
    repo = FacilityRepository(db)
    current = repo.get(facility_id)
    if current is None:
        raise not_found("Facility", facility_id)
    if not fac.is_active(current):
        return current
    fac.assert_deactivatable(db, facility_id)
    now = utcnow().isoformat()
    out = repo.update(facility_id, {"active": False, "deactivatedAt": now, "deactivatedBy": user["name"]})
    audit(db, user, "Deactivated", facility_id, f'Facility "{current["name"]}" deactivated; history kept.')
    return out


@router.post("/{facility_id}/reactivate", response_model=FacilityOut, summary="Make a deactivated facility available again")
def reactivate_facility(facility_id: str, db: Db, user: dict = Depends(require_permission("facility.manage"))):
    repo = FacilityRepository(db)
    current = repo.get(facility_id)
    if current is None:
        raise not_found("Facility", facility_id)
    now = utcnow().isoformat()
    out = repo.update(facility_id, {"active": True, "deactivatedAt": None, "deactivatedBy": None})
    audit(db, user, "Reactivated", facility_id, f'Facility "{current["name"]}" reactivated.')
    return out
