"""Carbon calculation engine — pure functions, no I/O, no framework imports.

CO2e (tonnes) = activity value x emission factor, with the factor's numerator converted to tonnes.
Every emission record produced here stores the factor id/value/unit/reference that was used, so a
figure can always be traced back to its activity data and factor version.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

CO2E_DECIMALS = Decimal("0.01")


class FactorError(ValueError):
    """The emission factor cannot be applied (bad unit, wrong scope, ...)."""


@dataclass(frozen=True)
class EmissionSource:
    name: str  # must equal EmissionFactor.source and EmissionRecord.source
    scope: str
    field: str  # key in the submission's activity data
    unit: str  # display unit stored on the emission record
    per: frozenset[str]  # accepted factor denominators (normalised, see _norm)


# Order matters: it defines the record id suffix (EM-<code>-<YYYYMM>-<n>) used by the seed data.
SOURCES: tuple[EmissionSource, ...] = (
    EmissionSource("Diesel Combustion", "Scope 1", "diesel", "litres", frozenset({"litre", "litres", "l"})),
    EmissionSource("Natural Gas Combustion", "Scope 1", "naturalGas", "SCM", frozenset({"scm", "sm3"})),
    EmissionSource("Flaring", "Scope 1", "flareGas", "SCM", frozenset({"scm", "sm3"})),
    EmissionSource("Fugitive Methane", "Scope 1", "methaneLeak", "kg CH₄", frozenset({"kgch4"})),
    EmissionSource("Purchased Electricity", "Scope 2", "electricity", "kWh", frozenset({"kwh"})),
    EmissionSource("Imported Steam", "Scope 2", "steam", "tonnes", frozenset({"tonne", "tonnes", "t"})),
)
SOURCE_BY_NAME = {s.name: s for s in SOURCES}

# Submission status -> (calcStatus, reviewStatus). Mirrors how the seed data relates the two.
STATUS_MAP: dict[str, tuple[str, str]] = {
    "Draft": ("Pending", "Draft"),
    "Submitted": ("Calculated", "Under Review"),
    "Under Review": ("Calculated", "Under Review"),
    "Approved": ("Calculated", "Approved"),
    "Rejected": ("Recalculation Required", "Rejected"),
}

_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
# numerator -> multiplier that converts the factor value to tonnes CO2e
_NUMERATORS = {"kgco2e": Decimal("0.001"), "tco2e": Decimal("1"), "gco2e": Decimal("0.000001")}


def _norm(text: str) -> str:
    return text.translate(_SUBSCRIPTS).lower().replace(" ", "")


def split_unit(unit: str) -> tuple[str, str]:
    if "/" not in unit:
        raise FactorError(f"Factor unit '{unit}' must look like 'kgCO₂e/<activity unit>'")
    num, _, den = unit.partition("/")
    return _norm(num), _norm(den)


def multiplier(unit: str) -> Decimal:
    num, _ = split_unit(unit)
    if num not in _NUMERATORS:
        raise FactorError(f"Factor unit '{unit}' must start with kgCO₂e, tCO₂e or gCO₂e")
    return _NUMERATORS[num]


def validate_factor(source: str, scope: str, unit: str) -> None:
    """Raises FactorError if the factor definition could not be applied correctly."""
    multiplier(unit)
    spec = SOURCE_BY_NAME.get(source)
    if spec is None:
        return  # informational factor (e.g. Scope 3) that the engine does not apply yet
    if scope != spec.scope:
        raise FactorError(f"'{source}' is a {spec.scope} source, not {scope}")
    _, den = split_unit(unit)
    if den not in spec.per:
        raise FactorError(f"'{source}' activity is measured in {spec.unit}; factor unit '{unit}' does not match")


def month_start(month: str) -> str:
    return f"{month}-01"


def prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def next_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def record_id(facility_code: str, month: str, index: int) -> str:
    return f"EM-{facility_code}-{month.replace('-', '')}-{index + 1}"


def select_factor(factors: list[Mapping[str, Any]], source: str, month: str) -> tuple[Mapping[str, Any] | None, str]:
    """Factor effective at the start of `month`: the one with the latest validFrom <= that date.

    Superseded factors stay selectable for the periods they covered. If nothing was effective yet,
    the earliest known factor is used and the fallback is reported in the returned note.
    """
    candidates = [f for f in factors if f.get("source") == source]
    if not candidates:
        return None, f"No emission factor is defined for '{source}'"
    start = month_start(month)
    effective = [f for f in candidates if f["validFrom"] <= start]
    if effective:
        best = max(effective, key=lambda f: (f["validFrom"], f.get("status") == "Active", f["id"]))
        return best, ""
    best = min(candidates, key=lambda f: (f["validFrom"], f["id"]))
    return best, f"No factor was effective on {start}; earliest available factor ({best['id']}, valid from {best['validFrom']}) used"


def compute_co2e(activity: float, factor_value: float, factor_unit: str) -> float:
    """Tonnes CO2e, rounded half-up to 2 decimals."""
    tonnes = Decimal(str(activity)) * Decimal(str(factor_value)) * multiplier(factor_unit)
    return float(tonnes.quantize(CO2E_DECIMALS, rounding=ROUND_HALF_UP))


def formula_text(activity: float, unit: str, factor_value: float, factor_unit: str, co2e: float) -> str:
    div = " ÷ 1000" if multiplier(factor_unit) == Decimal("0.001") else ""
    return f"{activity:,.2f}".rstrip("0").rstrip(".") + f" {unit} × {factor_value} {factor_unit}{div} = {co2e:,.2f} tCO₂e"


def build_records(
    *, facility_id: str, facility_code: str, month: str, submission_id: str, submission_status: str,
    data: Mapping[str, Any], factors: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (records, problems). A source whose factor is missing/unusable is reported, not guessed."""
    calc_status, review_status = STATUS_MAP.get(submission_status, ("Pending", "Draft"))
    records: list[dict[str, Any]] = []
    problems: list[str] = []
    for idx, spec in enumerate(SOURCES):
        factor, note = select_factor(factors, spec.name, month)
        if factor is None:
            problems.append(f"{spec.name}: {note}")
            continue
        try:
            validate_factor(spec.name, factor["scope"], factor["unit"])
            activity = float(data.get(spec.field, 0) or 0)
            co2e = compute_co2e(activity, factor["value"], factor["unit"])
        except FactorError as exc:
            problems.append(f"{spec.name}: factor {factor['id']} — {exc}")
            continue
        records.append(
            {
                "id": record_id(facility_code, month, idx),
                "facilityId": facility_id,
                "month": month,
                "source": spec.name,
                "activityValue": activity,
                "unit": spec.unit,
                "factor": factor["value"],
                "factorUnit": factor["unit"],
                "factorRef": factor["reference"],
                "factorId": factor["id"],
                "scope": spec.scope,
                "co2e": co2e,
                "calcStatus": calc_status,
                "reviewStatus": review_status,
                "submissionId": submission_id,
                "formula": formula_text(activity, spec.unit, factor["value"], factor["unit"], co2e),
                "calcNote": note,
            }
        )
    return records, problems


def numerically_different(old: Mapping[str, Any], new: Mapping[str, Any], tol: float = 0.051) -> bool:
    """tol absorbs the 1-decimal rounding that legacy (seeded) records were stored with."""
    return (
        abs(float(old.get("activityValue", 0)) - new["activityValue"]) > 1e-9
        or abs(float(old.get("factor", 0)) - float(new["factor"])) > 1e-12
        or abs(float(old.get("co2e", 0)) - new["co2e"]) > tol
    )
