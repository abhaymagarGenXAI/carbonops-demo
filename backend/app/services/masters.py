"""Stage 2 master data on MongoDB: production units, asset types, units of measure, energy streams, emission sources
and versioned emission factors (see DATABASE_ARCHITECTURE_PROPOSED.md).

Design notes
  * `emission_factors` stays the collection of factor VERSIONS (one row per validFrom; the proposed `emission_factor_versions`).
    Each version points to its series through `emissionSourceId` and carries an explicit `validTo` (exclusive end, null = open).
  * Emission records and Scope 3 entries keep their copied value/reference/formula (the calculation trace) and now ALSO store
    `emissionSourceId` + `factorVersionId` (= the factor row's id), so a source can be renamed without touching history.
  * The factor for a period is chosen by source id; name matching remains only as a fallback for rows not yet linked.
  * `ensure_masters` is idempotent: it creates missing masters and fills missing links; it never changes a figure.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Mapping

from pymongo.database import Database

from app.db import collections as C
from app.services import carbon_engine as ce
from app.services import energy_engine as ee
from app.utils.time import utcnow

log = logging.getLogger(__name__)

# (uomId, symbol, name, dimension) — the first six are the seeded reference list, the rest are used by the engines.
BASE_UOMS = [
    ("UOM-1", "kWh", "Kilowatt-hour", "Energy"), ("UOM-2", "SCM", "Standard Cubic Metre", "Volume (gas)"),
    ("UOM-3", "L", "Litre", "Volume (liquid)"), ("UOM-4", "t", "Tonne", "Mass"),
    ("UOM-5", "tCO₂e", "Tonne CO₂ equivalent", "Emissions"), ("UOM-6", "boe", "Barrel of Oil Equivalent", "Production"),
    ("UOM-7", "kg CH₄", "Kilogram of methane", "Mass"), ("UOM-8", "GJ", "Gigajoule", "Energy"), ("UOM-9", "INR", "Indian rupee", "Money"),
]
UOM_ALIAS = {"litres": "L", "tonnes": "t"}  # engine display units -> master symbol
# Emission source -> the energy stream it is calculated from (None = not an energy stream, e.g. flaring or fugitive methane).
SOURCE_STREAM = {"Diesel Combustion": "Diesel", "Natural Gas Combustion": "Natural Gas", "Purchased Electricity": "Electricity",
                 "Imported Steam": "Steam"}
# Free-text asset energySource -> stream (others stay unlinked rather than guessed).
ASSET_STREAM = {"natural gas": "Natural Gas", "diesel": "Diesel", "electricity": "Electricity", "grid electricity": "Electricity",
                "solar": "Renewable Energy"}


def _next_id(db: Database, coll: str, field: str, prefix: str, width: int) -> str:
    nums = [int(d[field].rsplit("-", 1)[1]) for d in db[coll].find({field: {"$regex": f"^{prefix}-\\d+$"}}, {field: 1, "_id": 0})]
    return f"{prefix}-{(max(nums) if nums else 0) + 1:0{width}d}"


def _upsert(db: Database, coll: str, key: Mapping[str, Any], doc: Mapping[str, Any]) -> bool:
    r = db[coll].update_one(dict(key), {"$setOnInsert": {**doc, "createdAt": utcnow()}}, upsert=True)
    return bool(r.upserted_id)


# ------------------------------------------------------------------------------------ migration / seeding
def ensure_masters(db: Database) -> dict[str, int]:
    made: dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        made[k] = made.get(k, 0) + n

    for uid, sym, name, dim in BASE_UOMS:
        if _upsert(db, C.UNITS_OF_MEASURE, {"symbol": sym}, {"uomId": uid, "symbol": sym, "name": name, "dimension": dim}):
            bump("uom")
    uom = {u["symbol"]: u["uomId"] for u in db[C.UNITS_OF_MEASURE].find({}, {"_id": 0})}

    for i, st in enumerate(ee.STREAMS, 1):
        sym = UOM_ALIAS.get(st.unit, st.unit)
        if _upsert(db, C.ENERGY_STREAMS, {"streamName": st.name}, {
                "streamId": f"STR-{i:02d}", "streamName": st.name, "code": st.code, "field": st.field, "nativeUomId": uom.get(sym),
                "gjPerNativeUnit": st.gj_per_unit, "isSystem": True, "isActive": True}):
            bump("energyStreams")
    stream = {s["streamName"]: s["streamId"] for s in db[C.ENERGY_STREAMS].find({}, {"_id": 0})}

    for i, sp in enumerate(ce.SOURCES, 1):
        sym = UOM_ALIAS.get(sp.unit, sp.unit)
        if _upsert(db, C.EMISSION_SOURCES, {"sourceName": sp.name}, {
                "sourceId": f"SRC-{i:02d}", "sourceName": sp.name, "scope": sp.scope, "field": sp.field, "activityUomId": uom.get(sym),
                "energyStreamId": stream.get(SOURCE_STREAM.get(sp.name, "")), "category": None, "isSystem": True, "isActive": True}):
            bump("emissionSources")
    for f in db[C.EMISSION_FACTORS].find({"scope": "Scope 3"}, {"_id": 0}):
        resolve_source(db, f["source"], "Scope 3", f.get("category"), create=True)

    src = source_ids(db)
    for f in db[C.EMISSION_FACTORS].find({"emissionSourceId": {"$exists": False}}, {"_id": 0, "factorId": 1, "source": 1}):
        if f["source"] in src:
            db[C.EMISSION_FACTORS].update_one({"factorId": f["factorId"]}, {"$set": {"emissionSourceId": src[f["source"]]}})
            bump("factorsLinked")
    for sid in set(src.values()):
        refresh_factor_validity(db, sid)

    for name, sid in src.items():
        for coll in (C.EMISSION_RECORDS, C.SCOPE3_ENTRIES):
            r = db[coll].update_many({"source": name, "emissionSourceId": {"$exists": False}}, {"$set": {"emissionSourceId": sid}})
            bump("recordsLinked", r.modified_count)
    for coll in (C.EMISSION_RECORDS, C.SCOPE3_ENTRIES):
        for d in db[coll].find({"factorId": {"$exists": True}, "factorVersionId": {"$exists": False}}, {"_id": 0, "factorId": 1}):
            r = db[coll].update_many({"factorId": d["factorId"], "factorVersionId": {"$exists": False}}, {"$set": {"factorVersionId": d["factorId"]}})
            bump("recordsLinked", r.modified_count)
    for name, sid in stream.items():
        r = db[C.ENERGY_RECORDS].update_many({"stream": name, "energyStreamId": {"$exists": False}}, {"$set": {"energyStreamId": sid}})
        bump("energyLinked", r.modified_count)

    for fac in db[C.FACILITIES].find({}, {"_id": 0, "facilityId": 1, "units": 1}):
        made_units = sync_units(db, fac["facilityId"], fac.get("units") or [], prune=False)
        bump("productionUnits", made_units)
    for a in db[C.ASSETS].find({"$or": [{"unitId": {"$exists": False}}, {"assetTypeId": {"$exists": False}}, {"energyStreamId": {"$exists": False}}]}, {"_id": 0}):
        link_asset(db, a["assetId"])
        bump("assetsLinked")
    for s in db[C.SUBMISSIONS].find({"unitId": {"$exists": False}}, {"_id": 0, "submissionId": 1, "facilityId": 1, "unit": 1}):
        uid = unit_id(db, s["facilityId"], s.get("unit"))
        if uid:
            db[C.SUBMISSIONS].update_one({"submissionId": s["submissionId"]}, {"$set": {"unitId": uid}})
            bump("submissionsLinked")
    made = {k: v for k, v in made.items() if v}
    if made:
        log.info("Masters ensured: %s", made)
    return made


# ------------------------------------------------------------------------------------ lookups
def source_ids(db: Database) -> dict[str, str]:
    return {s["sourceName"]: s["sourceId"] for s in db[C.EMISSION_SOURCES].find({}, {"_id": 0, "sourceName": 1, "sourceId": 1})}


def resolve_source(db: Database, name: str, scope: str, category: str | None = None, *, create: bool) -> str | None:
    """Source id for a factor/entry source name. Scope 3 sources are created on first use; Scope 1/2 sources are the engine's fixed set."""
    row = db[C.EMISSION_SOURCES].find_one({"sourceName": name}, {"_id": 0})
    if row:
        return row["sourceId"]
    if not create or scope != "Scope 3":
        return None
    sid = _next_id(db, C.EMISSION_SOURCES, "sourceId", "SRC", 2)
    db[C.EMISSION_SOURCES].insert_one({"sourceId": sid, "sourceName": name, "scope": "Scope 3", "field": None, "activityUomId": None,
                                      "energyStreamId": None, "category": category, "isSystem": False, "isActive": True, "createdAt": utcnow()})
    return sid


def unit_id(db: Database, facility_id: str, name: str | None) -> str | None:
    row = db[C.PRODUCTION_UNITS].find_one({"facilityId": facility_id, "unitName": name}, {"_id": 0, "unitId": 1}) if name else None
    return row["unitId"] if row else None


# ------------------------------------------------------------------------------------ production units
def sync_units(db: Database, facility_id: str, names: list[str], *, prune: bool = True) -> int:
    """Make production_units match the facility's unit-name list (ids of surviving units are kept)."""
    created = 0
    for n in dict.fromkeys(names):
        if db[C.PRODUCTION_UNITS].find_one({"facilityId": facility_id, "unitName": n}, {"_id": 1}) is None:
            db[C.PRODUCTION_UNITS].insert_one({"unitId": _next_id(db, C.PRODUCTION_UNITS, "unitId", "PU", 4), "facilityId": facility_id,
                                               "unitName": n, "isActive": True, "createdAt": utcnow()})
            created += 1
    if prune:
        db[C.PRODUCTION_UNITS].delete_many({"facilityId": facility_id, "unitName": {"$nin": list(names)}})
    for n in names:
        uid = unit_id(db, facility_id, n)
        if uid:
            db[C.ASSETS].update_many({"facilityId": facility_id, "unit": n, "unitId": {"$exists": False}}, {"$set": {"unitId": uid}})
            db[C.SUBMISSIONS].update_many({"facilityId": facility_id, "unit": n, "unitId": {"$exists": False}}, {"$set": {"unitId": uid}})
    return created


def drop_facility_units(db: Database, facility_id: str) -> None:
    db[C.PRODUCTION_UNITS].delete_many({"facilityId": facility_id})


# ------------------------------------------------------------------------------------ assets
def link_asset(db: Database, asset_id: str) -> None:
    """Resolve an asset's text fields (unit, type, energySource) to master ids. Unknown asset types are added; unknown energy sources stay unlinked."""
    a = db[C.ASSETS].find_one({"assetId": asset_id}, {"_id": 0})
    if a is None:
        return
    sets: dict[str, Any] = {"unitId": unit_id(db, a.get("facilityId"), a.get("unit"))}
    t = (a.get("type") or "").strip()
    if t:
        _upsert(db, C.ASSET_TYPES, {"typeName": t}, {"assetTypeId": _next_id(db, C.ASSET_TYPES, "assetTypeId", "AT", 2), "typeName": t,
                "defaultScope": a.get("carbonCategory"), "emissionSourceType": a.get("emissionSourceType"), "isActive": True})
        sets["assetTypeId"] = db[C.ASSET_TYPES].find_one({"typeName": t}, {"_id": 0})["assetTypeId"]
    sname = ASSET_STREAM.get((a.get("energySource") or "").strip().lower())
    row = db[C.ENERGY_STREAMS].find_one({"streamName": sname}, {"_id": 0}) if sname else None
    sets["energyStreamId"] = row["streamId"] if row else None
    db[C.ASSETS].update_one({"assetId": asset_id}, {"$set": sets})


# ------------------------------------------------------------------------------------ factor versions
def link_factor(db: Database, factor_id: str) -> dict[str, Any] | None:
    """Attach a factor version to its source (creating a Scope 3 source if new) and recompute that source's validity ranges."""
    f = db[C.EMISSION_FACTORS].find_one({"factorId": factor_id}, {"_id": 0})
    if f is None:
        return None
    old = f.get("emissionSourceId")
    sid = resolve_source(db, f["source"], f["scope"], f.get("category"), create=True)
    if sid:
        db[C.EMISSION_FACTORS].update_one({"factorId": factor_id}, {"$set": {"emissionSourceId": sid}})
        refresh_factor_validity(db, sid)
    if old and old != sid:
        refresh_factor_validity(db, old)
    return db[C.EMISSION_FACTORS].find_one({"factorId": factor_id}, {"_id": 0})


def refresh_factor_validity(db: Database, source_id: str | None) -> None:
    """validTo (exclusive) of each version = validFrom of the next version of the same source; the latest stays open-ended."""
    if not source_id:
        return
    rows = sorted(db[C.EMISSION_FACTORS].find({"emissionSourceId": source_id}, {"_id": 0, "factorId": 1, "validFrom": 1, "validTo": 1}),
                  key=lambda r: (r["validFrom"], r["factorId"]))
    for cur, nxt in zip(rows, rows[1:] + [None]):
        want = nxt["validFrom"] if nxt else None
        if cur.get("validTo", "<unset>") != want:
            db[C.EMISSION_FACTORS].update_one({"factorId": cur["factorId"]}, {"$set": {"validTo": want}})


# ------------------------------------------------------------------------------------ reconciliation
def verify(db: Database) -> dict[str, Any]:
    """Referential check used by tests and (Step 10) the nightly integrity script. Empty lists mean no orphans."""
    ids = {k: {d[f] for d in db[c].find({}, {f: 1, "_id": 0})} for k, c, f in [
        ("units", C.PRODUCTION_UNITS, "unitId"), ("sources", C.EMISSION_SOURCES, "sourceId"), ("streams", C.ENERGY_STREAMS, "streamId"),
        ("types", C.ASSET_TYPES, "assetTypeId"), ("factors", C.EMISSION_FACTORS, "factorId")]}
    out: dict[str, list[str]] = {k: [] for k in ("factorsWithoutSource", "recordsBadSource", "recordsBadFactor", "assetsBadRef", "submissionsBadUnit", "energyBadStream", "overlappingFactors")}
    for f in db[C.EMISSION_FACTORS].find({}, {"_id": 0}):
        if f.get("emissionSourceId") not in ids["sources"]:
            out["factorsWithoutSource"].append(f["factorId"])
    for coll in (C.EMISSION_RECORDS, C.SCOPE3_ENTRIES):
        for r in db[coll].find({}, {"_id": 0}):
            rid = r.get("emissionId") or r.get("entryId")
            if r.get("emissionSourceId") not in ids["sources"]:
                out["recordsBadSource"].append(rid)
            if "factorId" in r and r.get("factorVersionId") not in ids["factors"]:
                out["recordsBadFactor"].append(rid)
    for a in db[C.ASSETS].find({}, {"_id": 0}):
        if a.get("unitId") not in ids["units"] or a.get("assetTypeId") not in ids["types"] or (a.get("energyStreamId") and a["energyStreamId"] not in ids["streams"]):
            out["assetsBadRef"].append(a["assetId"])
    for s in db[C.SUBMISSIONS].find({}, {"_id": 0}):
        if s.get("unitId") not in ids["units"]:
            out["submissionsBadUnit"].append(s["submissionId"])
    for e in db[C.ENERGY_RECORDS].find({}, {"_id": 0}):
        if e.get("energyStreamId") not in ids["streams"]:
            out["energyBadStream"].append(e["recordId"])
    by_src: dict[str, list[dict[str, Any]]] = {}
    for f in db[C.EMISSION_FACTORS].find({}, {"_id": 0}):
        by_src.setdefault(f.get("emissionSourceId"), []).append(f)
    for sid, rows in by_src.items():
        rows.sort(key=lambda r: r["validFrom"])
        for a, b in zip(rows, rows[1:]):
            if a.get("validTo") is None or a["validTo"] > b["validFrom"]:
                out["overlappingFactors"].append(f"{a['factorId']}/{b['factorId']}")
    return {k: v for k, v in out.items() if v}


def total_co2e(db: Database) -> Decimal:
    """Sum of every stored emission record and Scope 3 entry — must be identical before and after any migration."""
    return sum((Decimal(str(d["co2e"])) for c in (C.EMISSION_RECORDS, C.SCOPE3_ENTRIES) for d in db[c].find({}, {"co2e": 1, "_id": 0})), Decimal("0"))
