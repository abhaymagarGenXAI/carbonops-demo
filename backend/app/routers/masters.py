from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, Db
from app.db import collections as C

router = APIRouter(tags=["master data"])

_HIDE = {"_id": 0, "createdAt": 0, "updatedAt": 0}


def _rows(db, coll: str, sort: str, flt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list(db[coll].find(flt or {}, _HIDE).sort(sort, 1))


@router.get("/production-units", response_model=list[dict[str, Any]])
def production_units(db: Db, _: CurrentUser, facility_id: str | None = Query(default=None, alias="facilityId")):
    return _rows(db, C.PRODUCTION_UNITS, "unitId", {"facilityId": facility_id} if facility_id else None)


@router.get("/asset-types", response_model=list[dict[str, Any]])
def asset_types(db: Db, _: CurrentUser):
    return _rows(db, C.ASSET_TYPES, "assetTypeId")


@router.get("/energy-streams", response_model=list[dict[str, Any]])
def energy_streams(db: Db, _: CurrentUser):
    return _rows(db, C.ENERGY_STREAMS, "streamId")


@router.get("/emission-sources", response_model=list[dict[str, Any]])
def emission_sources(db: Db, _: CurrentUser):
    return _rows(db, C.EMISSION_SOURCES, "sourceId")


@router.get("/units-of-measure", response_model=list[dict[str, Any]])
def units_of_measure(db: Db, _: CurrentUser):
    return _rows(db, C.UNITS_OF_MEASURE, "uomId")
