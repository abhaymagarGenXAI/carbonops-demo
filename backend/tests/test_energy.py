import pytest

from app.services import energy_engine as ee
from tests.conftest import ENGINEER, MANAGER, auth_headers
from tests.test_workflows import DATA

API = "/api/v1"
ELE = ee.STREAMS[0]


def test_variance_and_classification():
    assert ee.variance_pct(110, 100) == 10.0 and ee.variance_pct(5, None) == 0.0 and ee.variance_pct(5, 0) == 0.0
    assert ee.classify("Approved", 100, 100, 14.0) == "Validated"  # band is exclusive at 14.0
    assert ee.classify("Approved", 115, 100, 15.0) == "Anomaly"
    assert ee.classify("Approved", 0, 100, -100.0) == "Missing"
    assert ee.classify("Draft", 100, 100, 0) == "Pending"
    assert ee.classify("Rejected", 100, 100, 0) == "Pending"
    assert ee.classify("Draft", 0, None, 0.0) == "Pending"  # nothing to compare with, not "Missing"


def test_derive_records_ids_match_seed_format_and_gj():
    sub = {"id": "SUB-MOF-202602", "month": "2026-02", "status": "Approved", "data": {"electricity": 1000, "diesel": 10}}
    recs = ee.derive_records(facility_id="FAC-001", facility_code="MOF", submission=sub, prev_data={"electricity": 1000, "diesel": 20})
    by = {r["stream"]: r for r in recs}
    assert by["Electricity"]["id"] == "EN-MOF-ELE-202602" and by["Electricity"]["energyGj"] == 3.6
    assert by["Diesel"]["variance"] == -50.0 and by["Diesel"]["validation"] == "Anomaly"
    assert by["Steam"]["energyGj"] is None and len(recs) == 5


def _all(client, h):
    return {r["id"]: r for r in client.get(f"{API}/energy-records", headers=h).json()}


def test_reconcile_dry_run_writes_nothing_then_apply_is_idempotent(client):
    mgr = auth_headers(client, MANAGER)
    before = _all(client, mgr)
    r = client.post(f"{API}/energy-records/reconcile", headers=mgr, json={}).json()
    assert r["dryRun"] is True and r["updated"] > 0  # legacy records are not yet linked to submissions
    assert _all(client, mgr) == before
    applied = client.post(f"{API}/energy-records/reconcile", headers=mgr, json={"dryRun": False}).json()
    assert applied["updated"] == r["updated"] and applied["created"] == r["created"]
    after = _all(client, mgr)
    hidden = sum(1 for i in r["items"] if i["excluded"])  # records of Draft / Rejected submissions are not shown
    assert hidden > 0 and len(after) == 140 + r["created"] - hidden
    locked = {p["period"] for p in client.get(f"{API}/reference/reportingPeriods", headers=mgr).json() if p["status"] == "Locked"}
    assert locked and any(m in locked for m in {r["month"] for r in after.values()})
    assert all(bool(rec.get("submissionId")) == (rec["month"] not in locked) for rec in after.values())  # locked periods untouched
    assert any("locked" in sk["reason"] for sk in applied["skipped"])
    again = client.post(f"{API}/energy-records/reconcile", headers=mgr, json={"dryRun": False}).json()
    assert again["updated"] == 0 and again["created"] == 0
    # user-owned fields survive reconciliation
    assert after["EN-MOF-ELE-202606"]["meterRef"] == before["EN-MOF-ELE-202606"]["meterRef"]
    assert after["EN-MOF-ELE-202606"]["cost"] == before["EN-MOF-ELE-202606"]["cost"]
    audit = client.get(f"{API}/audit", headers=mgr).json()
    assert audit[0]["action"] == "Reconciled"


def test_reconcile_permissions(client):
    eng = auth_headers(client, ENGINEER)
    assert client.post(f"{API}/energy-records/reconcile", headers=eng, json={}).status_code == 403


def test_derived_fields_locked_but_cost_editable(client):
    mgr, eng = auth_headers(client, MANAGER), auth_headers(client, ENGINEER)
    client.post(f"{API}/energy-records/reconcile", headers=mgr, json={"dryRun": False})
    rid = "EN-MOF-ELE-202606"
    assert client.patch(f"{API}/energy-records/{rid}", headers=eng, json={"quantity": 1}).status_code == 409
    assert client.patch(f"{API}/energy-records/{rid}", headers=eng, json={"validation": "Validated"}).status_code == 409
    ok = client.patch(f"{API}/energy-records/{rid}", headers=eng, json={"cost": 123, "meterRef": "MTR-X", "invoiceRef": "INV-X"})
    assert ok.status_code == 200 and ok.json()["cost"] == 123 and ok.json()["meterRef"] == "MTR-X"
    assert client.delete(f"{API}/energy-records/{rid}", headers=eng).status_code == 409
    new = {"facilityId": "FAC-001", "month": "2026-06", "stream": "Electricity", "quantity": 1, "unit": "kWh"}
    assert client.post(f"{API}/energy-records", headers=eng, json=new).status_code == 409


def test_submission_save_updates_energy_and_next_month_variance(client):
    eng = auth_headers(client, ENGINEER)
    fac = client.get(f"{API}/facilities/FAC-004", headers=eng).json()
    body = {"facilityId": "FAC-004", "unit": fac["units"][0], "month": "2026-07", "status": "Draft",
            "data": {**DATA, "electricity": 4_000_000}}
    assert client.post(f"{API}/submissions", headers=eng, json=body).status_code == 200
    rid = f"EN-{fac['code']}-ELE-202607"
    rec = client.get(f"{API}/energy-records/{rid}", headers=eng).json()
    assert rec["quantity"] == 4_000_000 and rec["submissionId"] == f"SUB-{fac['code']}-202607" and rec["energyGj"] == 14400.0
    prev = client.get(f"{API}/energy-records/EN-{fac['code']}-ELE-202606", headers=eng).json()["quantity"]
    assert rec["variance"] == round((4_000_000 - prev) / prev * 100, 1)
    # correcting the submission re-derives the record
    body["data"]["electricity"] = prev
    body["status"] = "Submitted"
    client.post(f"{API}/submissions", headers=eng, json=body)
    assert client.get(f"{API}/energy-records/{rid}", headers=eng).json()["variance"] == 0.0
