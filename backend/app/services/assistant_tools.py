"""The only way the assistant can see data: a fixed set of read-only tools over the app's own calculations.

Each tool returns JSON computed by the existing engines (inventory, targets, forecast, initiatives, alerts). The language model never
computes or invents figures — it selects a tool and words the result; answers are checked against the tool output afterwards.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from pymongo.database import Database

from app.repositories.asset import AssetRepository
from app.repositories.emission import EmissionRecordRepository
from app.repositories.emission_factor import EmissionFactorRepository
from app.repositories.energy import EnergyRecordRepository
from app.repositories.facility import FacilityRepository
from app.repositories.initiative import InitiativeRepository
from app.repositories.scope3 import Scope3Repository
from app.repositories.submission import SubmissionRepository
from app.services import alerts as alerts_svc
from app.services import forecast as forecast_svc
from app.services import initiatives as init_svc
from app.services import periods as periods_svc
from app.services import reports as reports_svc
from app.services import targets as targets_svc

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ToolError(ValueError):
    """Bad arguments from the model — returned to it as data so it can retry; never raised to the user."""


def _month(v: Any, name: str) -> str | None:
    if v in (None, "", "null"):
        return None
    if not isinstance(v, str) or not MONTH.match(v):
        raise ToolError(f"{name} must look like YYYY-MM")
    return v


def _facility(db: Database, v: Any) -> str | None:
    if v in (None, "", "null", "all"):
        return None
    fac = FacilityRepository(db).list()
    hit = next((f for f in fac if str(v).lower() in (f["id"].lower(), f["code"].lower(), f["name"].lower())), None)
    if hit is None:
        raise ToolError(f"Unknown facility '{v}'. Call list_facilities for valid ids.")
    return hit["id"]


def list_facilities(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    return {"facilities": [{"id": f["id"], "code": f["code"], "name": f["name"], "units": f["units"]} for f in FacilityRepository(db).list()]}


def get_emission_inventory(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    basis = a.get("basis") or "approved"
    if basis not in ("approved", "pending"):
        raise ToolError("basis must be 'approved' or 'pending'")
    rep = reports_svc.build(db, _month(a.get("from_month"), "from_month"), _month(a.get("to_month"), "to_month"), basis, _facility(db, a.get("facility_id")))
    s = rep["summary"]
    return {"unit": "tCO2e", "scope": rep["scope"], "totals": s["totals"], "byFacility": s["byFacility"], "byMonth": s["byMonth"],
            "bySource": s.get("bySource", [])[:12], "coverage": s.get("coverage"), "warnings": rep["warnings"], "method": "GHG inventory, Scope 3 = entered categories only"}


def get_target_progress(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    v = targets_svc.get_targets(db)
    base = v["baseline"]
    return {"unit": "tCO2e", "baseline": ({k: base[k] for k in ("start", "end", "months", "total", "scope1", "scope2") if k in base} if base else None),
            "targets": v["targets"], "progress": v["progress"], "completeThrough": v["completeThrough"], "incompleteMonths": v["incompleteMonths"],
            "note": "Progress counts only complete approved months (every facility approved). Scope 1+2 only."}


def get_emission_forecast(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    h = a.get("horizon", 12)
    if not isinstance(h, int) or isinstance(h, bool) or not 1 <= h <= 24:
        raise ToolError("horizon must be an integer 1-24 (months)")
    f = forecast_svc.build(db, h)
    total = f["scopes"].get("Total")
    return {"unit": "tCO2e per month", "available": f["available"], "usedMonths": f["usedMonths"], "warnings": f["warnings"], "method": f["method"],
            "fit": total["fit"] if total else None, "projectionTotal": total["projection"] if total else [], "outlookAgainstTargets": f["outlook"]}


def get_initiatives_overview(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    x = init_svc.analysis(db)
    return {"portfolio": x["portfolio"], "targetCoverage": x["targetCoverage"], "facilityMeasured": x["facilityMeasured"],
            "mostCostEffective": x["macc"][:8] if isinstance(x["macc"], list) else x["macc"], "baselineSet": x["baselineSet"],
            "assumptions": x["assumptions"], "unit": "tCO2e per year; costs in INR"}


def get_alerts(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    rows = alerts_svc.build_alerts(db, _month(a.get("period"), "period"))
    return {"count": len(rows), "alerts": [{"kind": r.get("kind"), "severity": r["severity"], "title": r["title"], "detail": r["detail"]} for r in rows[:25]]}


def get_reporting_periods(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    rows = periods_svc.list_periods(db)
    by: dict[str, list[str]] = {}
    for p in rows:
        by.setdefault(p["status"], []).append(p["period"])
    return {"periods": [{k: p.get(k) for k in ("period", "status", "submissionDue", "approvalDue", "lockedOn")} for p in rows], "periodsByStatus": by,
            "meaning": "Open = data entry allowed; In Review = managers approve; Locked = final"}


def get_submission_status(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    """Which facilities have (not) submitted activity data for a period, and the status of what exists."""
    period = _month(a.get("period"), "period")
    if not period:
        raise ToolError("period (YYYY-MM) is required; call get_reporting_periods to see valid periods")
    facs = FacilityRepository(db).list()
    subs = SubmissionRepository(db).list({"month": period})
    rows, counts = [], {"Approved": 0, "Under Review": 0, "Submitted": 0, "Rejected": 0, "Draft": 0, "Not submitted": 0}
    for f in facs:
        mine = [s for s in subs if s["facilityId"] == f["id"]]
        status = "Not submitted" if not mine else (mine[0]["status"] if len({s["status"] for s in mine}) == 1 else "Mixed: " + ", ".join(sorted({s["status"] for s in mine})))
        for s in (mine or [{"status": "Not submitted"}]):
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        rows.append({"facilityId": f["id"], "facility": f["name"], "status": status, "submissions": len(mine)})
    period_row = next((p for p in periods_svc.list_periods(db) if p["period"] == period), None)
    return {"period": period, "periodStatus": period_row["status"] if period_row else "Period does not exist", "facilityCount": len(facs),
            "byFacility": rows, "countsByStatus": {k: v for k, v in counts.items() if v},
            "notYetSubmitted": [r["facility"] for r in rows if r["status"] in ("Not submitted", "Draft")],
            "note": "'Not yet submitted' = facilities with no submission or only a Draft for the period"}


def get_energy_consumption(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    frm, to, fid = _month(a.get("from_month"), "from_month"), _month(a.get("to_month"), "to_month"), _facility(db, a.get("facility_id"))
    stream = a.get("stream")
    basis = a.get("basis") or "approved"
    if basis not in ("approved", "all"):
        raise ToolError("basis must be 'approved' or 'all'")
    names = {f["id"]: f["name"] for f in FacilityRepository(db).list()}
    ok = ("Approved", None) if basis == "approved" else ("Approved", "Submitted", "Under Review", None)
    recs = [r for r in EnergyRecordRepository(db).list() if not r.get("excluded") and r.get("submissionStatus") in ok
            and (not frm or r["month"] >= frm) and (not to or r["month"] <= to) and (not fid or r["facilityId"] == fid)
            and (not stream or r["stream"].lower() == str(stream).lower())]
    month_stream: dict[tuple[str, str, str], dict[str, float]] = {}
    fac_rows: dict[tuple[str, str, str, str], float] = {}
    for r in recs:
        m = month_stream.setdefault((r["month"], r["stream"], r["unit"]), {"quantity": 0.0, "energyGj": 0.0, "cost": 0.0})
        m["quantity"] += r["quantity"]; m["energyGj"] += r.get("energyGj") or 0.0; m["cost"] += r.get("cost") or 0.0
        k = (r["month"], r["facilityId"], r["stream"], r["unit"])
        fac_rows[k] = fac_rows.get(k, 0.0) + r["quantity"]
    by_ms = [{"month": k[0], "stream": k[1], "unit": k[2], "quantity": round(v["quantity"], 2), "energyGj": round(v["energyGj"], 2), "costInr": round(v["cost"], 2)}
             for k, v in sorted(month_stream.items())]
    peak: dict[str, Any] = {}
    for row in by_ms:
        if row["stream"] not in peak or row["quantity"] > peak[row["stream"]]["quantity"]:
            peak[row["stream"]] = {"month": row["month"], "quantity": row["quantity"], "unit": row["unit"]}
    peak_months = {p["month"] for p in peak.values()}
    by_fac = [{"month": k[0], "facilityId": k[1], "facility": names.get(k[1], k[1]), "stream": k[2], "quantity": round(v, 2), "unit": k[3]}
              for k, v in sorted(fac_rows.items()) if k[0] in peak_months or (frm and frm == to)]
    return {"basis": "Approved records (plus legacy records without a submission)" if basis == "approved" else "All non-rejected records",
            "recordCount": len(recs), "byMonthAndStream": by_ms, "peakMonthPerStream": peak, "byFacilityInPeakMonths": by_fac[:150],
            "note": "Facility rows are given for each stream's peak month (or the single month requested). Use from_month=to_month for another month."}


def get_emission_factors(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    rows = EmissionFactorRepository(db).list()
    sc, src = a.get("scope"), (a.get("source") or "").lower()
    rows = [f for f in rows if (not sc or f["scope"] == sc) and (not src or src in f["source"].lower())]
    return {"count": len(rows), "factors": [{k: f.get(k) for k in ("id", "source", "scope", "value", "unit", "validFrom", "status", "reference", "category")} for f in rows]}


# Generic, read-only, whitelisted aggregation — the model chooses *what* to count; the numbers are always computed here, never by the model.
_COLLECTIONS: dict[str, tuple[Any, tuple[str, ...], tuple[str, ...]]] = {
    "assets": (AssetRepository, ("facilityId", "unit", "type", "status", "energySource", "carbonCategory", "emissionSourceType", "engineer", "lastInspection", "name", "id"), ()),
    "submissions": (SubmissionRepository, ("facilityId", "unit", "month", "status", "submittedBy", "reviewer", "validation", "id"), ("completeness",)),
    "energy_records": (EnergyRecordRepository, ("facilityId", "month", "stream", "unit", "validation", "submissionStatus", "id"), ("quantity", "cost", "energyGj", "variance")),
    "emission_records": (EmissionRecordRepository, ("facilityId", "month", "source", "scope", "reviewStatus", "calcStatus", "id"), ("co2e", "activityValue")),
    "initiatives": (InitiativeRepository, ("facilityId", "status", "type", "owner", "id", "name"), ("expectedReduction", "actualReduction", "investment", "completion")),
    "scope3_entries": (Scope3Repository, ("month", "category", "status", "facilityId", "source", "id"), ("co2e", "activityValue")),
    "facilities": (FacilityRepository, ("region", "type", "manager", "code", "id", "name"), ()),
}


def query_data(db: Database, a: dict[str, Any]) -> dict[str, Any]:
    name = a.get("collection")
    if name not in _COLLECTIONS:
        raise ToolError(f"collection must be one of: {', '.join(_COLLECTIONS)}")
    repo, fields, numeric = _COLLECTIONS[name]
    filters = a.get("filters") or {}
    if not isinstance(filters, dict):
        raise ToolError('filters must be an object like {"status": "Approved", "month": "2026-07"}')
    bad = [k for k in filters if k not in fields + numeric]
    if bad:
        raise ToolError(f"cannot filter on {bad}; allowed fields: {', '.join(fields + numeric)}")
    rows = [r for r in repo(db).list() if all(str(r.get(k)).lower() == str(v).lower() for k, v in filters.items())]
    group_by, agg, fld = a.get("group_by"), a.get("aggregate") or "count", a.get("field")
    if group_by and group_by not in fields:
        raise ToolError(f"cannot group by '{group_by}'; allowed: {', '.join(fields)}")
    if agg not in ("count", "sum", "avg", "min", "max"):
        raise ToolError("aggregate must be count, sum, avg, min or max")
    if agg != "count" and fld not in numeric:
        raise ToolError(f"aggregate '{agg}' needs field to be one of: {', '.join(numeric) or '(none for this collection)'}")

    def metric(items: list[dict[str, Any]]) -> float | int:
        if agg == "count":
            return len(items)
        vals = [float(i[fld]) for i in items if i.get(fld) is not None]
        if not vals:
            return 0
        return round({"sum": sum(vals), "avg": sum(vals) / len(vals), "min": min(vals), "max": max(vals)}[agg], 2)

    out: dict[str, Any] = {"collection": name, "filters": filters, "matched": len(rows), "aggregate": agg, "field": fld if agg != "count" else None}
    if group_by:
        groups: dict[Any, list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(r.get(group_by), []).append(r)
        out["groupBy"] = group_by
        out["groups"] = sorted(({"key": k, "count": len(v), "value": metric(v)} for k, v in groups.items()), key=lambda g: -float(g["value"] or 0))[:60]
    else:
        out["value"] = metric(rows)
        out["rows"] = [{k: r.get(k) for k in fields + numeric if k in r} for r in rows[:25]]
    return out


_MONTH_P = {"type": "string", "description": "Month as YYYY-MM"}
TOOLS: dict[str, tuple[str, dict[str, Any], Callable[[Database, dict[str, Any]], dict[str, Any]]]] = {
    "list_facilities": ("List facilities with their ids, codes and production units.", {}, list_facilities),
    "get_emission_inventory": (
        "GHG emissions inventory in tCO2e: totals for Scope 1, 2, 3 and overall, plus breakdown by facility, month and source. Use for any question "
        "about how much was emitted, which facility/source/month is highest, or comparisons between periods.",
        {"from_month": _MONTH_P, "to_month": _MONTH_P, "facility_id": {"type": "string", "description": "Facility id, code or name; omit for all"},
         "basis": {"type": "string", "enum": ["approved", "pending"], "description": "approved = default; pending also counts records awaiting approval"}},
        get_emission_inventory),
    "get_target_progress": ("Emission reduction targets and baseline: status (On track / At risk / Off track), cumulative actual vs allowed.", {}, get_target_progress),
    "get_emission_forecast": (
        "Statistical trend forecast of monthly emissions (least-squares line with prediction band) and whether targets are projected to be met.",
        {"horizon": {"type": "integer", "description": "Months ahead, 1-24 (default 12)"}}, get_emission_forecast),
    "get_initiatives_overview": ("Decarbonisation initiatives: portfolio totals, cost-effectiveness (MACC), coverage of the target gap, measured vs planned reductions.", {}, get_initiatives_overview),
    "get_alerts": ("Current data-quality, deadline and approval alerts (overdue asset inspections, anomalies, rework). NOT for submission status.", {"period": _MONTH_P}, get_alerts),
    "get_reporting_periods": ("All reporting periods with status Open / In Review / Locked and due dates. Call this first whenever the user asks about periods or does not name one.", {}, get_reporting_periods),
    "get_submission_status": (
        "For one reporting period: which facilities have not yet submitted activity data, and the status (Approved, Under Review, Submitted, Rejected, Draft) of those that have.",
        {"period": _MONTH_P}, get_submission_status),
    "get_energy_consumption": (
        "Energy consumption (electricity kWh, diesel, natural gas, steam, ...) by month, stream and facility, with the peak month per stream. Use for 'which month consumed the most electricity' "
        "and facility-wise consumption.",
        {"from_month": _MONTH_P, "to_month": _MONTH_P, "facility_id": {"type": "string"}, "stream": {"type": "string", "description": "e.g. Electricity, Diesel, Natural Gas, Steam"},
         "basis": {"type": "string", "enum": ["approved", "all"]}}, get_energy_consumption),
    "get_emission_factors": ("Emission factor register: value, unit, scope, reference, valid-from date and status.",
                             {"scope": {"type": "string", "enum": ["Scope 1", "Scope 2", "Scope 3"]}, "source": {"type": "string", "description": "Name contains"}}, get_emission_factors),
    "query_data": (
        "Generic counting/summing over the platform's records when no specific tool fits. collection: assets | submissions | energy_records | emission_records | initiatives | scope3_entries | facilities. "
        "filters: exact-match field values; group_by: one field; aggregate: count|sum|avg|min|max (sum/avg/min/max need a numeric field). "
        "Examples: submissions {month:'2026-07', status:'Submitted'} count; assets group_by status; energy_records filters {stream:'Electricity'} group_by month sum quantity.",
        {"collection": {"type": "string", "enum": list(_COLLECTIONS)}, "filters": {"type": "object"}, "group_by": {"type": "string"},
         "aggregate": {"type": "string", "enum": ["count", "sum", "avg", "min", "max"]}, "field": {"type": "string"}}, query_data),
}


def specs() -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": {"type": "object", "properties": p, "required": []}}}
            for n, (d, p, _) in TOOLS.items()]


def run(db: Database, name: str, args: Any) -> dict[str, Any]:
    if name not in TOOLS:
        return {"error": f"Unknown tool '{name}'. Available: {', '.join(TOOLS)}"}
    if not isinstance(args, dict):
        args = {}
    allowed = set(TOOLS[name][1])
    try:
        return TOOLS[name][2](db, {k: v for k, v in args.items() if k in allowed})
    except ToolError as exc:
        return {"error": str(exc)}
