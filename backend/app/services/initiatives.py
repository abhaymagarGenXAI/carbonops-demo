from __future__ import annotations

from typing import Any, Mapping

from pymongo.errors import DuplicateKeyError
from pymongo.database import Database

from app.repositories.facility import FacilityRepository
from app.repositories.initiative import InitiativeRepository
from app.schemas.initiative import AdvanceRequest, InitiativeCreate, InitiativeUpdate
from app.services import initiative_assumptions, rules, targets_engine as te
from app.services import initiatives_engine as ie
from app.repositories.emission import EmissionRecordRepository
from app.services import facilities as facilities_svc
from app.services.common import audit, not_found, unprocessable


def create_initiative(db: Database, user: Mapping[str, Any], p: InitiativeCreate) -> dict[str, Any]:
    if not FacilityRepository(db).exists(p.facility_id):
        raise not_found("Facility", p.facility_id)
    facilities_svc.assert_active(db, p.facility_id)
    repo = InitiativeRepository(db)
    base = {
        "name": p.name.strip(),
        "type": p.type,
        "owner": p.owner.strip() or "Unassigned",
        "facilityId": p.facility_id,
        "status": "Planned",
        "expectedReduction": p.expected_reduction,
        "actualReduction": 0,
        "investment": p.investment,
        "annualSavings": p.annual_savings,
        "roi": 0,
        "completion": 0,
        "startDate": p.start_date,
        "endDate": p.end_date,
        "timeline": "On Track",
        "priority": p.priority,
        "dependencies": "—",
        "notes": p.notes.strip(),
        "milestones": rules.default_milestones(p.start_date, p.end_date),
    }
    for _ in range(5):  # id is max+1; retry if a concurrent request took it
        try:
            out = repo.create({**base, "id": repo.next_id()})
            break
        except DuplicateKeyError:
            continue
    else:  # pragma: no cover
        raise unprocessable("Could not allocate an initiative id, please retry")
    audit(db, user, "Saved", out["id"], f'Initiative "{out["name"]}" created.')
    return out


def update_initiative(db: Database, user: Mapping[str, Any], id_: str, p: InitiativeUpdate) -> dict[str, Any]:
    repo = InitiativeRepository(db)
    changes = p.model_dump(by_alias=True, exclude_none=True)
    if "facilityId" in changes and not FacilityRepository(db).exists(changes["facilityId"]):
        raise not_found("Facility", changes["facilityId"])
    if not changes:
        existing = repo.get(id_)
        if existing is None:
            raise not_found("Initiative", id_)
        return existing
    existing = repo.get(id_)
    if existing is None:
        raise not_found("Initiative", id_)
    if "milestones" in changes and "completion" not in changes:
        # the milestone checklist drives completion/status — progress is evidence-based, not a button
        changes.update(ie.derive_progress(changes["milestones"], changes.get("status", existing["status"])))
    out = repo.update(id_, changes)
    if out is None:
        raise not_found("Initiative", id_)
    audit(db, user, "Saved", id_, f'Initiative "{out["name"]}" updated ({", ".join(sorted(changes)) or "no changes"}).')
    return out


def advance_initiative(db: Database, user: Mapping[str, Any], id_: str, req: AdvanceRequest) -> dict[str, Any]:
    repo = InitiativeRepository(db)
    cur = repo.get(id_)
    if cur is None:
        raise not_found("Initiative", id_)
    changes = rules.advance_initiative(
        expected_reduction=cur["expectedReduction"], completion=cur["completion"], timeline=cur["timeline"], step=req.step
    )
    out = repo.update(id_, changes)
    assert out is not None
    audit(db, user, "Saved", id_, f'Initiative "{out["name"]}" progress set to {changes["completion"]:.0f}%.')
    return out


def enrich(row: Mapping[str, Any], assumptions: Mapping[str, Any]) -> dict[str, Any]:
    """Derived figures are computed on read from the current assumptions, so they can never go stale."""
    return {**row, **ie.economics(row, assumptions)}


def list_enriched(db: Database, filters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    a = initiative_assumptions.load(db)
    return [enrich(r, a) for r in InitiativeRepository(db).list(dict(filters or {}))]


def analysis(db: Database) -> dict[str, Any]:
    from app.services import targets as targets_svc

    a = initiative_assumptions.load(db)
    items = InitiativeRepository(db).list({})
    view = targets_svc.get_targets(db)
    total_prog = next((p for p in view["progress"] if p["scope"] == "Total"), None)
    base = view["baseline"]

    measured: list[dict[str, Any]] = []
    if base and base.get("byFacility"):
        agg = te.aggregate(EmissionRecordRepository(db).list())
        fac_ids = [f["id"] for f in facilities_svc.active_facilities(db)]  # completeness is judged on the current boundary
        after = [m for m in te.complete_months(agg, fac_ids) if m > base["end"]]
        for fid in sorted({i["facilityId"] for i in items}):
            mine = [i for i in items if i["facilityId"] == fid]
            base_m = base["byFacility"].get(fid, 0.0) / base["months"]
            row: dict[str, Any] = {
                "facilityId": fid, "initiativeIds": [i["id"] for i in mine],
                "plannedAnnual": round(sum(float(i["expectedReduction"]) for i in mine), 2),
                "verifiedAnnual": round(sum(float(i["actualReduction"]) for i in mine), 2),
                "baselineMonthly": round(base_m, 2), "monthsEvaluated": len(after),
                "actualMonthly": None, "measuredAnnualReduction": None,
            }
            if after:
                actual_m = sum(agg[m]["byFacility"].get(fid, 0.0) for m in after) / len(after)
                row["actualMonthly"] = round(actual_m, 2)
                row["measuredAnnualReduction"] = round((base_m - actual_m) * 12, 2)
            measured.append(row)
    return {
        "assumptions": a,
        "portfolio": {
            "count": len(items), "expected": round(sum(float(i["expectedReduction"]) for i in items), 2),
            "verified": round(sum(float(i["actualReduction"]) for i in items), 2),
            "investment": round(sum(float(i["investment"]) for i in items), 2),
        },
        "macc": ie.macc_curve(items, a),
        "targetCoverage": ie.target_coverage(items, total_prog),
        "facilityMeasured": measured,
        "baselineSet": base is not None,
    }
