"""Initiative economics & progress — pure functions. Every figure follows from the editable assumptions.

* annualised cost   = investment x capital-recovery factor(discount rate, lifetime)
* net annual cost   = annualised cost - annual savings (energy/fuel savings the project is expected to bring)
* marginal abatement cost (MACC) = net annual cost / expected annual reduction   [₹ per tCO2e; negative = pays for itself]
* annual benefit    = expected reduction x carbon value + annual savings
* ROI %             = annual benefit / investment x 100;  payback = investment / annual benefit
* completion        = share of milestones done (when milestones exist)
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

DEFAULTS = {"carbonValuePerTonne": 2200.0, "discountRatePct": 8.0, "lifetimeYears": 10}
OPEN_STATUSES = ("Planned", "In Progress")  # still to deliver (On Hold is excluded from the pipeline)


def crf(rate_pct: float, years: int) -> float:
    r = rate_pct / 100
    return 1 / years if r == 0 else r * (1 + r) ** years / ((1 + r) ** years - 1)


def economics(i: Mapping[str, Any], a: Mapping[str, Any]) -> dict[str, Any]:
    inv, red, sav = float(i["investment"]), float(i["expectedReduction"]), float(i.get("annualSavings", 0) or 0)
    annual_cost = inv * crf(a["discountRatePct"], int(a["lifetimeYears"]))
    benefit = red * a["carbonValuePerTonne"] + sav
    return {
        "annualCost": round(annual_cost, 2),
        "maccCost": round((annual_cost - sav) / red, 2) if red > 0 else None,
        "roi": round(benefit / max(inv, 1) * 100, 1),
        "paybackYears": round(inv / benefit, 1) if benefit > 0 and inv > 0 else None,
    }


def derive_progress(milestones: Sequence[Mapping[str, Any]], status: str) -> dict[str, Any]:
    """Completion/status/timeline implied by the milestone checklist (empty dict if there are no milestones)."""
    if not milestones:
        return {}
    done = sum(1 for m in milestones if m.get("done"))
    pct = round(done / len(milestones) * 100)
    out: dict[str, Any] = {"completion": float(pct)}
    if pct >= 100:
        out.update(status="Completed", timeline="Complete")
    elif status in ("Planned", "Completed") and done > 0:
        out["status"] = "In Progress"
        if status == "Completed":
            out["timeline"] = "On Track"
    return out


def macc_curve(items: Sequence[Mapping[str, Any]], a: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Open initiatives ordered by marginal abatement cost, with cumulative abatement (the classic MACC order)."""
    rows = []
    for i in items:
        if i["status"] not in OPEN_STATUSES:
            continue
        e = economics(i, a)
        if e["maccCost"] is None:
            continue
        rows.append({"id": i["id"], "name": i["name"], "facilityId": i["facilityId"], "status": i["status"],
                     "expectedReduction": float(i["expectedReduction"]), "maccCost": e["maccCost"]})
    rows.sort(key=lambda r: (r["maccCost"], r["id"]))
    cum = 0.0
    for r in rows:
        cum += r["expectedReduction"]
        r["cumulativeReduction"] = round(cum, 2)
    return rows


def target_coverage(items: Sequence[Mapping[str, Any]], progress_row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """How much of the Total target's annual gap is delivered (measured/verified) or still in the pipeline."""
    if not progress_row:
        return None
    gap = float(progress_row["baselineAnnual"]) - float(progress_row["targetAnnual"])
    delivered = sum(float(i["actualReduction"]) for i in items)
    pipeline = sum(max(float(i["expectedReduction"]) - float(i["actualReduction"]), 0.0) for i in items if i["status"] in OPEN_STATUSES)
    held = sum(max(float(i["expectedReduction"]) - float(i["actualReduction"]), 0.0) for i in items if i["status"] == "On Hold")
    return {
        "targetYear": progress_row["targetYear"], "reductionPct": progress_row["reductionPct"], "gapAnnual": round(gap, 2),
        "delivered": round(delivered, 2), "pipeline": round(pipeline, 2), "onHold": round(held, 2),
        "coveragePct": round((delivered + pipeline) / gap * 100, 1) if gap > 0 else None,
        "uncovered": round(max(gap - delivered - pipeline, 0.0), 2),
    }
