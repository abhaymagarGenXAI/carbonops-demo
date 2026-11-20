"""API-level tests for carbon accounting (need the full dependency set: fastapi, mongomock)."""
from decimal import ROUND_HALF_UP, Decimal

from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, open_periods

API = "/api/v1"
DATA = dict(productionVolume=100000, electricity=1_000_000, diesel=100_000, naturalGas=2_000_000, steam=50_000,
            water=6, flareGas=100_000, methaneLeak=400, renewable=9, operatingHours=700, remarks="", notes="")


def t(x):  # expected tCO2e, half-up 2dp
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def save(client, headers, status="Submitted", month="2026-08", data=DATA):
    open_periods(client, month)
    return client.post(f"{API}/submissions", headers=headers,
                       json={"facilityId": "FAC-001", "unit": "Bombay High North", "month": month, "status": status, "data": data})


def records(client, headers, month="2026-08"):
    r = client.get(f"{API}/emission-records", headers=headers, params={"facility_id": "FAC-001", "month": month})
    assert r.status_code == 200
    return {x["source"]: x for x in r.json()}


def test_submission_generates_traceable_emission_records(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert save(client, eng).status_code == 200
    recs = records(client, eng)
    assert len(recs) == 6
    el = recs["Purchased Electricity"]
    assert el["co2e"] == t(1_000_000 * 0.716 / 1000) and el["factorId"] == "EF-05" and el["submissionId"] == "SUB-MOF-202608"
    assert "tCO₂e" in el["formula"] and (el["calcStatus"], el["reviewStatus"]) == ("Calculated", "Under Review")
    assert recs["Fugitive Methane"]["co2e"] == t(400 * 28 / 1000)
    assert recs["Diesel Combustion"]["prevCo2e"] == 448.2  # linked to the seeded July record

    # approval -> Approved; re-save while locked is refused; rejection -> Recalculation Required
    sid = "SUB-MOF-202608"
    client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Approved", "comment": "ok"})
    assert records(client, eng)["Flaring"]["reviewStatus"] == "Approved"
    # an approved submission is final: it cannot be flipped to Rejected afterwards
    late = client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Rejected", "comment": "too late"})
    assert late.status_code == 409 and "final" in late.json()["detail"]
    assert records(client, eng)["Flaring"]["reviewStatus"] == "Approved"
    # rejection of a pending submission -> Recalculation Required
    save(client, eng, "Submitted", month="2026-09")
    client.post(f"{API}/submissions/SUB-MOF-202609/review", headers=mgr, json={"status": "Rejected", "comment": "bad meter"})
    rej = {r["source"]: r for r in client.get(f"{API}/emission-records", headers=eng, params={"facility_id": "FAC-001", "month": "2026-09"}).json()}["Flaring"]
    assert (rej["calcStatus"], rej["reviewStatus"]) == ("Recalculation Required", "Rejected")


def test_resubmitting_updates_in_place_and_keeps_comments(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    save(client, eng, "Draft")
    assert {r["calcStatus"] for r in records(client, eng).values()} == {"Pending"}
    r = client.post(f"{API}/emission-records/EM-MOF-202608-1/review", headers=mgr, json={"status": "Under Review", "comment": "check"})
    assert r.status_code == 409  # a draft submission is not awaiting review
    save(client, eng, "Submitted", data={**DATA, "diesel": 200_000})
    recs = records(client, eng)
    assert len(recs) == 6 and recs["Diesel Combustion"]["co2e"] == t(200_000 * 2.68 / 1000)


def test_next_months_previous_value_is_relinked(client):
    eng = auth_headers(client, ENGINEER)
    save(client, eng, status="Draft", month="2026-08")  # a submitted record is read-only until the reviewer reopens it
    save(client, eng, month="2026-09")
    aug = records(client, eng, "2026-08")["Diesel Combustion"]["co2e"]
    assert records(client, eng, "2026-09")["Diesel Combustion"]["prevCo2e"] == aug
    save(client, eng, month="2026-08", data={**DATA, "diesel": 50_000})
    assert records(client, eng, "2026-09")["Diesel Combustion"]["prevCo2e"] == t(50_000 * 2.68 / 1000)


def test_recalculate_dry_run_apply_and_permissions(client):
    eng, mgr, adm = (auth_headers(client, e) for e in (ENGINEER, MANAGER, ADMIN))
    assert client.post(f"{API}/emission-records/recalculate", headers=eng, json={}).status_code == 403

    r = client.post(f"{API}/emission-records/recalculate", headers=mgr, json={}).json()
    assert r["dryRun"] is True and r["updated"] == 0 and r["created"] == 0  # seed ledger is already consistent
    assert any("2026-01 is locked" in s["reason"] for s in r["skipped"])  # locked periods untouched

    new = client.post(f"{API}/emission-factors", headers=adm, json={
        "source": "Diesel Combustion", "scope": "Scope 1", "value": 3.0, "unit": "kgCO₂e/litre",
        "reference": "Test 2026", "validFrom": "2026-07-01", "status": "Active"})
    assert new.status_code == 201
    factors = {f["id"]: f for f in client.get(f"{API}/emission-factors", headers=adm).json()}
    assert factors["EF-01"]["status"] == "Superseded"  # older active version retired

    before = records(client, mgr, "2026-07")["Diesel Combustion"]["co2e"]
    dry = client.post(f"{API}/emission-records/recalculate", headers=mgr, json={"month": "2026-07", "facilityId": "FAC-001"}).json()
    assert dry["updated"] == 1 and dry["items"][0]["newFactor"] == 3.0 and dry["items"][0]["oldCo2e"] == before
    assert records(client, mgr, "2026-07")["Diesel Combustion"]["co2e"] == before  # nothing written

    applied = client.post(f"{API}/emission-records/recalculate", headers=mgr,
                          json={"month": "2026-07", "facilityId": "FAC-001", "dryRun": False}).json()
    assert applied["updated"] == 1
    rec = records(client, mgr, "2026-07")["Diesel Combustion"]
    assert rec["factor"] == 3.0 and rec["factorId"] == new.json()["id"]
    again = client.post(f"{API}/emission-records/recalculate", headers=mgr, json={"month": "2026-07", "facilityId": "FAC-001"}).json()
    assert again["updated"] == 0  # idempotent
    assert client.get(f"{API}/audit", headers=mgr).json()[0]["action"] == "Recalculated"


def test_changed_approved_figure_returns_to_review(client):
    eng, mgr, adm = (auth_headers(client, e) for e in (ENGINEER, MANAGER, ADMIN))
    save(client, eng)
    client.post(f"{API}/submissions/SUB-MOF-202608/review", headers=mgr, json={"status": "Approved", "comment": "ok"})
    client.post(f"{API}/emission-factors", headers=adm, json={
        "source": "Purchased Electricity", "scope": "Scope 2", "value": 0.7, "unit": "kgCO₂e/kWh",
        "reference": "CEA v20", "validFrom": "2026-08-01", "status": "Active"})
    client.post(f"{API}/emission-records/recalculate", headers=mgr, json={"month": "2026-08", "dryRun": False})
    el = records(client, mgr)["Purchased Electricity"]
    assert el["co2e"] == t(1_000_000 * 0.7 / 1000) and el["reviewStatus"] == "Under Review"
    assert "Re-approval required" in el["comments"][0]["text"]


def test_factor_integrity_rules(client):
    eng, adm = auth_headers(client, ENGINEER), auth_headers(client, ADMIN)
    save(client, eng)  # records now cite EF-05
    assert client.patch(f"{API}/emission-factors/EF-05", headers=adm, json={"value": 0.9}).status_code == 409
    assert client.delete(f"{API}/emission-factors/EF-05", headers=adm).status_code == 409
    assert client.patch(f"{API}/emission-factors/EF-05", headers=adm, json={"reference": "CEA v19 (rev)"}).status_code == 200
    bad = {"source": "Diesel Combustion", "scope": "Scope 1", "value": 1, "unit": "kgCO₂e/kWh", "reference": "x",
           "validFrom": "2030-01-01", "status": "Active"}
    assert client.post(f"{API}/emission-factors", headers=adm, json=bad).status_code == 422  # unit mismatch
    dup = {**bad, "unit": "kgCO₂e/litre", "validFrom": "2026-04-01"}
    assert client.post(f"{API}/emission-factors", headers=adm, json=dup).status_code == 409  # same source + date


def test_missing_factor_does_not_block_submission_but_is_audited(client):
    eng, adm = auth_headers(client, ENGINEER), auth_headers(client, ADMIN)
    assert client.delete(f"{API}/emission-factors/EF-03", headers=adm).status_code == 200  # Flaring
    assert save(client, eng).status_code == 200
    assert "Flaring" not in records(client, eng) and len(records(client, eng)) == 5
    assert any(a["action"] == "Calculation warning" for a in client.get(f"{API}/audit", headers=eng).json())
