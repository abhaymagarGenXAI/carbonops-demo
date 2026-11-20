"""Replacements for the temporary TanStack server functions used by the
/db-model-test and /db-crud-test pages (testDatabaseModels, testFacilityCrud,
seedFacilitiesToDatabase). Administrator only."""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends

from app.core.deps import ADMINISTRATOR, Db, require_roles
from app.repositories.facility import FacilityRepository

router = APIRouter(prefix="/admin/db", tags=["admin tools"], dependencies=[Depends(require_roles(ADMINISTRATOR))])

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "seed_data.json"


@router.get("/status")
def db_status(db: Db):
    db.command("ping")
    return {"connected": True, "facilityCount": FacilityRepository(db).count()}


@router.post("/crud-test")
def facility_crud_test(db: Db):
    repo = FacilityRepository(db)
    test_id = f"TEST-{int(time.time() * 1000)}"
    created = repo.create(
        {
            "id": test_id, "name": "MongoDB Test Facility", "code": "TEST", "region": "Test Region",
            "type": "Test Facility", "manager": "Test Manager", "units": ["Test Unit"],
            "commissioned": "2026-08-12", "employees": 10,
        }
    )
    read = repo.get(test_id)
    updated = repo.update(test_id, {"name": "MongoDB Updated Facility", "employees": 20})
    deleted = repo.delete(test_id)
    return {"created": bool(created), "read": bool(read), "updated": bool(updated), "deleted": deleted}


@router.post("/seed-facilities")
def seed_facilities(db: Db):
    repo = FacilityRepository(db)
    if repo.count():
        # Recovery tool for an empty database only: on a live system it would resurrect facilities that were deliberately deleted.
        return [{"facilityId": f["id"], "status": "skipped-facilities-exist"} for f in repo.list()]
    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    results = []
    for f in seed["facilities"]:
        if repo.exists(f["id"]):
            results.append({"facilityId": f["id"], "status": "already-exists"})
            continue
        repo.create(f)
        results.append({"facilityId": f["id"], "status": "created"})
    return results
