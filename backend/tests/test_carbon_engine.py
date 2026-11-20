"""Pure unit tests for the carbon engine (no database / HTTP needed)."""
import json
from pathlib import Path

import pytest

from app.services import carbon_engine as ce

SEED = json.loads((Path(__file__).resolve().parent.parent / "app" / "seed" / "seed_data.json").read_text(encoding="utf-8"))
FACTORS = SEED["emissionFactors"]


def test_compute_co2e_kg_factor():
    assert ce.compute_co2e(174804, 2.68, "kgCO₂e/litre") == 468.47  # 468.47472 -> 2 dp
    assert ce.compute_co2e(7341701, 0.716, "kgCO₂e/kWh") == 5256.66  # 5256.6579


def test_compute_co2e_tonne_and_gram_numerators():
    assert ce.compute_co2e(1000, 0.5, "tCO₂e/kWh") == 500.0
    assert ce.compute_co2e(1_000_000, 2, "gCO₂e/kWh") == 2.0


def test_rounding_is_half_up_not_bankers():
    assert ce.compute_co2e(1, 5, "kgCO₂e/litre") == 0.01  # 0.005 -> 0.01


@pytest.mark.parametrize(
    "source,scope,unit",
    [
        ("Purchased Electricity", "Scope 2", "kgCO₂e/litre"),  # wrong activity unit
        ("Purchased Electricity", "Scope 1", "kgCO₂e/kWh"),  # wrong scope
        ("Diesel Combustion", "Scope 1", "2.68"),  # no denominator
        ("Diesel Combustion", "Scope 1", "kg/litre"),  # not a CO2e numerator
    ],
)
def test_validate_factor_rejects_bad_definitions(source, scope, unit):
    with pytest.raises(ce.FactorError):
        ce.validate_factor(source, scope, unit)


def test_validate_factor_accepts_seed_factors_and_unmapped_scope3():
    for f in FACTORS:
        ce.validate_factor(f["source"], f["scope"], f["unit"])
    ce.validate_factor("Some New Scope 3 Source", "Scope 3", "kgCO₂e/pax-km")


def test_select_factor_uses_version_effective_for_the_period():
    f, note = ce.select_factor(FACTORS, "Purchased Electricity", "2026-06")
    assert (f["id"], note) == ("EF-05", "")  # v19, valid from 2026-04-01
    f, note = ce.select_factor(FACTORS, "Purchased Electricity", "2025-12")
    assert (f["id"], note) == ("EF-07", "")  # superseded v18 still applies to its own period


def test_select_factor_fallback_is_reported_and_missing_is_none():
    f, note = ce.select_factor(FACTORS, "Diesel Combustion", "2026-01")
    assert f["id"] == "EF-01" and "No factor was effective" in note
    f, note = ce.select_factor(FACTORS, "Nope", "2026-01")
    assert f is None and "No emission factor" in note


def test_month_helpers_and_record_id():
    assert ce.prev_month("2026-01") == "2025-12" and ce.next_month("2026-12") == "2027-01"
    assert ce.record_id("MOF", "2026-07", 0) == "EM-MOF-202607-1"


def _build(sub, factors=FACTORS):
    code = {f["id"]: f["code"] for f in SEED["facilities"]}[sub["facilityId"]]
    return ce.build_records(
        facility_id=sub["facilityId"], facility_code=code, month=sub["month"], submission_id=sub["id"],
        submission_status=sub["status"], data=sub["data"], factors=factors,
    )


def test_missing_factor_is_a_problem_not_a_guess():
    sub = SEED["submissions"][0]
    records, problems = _build(sub, [f for f in FACTORS if f["source"] != "Flaring"])
    assert len(records) == 5 and len(problems) == 1 and problems[0].startswith("Flaring")


def test_every_seeded_record_is_reproduced():
    """The engine must reproduce the seed ledger: same ids, statuses, activity; numbers identical
    except where the seed used a newer grid factor than the one effective at the time."""
    seeded = {e["id"]: e for e in SEED["emissionRecords"]}
    differing = []
    for sub in SEED["submissions"]:
        records, problems = _build(sub)
        assert not problems
        assert len(records) == 6
        for r in records:
            old = seeded[r["id"]]
            assert (r["calcStatus"], r["reviewStatus"], r["scope"], r["source"], r["unit"]) == (
                old["calcStatus"], old["reviewStatus"], old["scope"], old["source"], old["unit"])
            assert r["activityValue"] == old["activityValue"]
            if ce.numerically_different(old, r):
                differing.append(r)
    # Seed Jan-Mar electricity used CEA v19 (valid from Apr 2026); by date, v18 applied. 4 facilities x 3 months.
    assert len(differing) == 12
    assert {r["source"] for r in differing} == {"Purchased Electricity"}
    assert {r["month"] for r in differing} == {"2026-01", "2026-02", "2026-03"}
