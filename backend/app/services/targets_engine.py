"""Baseline & target maths — pure functions, no I/O, every figure traceable to approved emission records.

Rules (also shown to users):
* Only **Approved** emission records count. A month is *complete* when every facility has approved records for it,
  so a half-approved month can never look like a reduction.
* The baseline is a frozen snapshot over a month range (1–12 months). Its monthly average is the flat reference level
  (annualised = total × 12 / months).
* A target is a % reduction of the baseline level, reached by December of the target year. The allowed level falls
  linearly month by month from the end of the baseline period:  allowed(m) = baseline_monthly × (1 − pct × progress),
  progress = months since baseline end / months from baseline end to December of the target year (capped at 1).
* Status compares cumulative actual vs cumulative allowed over the complete months after the baseline:
  On track (≤ 100 %), At risk (≤ 100 % + tolerance), Off track (above).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

SCOPES = ("Scope 1", "Scope 2")
TARGET_SCOPES = ("Total", "Scope 1", "Scope 2")
AT_RISK_TOLERANCE_PCT = 5.0


def month_index(m: str) -> int:
    return int(m[:4]) * 12 + int(m[5:7]) - 1


def month_str(i: int) -> str:
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def month_range(start: str, end: str) -> list[str]:
    return [month_str(i) for i in range(month_index(start), month_index(end) + 1)]


def aggregate(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Approved records -> {month: {"Scope 1": t, "Scope 2": t, "Total": t, "facilities": {ids}, "records": n}}."""
    out: dict[str, dict[str, Any]] = {}
    for r in records:
        if r.get("reviewStatus") != "Approved":
            continue
        m = out.setdefault(r["month"], {"Scope 1": 0.0, "Scope 2": 0.0, "Total": 0.0, "facilities": set(), "records": 0, "byFacility": {}})
        if r["scope"] in SCOPES:
            m[r["scope"]] += float(r["co2e"])
        m["Total"] += float(r["co2e"])
        m["facilities"].add(r["facilityId"])
        m["byFacility"][r["facilityId"]] = m["byFacility"].get(r["facilityId"], 0.0) + float(r["co2e"])
        m["records"] += 1
    return out


def complete_months(agg: Mapping[str, Mapping[str, Any]], facility_ids: Sequence[str]) -> list[str]:
    need = set(facility_ids)
    return sorted(m for m, v in agg.items() if need and need <= v["facilities"])


def build_baseline(agg: Mapping[str, Mapping[str, Any]], facility_ids: Sequence[str], start: str, end: str) -> dict[str, Any]:
    """Returns {"snapshot": {...} | None, "missing": [{"month", "facilityIds"}]}; snapshot only if coverage is complete."""
    months = month_range(start, end)
    need = set(facility_ids)
    missing = []
    for m in months:
        have = agg.get(m, {}).get("facilities", set())
        if need - have:
            missing.append({"month": m, "facilityIds": sorted(need - have)})
    if missing or not months:
        return {"snapshot": None, "missing": missing}
    tot = {k: round(sum(agg[m][k] for m in months), 2) for k in ("Scope 1", "Scope 2", "Total")}
    n = len(months)
    return {"snapshot": {
        "start": start, "end": end, "months": n, "facilities": len(need),
        "recordCount": sum(agg[m]["records"] for m in months),
        "scope1": tot["Scope 1"], "scope2": tot["Scope 2"], "total": tot["Total"],
        "annualScope1": round(tot["Scope 1"] * 12 / n, 2), "annualScope2": round(tot["Scope 2"] * 12 / n, 2),
        "annualTotal": round(tot["Total"] * 12 / n, 2),
        "byFacility": {f: round(sum(agg[m]["byFacility"].get(f, 0.0) for m in months), 2) for f in sorted(need)},
    }, "missing": []}


def _base_monthly(baseline: Mapping[str, Any], scope: str) -> float:
    key = {"Total": "total", "Scope 1": "scope1", "Scope 2": "scope2"}[scope]
    return float(baseline[key]) / baseline["months"]


def allowed_monthly(baseline: Mapping[str, Any], scope: str, reduction_pct: float, target_year: int, month: str) -> float:
    """Allowed tCO2e for `month` on the straight line from the baseline level to (1 − pct) in December of the target year."""
    start = month_index(baseline["end"])
    span = month_index(f"{target_year}-12") - start
    progress = 0.0 if span <= 0 else min(1.0, max(0.0, (month_index(month) - start) / span))
    return _base_monthly(baseline, scope) * (1 - reduction_pct / 100 * progress)


def progress(baseline: Mapping[str, Any], target: Mapping[str, Any], agg: Mapping[str, Mapping[str, Any]],
             complete: Sequence[str]) -> dict[str, Any]:
    scope, pct, year = target["scope"], float(target["reductionPct"]), int(target["targetYear"])
    after = [m for m in complete if m > baseline["end"]]
    cum_actual = sum(agg[m][scope] for m in after)
    cum_allowed = sum(allowed_monthly(baseline, scope, pct, year, m) for m in after)
    base_m = _base_monthly(baseline, scope)
    out: dict[str, Any] = {
        "scope": scope, "reductionPct": pct, "targetYear": year,
        "baselineAnnual": round(base_m * 12, 2), "targetAnnual": round(base_m * 12 * (1 - pct / 100), 2),
        "monthsEvaluated": len(after), "latestMonth": after[-1] if after else None,
        "cumulativeActual": round(cum_actual, 2), "cumulativeAllowed": round(cum_allowed, 2),
        "currentActual": None, "currentAllowed": None, "achievedReductionPct": None, "requiredReductionPct": None,
        "status": "No data yet",
    }
    if not after:
        return out
    last = after[-1]
    actual, allowed = agg[last][scope], allowed_monthly(baseline, scope, pct, year, last)
    out.update(
        currentActual=round(actual, 2), currentAllowed=round(allowed, 2),
        achievedReductionPct=round((1 - actual / base_m) * 100, 1) if base_m else None,
        requiredReductionPct=round((1 - allowed / base_m) * 100, 1) if base_m else None,
    )
    ratio = cum_actual / cum_allowed if cum_allowed else 1.0
    out["status"] = "On track" if ratio <= 1 else "At risk" if ratio <= 1 + AT_RISK_TOLERANCE_PCT / 100 else "Off track"
    return out


def series(baseline: Mapping[str, Any], targets: Sequence[Mapping[str, Any]], agg: Mapping[str, Mapping[str, Any]],
           complete: Sequence[str]) -> list[dict[str, Any]]:
    """Per complete month from the baseline start: actual per scope and the allowed level for each targeted scope."""
    rows = []
    for m in (x for x in complete if x >= baseline["start"]):
        row: dict[str, Any] = {"month": m, "phase": "baseline" if m <= baseline["end"] else "tracking",
                               "actual": {k: round(agg[m][k], 2) for k in ("Total", "Scope 1", "Scope 2")}, "allowed": {}}
        for t in targets:
            row["allowed"][t["scope"]] = round(
                _base_monthly(baseline, t["scope"]) if m <= baseline["end"]
                else allowed_monthly(baseline, t["scope"], float(t["reductionPct"]), int(t["targetYear"]), m), 2)
        rows.append(row)
    return rows
