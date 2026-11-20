from __future__ import annotations

import random

from fastapi import APIRouter, Depends, status
from pymongo.errors import DuplicateKeyError

from app.core.deps import ADMINISTRATOR, PLANT_ENGINEER, CurrentUser, Db, require_roles
from app.repositories.asset import AssetRepository
from app.repositories.facility import FacilityRepository
from app.schemas.asset import AssetCreate, AssetOut, AssetUpdate
from app.schemas.common import DeleteResult
from app.services.common import audit, conflict, not_found

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetOut])
def list_assets(db: Db, _: CurrentUser, facility_id: str | None = None):
    repo = AssetRepository(db)
    return repo.list_by_facility(facility_id) if facility_id else repo.list()


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, db: Db, _: CurrentUser):
    row = AssetRepository(db).get(asset_id)
    if row is None:
        raise not_found("Asset", asset_id)
    return row


@router.post("", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
def create_asset(body: AssetCreate, db: Db, user: dict = Depends(require_roles(ADMINISTRATOR))):
    facility = FacilityRepository(db).get(body.facility_id)
    if facility is None:
        raise not_found("Facility", body.facility_id)
    repo = AssetRepository(db)
    data = body.model_dump(by_alias=True)
    if data.get("id"):
        out = repo.create(data)
    else:
        for _ in range(10):
            data["id"] = f"{facility['code']}-AST-{random.randint(200, 999)}"
            try:
                out = repo.create(data)
                break
            except DuplicateKeyError:
                continue
        else:
            raise conflict("Could not allocate a unique asset id, please retry")
    audit(db, user, "Saved", out["id"], f'Asset "{out["name"]}" created.')
    return out


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: str, body: AssetUpdate, db: Db, user: dict = Depends(require_roles(ADMINISTRATOR, PLANT_ENGINEER))
):
    changes = body.model_dump(by_alias=True, exclude_none=True)
    if "facilityId" in changes and not FacilityRepository(db).exists(changes["facilityId"]):
        raise not_found("Facility", changes["facilityId"])
    repo = AssetRepository(db)
    out = repo.update(asset_id, changes) if changes else repo.get(asset_id)
    if out is None:
        raise not_found("Asset", asset_id)
    audit(db, user, "Saved", asset_id, f'Asset "{out["name"]}" updated.')
    return out


@router.delete("/{asset_id}", response_model=DeleteResult)
def delete_asset(asset_id: str, db: Db, user: dict = Depends(require_roles(ADMINISTRATOR))):
    if not AssetRepository(db).delete(asset_id):
        raise not_found("Asset", asset_id)
    audit(db, user, "Deleted", asset_id, "Asset removed from inventory.")
    return DeleteResult(id=asset_id, deleted=True)
