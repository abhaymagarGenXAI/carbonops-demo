"""Facility master-data integrity: unique codes, no orphans.

The facility code is part of generated ids (SUB-/EM-/EN-<code>-…), so it must be unique and must not change once data exists.
A facility, or a production unit, that other records still reference cannot be removed or renamed.
"""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.asset import AssetRepository
from app.repositories.emission import EmissionRecordRepository
from app.repositories.energy import EnergyRecordRepository
from app.repositories.facility import FacilityRepository
from app.repositories.initiative import InitiativeRepository
from app.repositories.scope3 import Scope3Repository
from app.repositories.submission import SubmissionRepository
from app.services.common import conflict

_LABELS = (("assets", "asset(s)"), ("submissions", "submission(s)"), ("emissionRecords", "emission record(s)"),
           ("energyRecords", "energy record(s)"), ("initiatives", "initiative(s)"), ("scope3Entries", "Scope 3 entry(ies)"))


def normalise_code(code: str) -> str:
    return code.strip().upper()


def dependents(db: Database, facility_id: str) -> dict[str, int]:
    f = {"facilityId": facility_id}
    counts = {
        "assets": AssetRepository(db).count(f), "submissions": SubmissionRepository(db).count(f),
        "emissionRecords": EmissionRecordRepository(db).count(f), "energyRecords": EnergyRecordRepository(db).count(f),
        "initiatives": InitiativeRepository(db).count(f), "scope3Entries": Scope3Repository(db).count(f),
    }
    return {k: v for k, v in counts.items() if v}


def _describe(counts: Mapping[str, int]) -> str:
    return ", ".join(f"{counts[k]} {label}" for k, label in _LABELS if k in counts)


def assert_code_free(db: Database, code: str, self_id: str | None = None) -> None:
    for f in FacilityRepository(db).list():
        if f["id"] != self_id and normalise_code(f["code"]) == code:
            raise conflict(f"Facility code '{code}' is already used by {f['name']}; codes must be unique")


def assert_code_change_allowed(db: Database, current: Mapping[str, Any], new_code: str) -> None:
    if normalise_code(current["code"]) == new_code:
        return
    used = dependents(db, current["id"])
    used.pop("assets", None)  # asset ids carry the code too, but existing ids stay valid; ids of *records* are what break
    if used:
        raise conflict(f"The code of {current['name']} cannot change: it is part of the ids of existing records ({_describe(used)})")


def assert_deletable(db: Database, facility_id: str) -> None:
    used = dependents(db, facility_id)
    if used:
        raise conflict(f"Facility is still referenced by {_describe(used)}; remove or reassign them first")


def assert_units_removable(db: Database, facility_id: str, new_units: list[str]) -> None:
    keep = set(new_units)
    in_use = {s["unit"] for s in SubmissionRepository(db).list({"facilityId": facility_id})} | \
             {a["unit"] for a in AssetRepository(db).list({"facilityId": facility_id})}
    lost = sorted(in_use - keep)
    if lost:
        raise conflict("Production unit(s) still in use by submissions or assets cannot be removed or renamed: " + ", ".join(lost))
