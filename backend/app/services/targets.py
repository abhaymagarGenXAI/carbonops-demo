"""Baseline snapshot + reduction targets (one document in the reference store) and live progress."""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.emission import EmissionRecordRepository
from app.repositories.facility import FacilityRepository
from app.repositories.reference import ReferenceRepository
from app.services import targets_engine as te
from app.services.common import audit, conflict, unprocessable
from app.utils.time import to_display, utcnow

KEY = "emissionTargets"


def _doc(db: Database) -> dict[str, Any]:
    items = ReferenceRepository(db).get_items(KEY) or []
    return dict(items[0]) if items else {"id": "default", "baseline": None, "targets": []}


def _save(db: Database, doc: dict[str, Any]) -> None:
    ReferenceRepository(db).set_items(KEY, [doc])


def _facility_ids(db: Database) -> list[str]:
    return [f["id"] for f in FacilityRepository(db).list()]


def _agg(db: Database):
    return te.aggregate(EmissionRecordRepository(db).list())


def get_targets(db: Database) -> dict[str, Any]:
    doc = _doc(db)
    agg, fac = _agg(db), _facility_ids(db)
    complete = te.complete_months(agg, fac)
    base = doc.get("baseline")
    out: dict[str, Any] = {
        "baseline": base, "targets": doc.get("targets", []), "progress": [], "series": [],
        "completeThrough": complete[-1] if complete else None,
        "incompleteMonths": sorted(m for m in agg if m not in complete),
        "atRiskTolerancePct": te.AT_RISK_TOLERANCE_PCT,
    }
    if base:
        out["progress"] = [te.progress(base, t, agg, complete) for t in doc.get("targets", [])]
        out["series"] = te.series(base, doc.get("targets", []), agg, complete)
    return out


def set_baseline(db: Database, user: Mapping[str, Any], start: str, end: str) -> dict[str, Any]:
    built = te.build_baseline(_agg(db), _facility_ids(db), start, end)
    if built["snapshot"] is None:
        gaps = "; ".join(f"{m['month']}: {', '.join(m['facilityIds'])}" for m in built["missing"][:6])
        raise unprocessable(
            "Baseline needs approved emissions for every facility in every month of the range. Missing (month: facilities) — " + gaps)
    doc = _doc(db)
    base_year = int(end[:4])
    bad = [t for t in doc.get("targets", []) if int(t["targetYear"]) <= base_year]
    if bad:
        raise conflict(f"Existing {bad[0]['scope']} target year {bad[0]['targetYear']} is not after the new baseline year {base_year}; update targets first")
    snap = {**built["snapshot"], "basis": "Approved", "setAt": to_display(utcnow()), "setBy": user["name"]}
    doc["baseline"] = snap
    _save(db, doc)
    audit(db, user, "Saved", "emission-baseline",
          f"Baseline set to {start}…{end} ({snap['months']} months, {snap['recordCount']} approved records): "
          f"{snap['total']:,.2f} tCO₂e (annualised {snap['annualTotal']:,.2f}).")
    return get_targets(db)


def set_targets(db: Database, user: Mapping[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    doc = _doc(db)
    base = doc.get("baseline")
    if not base:
        raise conflict("Set a baseline before defining targets")
    for t in targets:
        if t["targetYear"] <= int(base["end"][:4]):
            raise unprocessable(f"{t['scope']} target year must be after the baseline year {base['end'][:4]}")
    doc["targets"] = [{"scope": t["scope"], "reductionPct": float(t["reductionPct"]), "targetYear": int(t["targetYear"])} for t in targets]
    _save(db, doc)
    audit(db, user, "Saved", "emission-targets",
          "Targets: " + ("; ".join(f"{t['scope']} −{t['reductionPct']:g}% by {t['targetYear']}" for t in doc["targets"]) or "none") + ".")
    return get_targets(db)
