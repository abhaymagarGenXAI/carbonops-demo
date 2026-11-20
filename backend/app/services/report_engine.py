"""GHG inventory report maths — pure functions, no I/O.

Rules (printed in every report):
* Records count by *basis*: "approved" = Approved only (the reportable inventory); "pending" adds records still awaiting a
  decision. Rejected and draft records never count.
* Totals are exact sums of the stored record values (Decimal, 2 dp) — every figure traces to calculation records.
* A month is *complete* when every facility has approved records for it; incomplete months inside the period are flagged.
* Scope 1/2 come from approved activity submissions; Scope 3 comes from approved Scope 3 entries and covers only the categories entered.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Mapping, Sequence

from app.services import targets_engine as te

BASES = {"approved": ("Approved",), "pending": ("Approved", "Under Review", "Submitted")}
SCOPE_KEYS = {"Scope 1": "scope1", "Scope 2": "scope2", "Scope 3": "scope3"}


def d(x: Any) -> Decimal:
    return Decimal(str(x or 0))


def q(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def select(records: Iterable[Mapping[str, Any]], basis: str, month_from: str | None, month_to: str | None,
           facility_id: str | None) -> list[dict[str, Any]]:
    ok = BASES[basis]
    return [dict(r) for r in records
            if r["reviewStatus"] in ok and (not month_from or r["month"] >= month_from) and (not month_to or r["month"] <= month_to)
            and (not facility_id or r["facilityId"] == facility_id)]


def summarise(chosen: Sequence[Mapping[str, Any]], all_records: Sequence[Mapping[str, Any]], facilities: Sequence[Mapping[str, Any]],
              factors: Mapping[str, Mapping[str, Any]], month_from: str | None, month_to: str | None, facility_id: str | None,
              scope3_left_out: Mapping[str, int] | None = None) -> dict[str, Any]:
    """`chosen` may mix emission records and Scope 3 entries (as records); `all_records` is Scope 1/2 only (month coverage)."""
    names = {f["id"]: f["name"] for f in facilities} | {"CORP": "Corporate / not facility-specific"}
    tot: dict[str, Decimal] = defaultdict(Decimal)
    by_src: dict[tuple[str, str, str], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    by_fac: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    by_mon: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    used: dict[str, int] = defaultdict(int)
    traced = 0
    for r in chosen:
        v, k = d(r["co2e"]), SCOPE_KEYS.get(r["scope"], "scope3")
        tot[k] += v
        tot["total"] += v
        s = by_src[(r["source"], r["scope"], r["unit"])]
        s[0] += d(r["activityValue"])
        s[1] += v
        for acc, key in ((by_fac, r["facilityId"]), (by_mon, r["month"])):
            acc[key][k] += v
            acc[key]["total"] += v
        if r.get("factorId"):
            used[r["factorId"]] += 1
        if r.get("formula") and (r.get("submissionId") or r.get("entryId")):
            traced += 1
    total = tot["total"]

    # coverage: which months in the period are fully approved, and what was left out
    fac_ids = [f["id"] for f in facilities if not facility_id or f["id"] == facility_id]
    agg = te.aggregate(r for r in all_records if not facility_id or r["facilityId"] == facility_id)
    in_range = sorted(m for m in {r["month"] for r in all_records} if (not month_from or m >= month_from) and (not month_to or m <= month_to))
    complete = set(te.complete_months(agg, fac_ids))
    left_out = defaultdict(int)
    for r in all_records:
        if (not month_from or r["month"] >= month_from) and (not month_to or r["month"] <= month_to) and (not facility_id or r["facilityId"] == facility_id):
            if r["reviewStatus"] not in ("Approved",):
                left_out[r["reviewStatus"]] += 1
    for k, n in (scope3_left_out or {}).items():
        left_out[k] += n

    return {
        "totals": {k: q(tot[k]) for k in ("scope1", "scope2", "scope3", "total")},
        "bySource": sorted(({"source": s, "scope": sc, "unit": u, "activity": float(a), "co2e": q(c),
                             "sharePct": round(float(c / total * 100), 1) if total else 0.0} for (s, sc, u), (a, c) in by_src.items()),
                           key=lambda x: (-x["co2e"], x["source"])),
        "byFacility": sorted(({"facilityId": f, "facility": names.get(f, f), **{k: q(v.get(k, Decimal(0))) for k in ("scope1", "scope2", "scope3", "total")}}
                              for f, v in by_fac.items()), key=lambda x: x["facilityId"]),
        "byMonth": sorted(({"month": m, **{k: q(v.get(k, Decimal(0))) for k in ("scope1", "scope2", "scope3", "total")}} for m, v in by_mon.items()),
                          key=lambda x: x["month"]),
        "factorsUsed": sorted(({"factorId": fid, "records": n, **{k: factors[fid].get(k) for k in ("source", "scope", "value", "unit", "reference", "validFrom")}}
                               for fid, n in used.items() if fid in factors), key=lambda x: (x["scope"], x["source"], x["validFrom"])),
        "coverage": {
            "monthsInPeriod": in_range, "incompleteMonths": [m for m in in_range if m not in complete],
            "leftOut": dict(left_out), "recordCount": len(chosen),
            "tracedRecords": traced, "legacyUntraced": len(chosen) - traced,
        },
    }


def warnings(summary: Mapping[str, Any], basis: str) -> list[str]:
    cov, out = summary["coverage"], []
    if cov["recordCount"] == 0:
        out.append("No records match the selected period, facility and basis.")
    if basis == "approved" and cov["incompleteMonths"]:
        out.append("Months not fully approved for every facility (inventory may be understated): " + ", ".join(cov["incompleteMonths"]) + ".")
    if cov["leftOut"]:
        out.append("Excluded from the totals — " + ", ".join(f"{n} {k.lower()} record(s)" for k, n in sorted(cov["leftOut"].items())) + ".")
    if basis == "pending":
        out.append("Basis includes records still awaiting approval — not a final inventory.")
    if cov["legacyUntraced"]:
        out.append(f"{cov['legacyUntraced']} record(s) have no stored calculation trace (legacy data); run Recalculate in Carbon Accounting to link them.")
    if summary["totals"]["scope3"] == 0:
        out.append("No approved Scope 3 entries in this selection; Scope 3 is not included.")
    else:
        out.append("Scope 3 covers only the categories that were entered and approved — it is a partial value chain figure, not a full Scope 3 inventory.")
    return out


METHOD = [
    "Method: activity data (approved submissions) × emission factor = tCO2e, per source and facility-month (GHG Protocol corporate standard).",
    "Scope 3 entries use spend- or activity-based factors (activity x factor); categories with no entries are not estimated.",
    "Scope 2 is location-based, using the grid factor version effective for each period.",
    "Each factor version is listed with its reference and validity date; each record names the factor version it used.",
    "Totals are exact sums of the calculation records shown in the Calculation trace; nothing is estimated or typed in.",
]
