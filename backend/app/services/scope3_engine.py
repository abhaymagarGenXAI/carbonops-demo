"""Scope 3 calculation — pure functions, no I/O.

tCO2e = activity x factor (same maths and rounding as Scope 1/2, see carbon_engine). The activity unit is whatever the factor is
expressed per (e.g. kgCO2e/passenger-km -> passenger-km, kgCO2e/INR -> INR), so spend-based and activity-based methods share one path.
Only categories the organisation actually enters are included; the platform never estimates missing categories.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.services import carbon_engine as ce

# GHG Protocol Corporate Value Chain (Scope 3) Standard — the 15 categories.
CATEGORIES: tuple[str, ...] = (
    "1 Purchased goods and services", "2 Capital goods", "3 Fuel- and energy-related activities", "4 Upstream transportation and distribution",
    "5 Waste generated in operations", "6 Business travel", "7 Employee commuting", "8 Upstream leased assets",
    "9 Downstream transportation and distribution", "10 Processing of sold products", "11 Use of sold products",
    "12 End-of-life treatment of sold products", "13 Downstream leased assets", "14 Franchises", "15 Investments",
)
METHODS = {"spend": "Spend-based", "activity": "Activity-based"}


class Scope3Error(ValueError):
    pass


def factor_options(factors: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [f for f in factors if f.get("scope") == "Scope 3"]


def activity_unit(factor_unit: str) -> str:
    """'kgCO₂e/passenger-km' -> 'passenger-km' (original casing kept for display)."""
    ce.split_unit(factor_unit)
    return factor_unit.partition("/")[2].strip()


def method_of(unit: str) -> str:
    return METHODS["spend"] if ce._norm(unit) in {"inr", "₹", "usd", "eur", "rs", "lakhinr", "crinr"} else METHODS["activity"]


def calculate(*, month: str, category: str, source: str, activity: float, factors: Sequence[Mapping[str, Any]], source_id: str | None = None) -> dict[str, Any]:
    """Returns the calculated part of an entry. Raises Scope3Error when the factor cannot be applied — nothing is guessed."""
    if category not in CATEGORIES:
        raise Scope3Error(f"Unknown Scope 3 category '{category}'")
    options = factor_options(factors)
    factor, note = ce.select_factor(options, source, month, source_id)
    if factor is None:
        raise Scope3Error(f"No Scope 3 emission factor named '{source}' exists. Add one under Emission factors first.")
    if factor.get("category") and factor["category"] != category:
        raise Scope3Error(f"Factor {factor['id']} belongs to category '{factor['category']}', not '{category}'")
    try:
        unit = activity_unit(factor["unit"])
        co2e = ce.compute_co2e(activity, factor["value"], factor["unit"])
    except ce.FactorError as exc:
        raise Scope3Error(f"Factor {factor['id']} — {exc}") from exc
    return {
        "unit": unit, "method": method_of(unit), "factor": factor["value"], "factorUnit": factor["unit"],
        "factorRef": factor["reference"], "factorId": factor["id"], "factorVersionId": factor["id"], "emissionSourceId": factor.get("emissionSourceId") or source_id,
        "co2e": co2e, "calcNote": note,
        "formula": ce.formula_text(activity, unit, factor["value"], factor["unit"], co2e),
    }


def as_record(e: Mapping[str, Any]) -> dict[str, Any]:
    """Entry -> the record shape report_engine consumes (facility-less entries become 'CORP')."""
    return {
        "id": e["id"], "facilityId": e.get("facilityId") or "CORP", "month": e["month"], "source": f"{e['source']} (Cat {e['category']})",
        "scope": "Scope 3", "unit": e["unit"], "activityValue": e["activityValue"], "factor": e["factor"], "factorUnit": e["factorUnit"],
        "factorRef": e["factorRef"], "factorId": e["factorId"], "co2e": e["co2e"], "formula": e["formula"], "entryId": e["id"],
        "reviewStatus": e["status"] if e["status"] != "Submitted" else "Under Review", "submissionId": None, "calcStatus": "Calculated",
    }
