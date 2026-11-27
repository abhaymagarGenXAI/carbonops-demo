"""Energy record derivation — pure functions, no I/O.

Quantities are NOT entered twice: each monthly submission is the single source of truth for the five
energy streams. Energy records add what a submission does not carry (meter, invoice, cost) and the
derived analytics: month-on-month variance, a validation status and energy content in GJ.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Submissions in these states carry no usable figures (unfinished or rejected) and are kept out of energy analytics.
EXCLUDED_STATUSES = ("Draft", "Rejected")
VARIANCE_BAND_PCT = 14.0  # |MoM variance| above this is an Anomaly (same band the UI documents)


@dataclass(frozen=True)
class Stream:
    name: str  # EnergyRecord.stream
    field: str  # key in the submission's activity data
    unit: str
    code: str  # 3-letter id segment
    gj_per_unit: float | None  # energy content; None => not counted in "energy consumed"


# gj_per_unit are the conversion values the UI already used (project defaults — confirm against your
# fuel certificates / national NCV table before external reporting). Steam depends on pressure, and
# on-site renewable generation is reported separately, so neither is added to consumed energy.
STREAMS: tuple[Stream, ...] = (
    Stream("Electricity", "electricity", "kWh", "ELE", 0.0036),
    Stream("Diesel", "diesel", "litres", "DIE", 0.0386),
    Stream("Natural Gas", "naturalGas", "SCM", "NAT", 0.0373),
    Stream("Steam", "steam", "tonnes", "STE", None),
    Stream("Renewable Energy", "renewable", "kWh", "REN", None),
)

# Derived fields: never writable through the API once a record is linked to a submission.
DERIVED_FIELDS = ("quantity", "unit", "variance", "validation")


def record_id(facility_code: str, stream: Stream, month: str) -> str:
    return f"EN-{facility_code}-{stream.code}-{month.replace('-', '')}"


def variance_pct(current: float, previous: float | None) -> float:
    if not previous:
        return 0.0
    return round((current - previous) / previous * 100, 1)


def classify(submission_status: str, quantity: float, previous: float | None, variance: float, band: float = VARIANCE_BAND_PCT) -> str:
    """Missing > Anomaly > Pending > Validated."""
    if quantity == 0 and previous:
        return "Missing"
    if abs(variance) > band:
        return "Anomaly"
    if submission_status != "Approved":
        return "Pending"  # not yet signed off (draft / submitted / under review / rejected)
    return "Validated"


def energy_gj(stream: Stream, quantity: float) -> float | None:
    return None if stream.gj_per_unit is None else round(quantity * stream.gj_per_unit, 2)


def derive_records(
    *, facility_id: str, facility_code: str, submission: Mapping[str, Any], prev_data: Mapping[str, Any] | None,
    band: float = VARIANCE_BAND_PCT,
) -> list[dict[str, Any]]:
    """The five derived fields-set of one facility-month (no meter/invoice/cost — those are user-owned)."""
    out = []
    for st in STREAMS:
        qty = float(submission["data"].get(st.field, 0) or 0)
        prev = float(prev_data.get(st.field, 0) or 0) if prev_data else None
        var = variance_pct(qty, prev)
        out.append({
            "id": record_id(facility_code, st, submission["month"]), "facilityId": facility_id,
            "month": submission["month"], "stream": st.name, "quantity": qty, "unit": st.unit,
            "variance": var, "validation": classify(submission["status"], qty, prev, var, band),
            "energyGj": energy_gj(st, qty), "submissionId": submission["id"],
            "excluded": submission["status"] in EXCLUDED_STATUSES, "submissionStatus": submission["status"],
        })
    return out
