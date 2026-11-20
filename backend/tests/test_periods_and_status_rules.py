from tests.conftest import ENGINEER, MANAGER, auth_headers, open_periods
from tests.test_workflows import DATA

API = "/api/v1"


def _body(month="2026-07", status="Submitted", **data):
    return {"facilityId": "FAC-004", "unit": "", "month": month, "status": status, "data": {**DATA, **data}}


def _unit(client, h):
    return client.get(f"{API}/facilities/FAC-004", headers=h).json()["units"][0]


def _submit(client, h, **kw):
    b = _body(**{k: v for k, v in kw.items() if k in ("month", "status")})
    b["unit"] = _unit(client, h)
    b["data"].update({k: v for k, v in kw.items() if k not in ("month", "status")})
    return client.post(f"{API}/submissions", headers=h, json=b)


# ---------------------------------------------------------------- reporting periods (question 1)
def test_cannot_submit_to_missing_or_locked_period(client):
    eng = auth_headers(client, ENGINEER)
    assert _submit(client, eng, month="2026-08").status_code == 422  # not opened yet
    assert _submit(client, eng, month="2026-03", status="Draft").status_code == 409  # locked


def test_open_next_period_and_permissions(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert client.post(f"{API}/reporting-periods", headers=eng, json={}).status_code == 403
    r = client.post(f"{API}/reporting-periods", headers=mgr, json={})
    assert r.status_code == 201 and r.json()["period"] == "2026-08" and r.json()["status"] == "Open"
    assert r.json()["submissionDue"] == "2026-08-15" and r.json()["approvalDue"] == "2026-08-25"
    periods = {p["period"]: p["status"] for p in client.get(f"{API}/reporting-periods", headers=eng).json()}
    assert periods["2026-08"] == "Open" and periods["2026-07"] == "In Review"  # previous Open moved to review
    assert _submit(client, eng, month="2026-08", status="Draft").status_code == 200
    assert client.post(f"{API}/reporting-periods", headers=mgr, json={"submissionDue": "2026-09-20", "approvalDue": "2026-09-10"}).status_code == 422


def test_lock_requires_all_approved_and_is_final(client):
    mgr = auth_headers(client, MANAGER)
    r = client.post(f"{API}/reporting-periods/2026-07/status", headers=mgr, json={"status": "Locked"})
    assert r.status_code == 409 and "approved submission" in r.json()["detail"]
    client.post(f"{API}/reporting-periods", headers=mgr, json={})  # brand-new empty 2026-08
    r = client.post(f"{API}/reporting-periods/2026-08/status", headers=mgr, json={"status": "Locked"})
    assert r.status_code == 409 and "has no submission" in r.json()["detail"]  # an empty period cannot be locked
    r = client.post(f"{API}/reporting-periods/2026-06/status", headers=mgr, json={"status": "Locked"})
    assert r.status_code == 409 and "SUB-HZR-202606 is Under Review" in r.json()["detail"] and "SUB-ASM-202606 is Rejected" in r.json()["detail"]
    eng = auth_headers(client, ENGINEER)  # a rejected submission cannot be approved: the data owner resubmits first
    old = client.get(f"{API}/submissions/SUB-ASM-202606", headers=eng).json()
    assert client.post(f"{API}/submissions/SUB-ASM-202606/review", headers=mgr, json={"status": "Approved", "comment": "x"}).status_code == 409
    assert client.post(f"{API}/submissions", headers=eng, json={
        "facilityId": old["facilityId"], "unit": old["unit"], "month": "2026-06", "status": "Submitted", "data": old["data"]}).status_code == 200
    for sid in ("SUB-HZR-202606", "SUB-ASM-202606"):  # approve the two open items, then the lock is allowed
        assert client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Approved", "comment": "ok"}).status_code == 200
    r = client.post(f"{API}/reporting-periods/2026-06/status", headers=mgr, json={"status": "Locked"})
    assert r.status_code == 200 and r.json()["status"] == "Locked" and r.json()["lockedOn"] != "—"
    assert _submit(client, auth_headers(client, ENGINEER), month="2026-06", status="Draft").status_code == 409
    assert client.post(f"{API}/reporting-periods/2026-03/status", headers=mgr, json={"status": "In Review"}).status_code == 409  # no reopening
    assert client.post(f"{API}/reporting-periods/2026-13/status", headers=mgr, json={"status": "Locked"}).status_code == 422


def test_review_blocked_in_locked_period(client):
    mgr = auth_headers(client, MANAGER)
    r = client.post(f"{API}/submissions/SUB-MOF-202603/review", headers=mgr, json={"status": "Rejected", "comment": "x"})
    assert r.status_code == 409


# ---------------------------------------------------------------- alerts (question 2)
def _alert_ids(client, h, sub_id):
    return [a["id"] for a in client.get(f"{API}/alerts", headers=h).json() if sub_id in a["id"]]


def test_alerts_clear_when_submission_is_decided(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert _submit(client, eng, electricity=90_000_000).status_code == 200
    sid = "SUB-KGB-202607"
    sid = client.get(f"{API}/submissions", headers=eng, params={"facility_id": "FAC-004", "month": "2026-07"}).json()[0]["id"]
    assert any("SPIKE" in i for i in _alert_ids(client, eng, sid))  # pending decision -> alert
    r = client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Rejected", "comment": "Meter reading wrong"})
    assert r.status_code == 200
    ids = _alert_ids(client, eng, sid)
    assert not any("SPIKE" in i for i in ids)  # rejected figures no longer raise anomaly alerts
    rej = [a for a in client.get(f"{API}/alerts", headers=eng).json() if a["id"] == f"ALR-REJ-{sid}"]
    assert rej and "Meter reading wrong" in rej[0]["detail"] and "Resubmission" in rej[0]["title"]
    assert _submit(client, eng, electricity=90_000_000).status_code == 200  # engineer resubmits
    assert not any(i.startswith("ALR-REJ") for i in _alert_ids(client, eng, sid))
    client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Approved", "comment": "ok"})
    assert _alert_ids(client, eng, sid) == []  # approved -> nothing left to act on


# ---------------------------------------------------------------- energy visibility (question 4)
def _energy_ids(client, h):
    return {r["id"] for r in client.get(f"{API}/energy-records", headers=h, params={"facility_id": "FAC-004", "month": "2026-07"}).json()}


def test_draft_and_rejected_data_is_kept_out_of_energy(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert _submit(client, eng, status="Draft", electricity=777).status_code == 200
    assert _energy_ids(client, eng) == set()  # a draft is not consumption
    sid = client.get(f"{API}/submissions", headers=eng, params={"facility_id": "FAC-004", "month": "2026-07"}).json()[0]["id"]
    code = sid.split("-")[1]
    ele = f"EN-{code}-ELE-202607"
    assert _submit(client, eng, electricity=5_000_000).status_code == 200
    assert ele in _energy_ids(client, eng)
    client.patch(f"{API}/energy-records/{ele}", headers=eng, json={"cost": 999, "meterRef": "MTR-KEEP"})
    client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Rejected", "comment": "no"})
    assert _energy_ids(client, eng) == set()  # rejected data disappears
    # reconcile (dry run + apply) must not bring it back
    for dry in (True, False):
        client.post(f"{API}/energy-records/reconcile", headers=mgr, json={"dryRun": dry})
        assert _energy_ids(client, eng) == set()
    # resubmitting restores the record with the engineer's procurement details intact
    assert _submit(client, eng, electricity=5_000_000).status_code == 200
    rec = client.get(f"{API}/energy-records/{ele}", headers=eng).json()
    assert rec["cost"] == 999 and rec["meterRef"] == "MTR-KEEP" and rec["excluded"] is False


def test_variance_ignores_rejected_previous_month(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    open_periods(client, "2026-08")
    assert _submit(client, eng, status="Draft", month="2026-08", electricity=1_000_000).status_code == 200
    sid = client.get(f"{API}/submissions", headers=eng, params={"facility_id": "FAC-004", "month": "2026-07"}).json()[0]["id"]
    client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Rejected", "comment": "bad"})
    assert _submit(client, eng, month="2026-08", electricity=1_000_000).status_code == 200  # re-derive 2026-08
    code = sid.split("-")[1]
    assert client.get(f"{API}/energy-records/EN-{code}-ELE-202608", headers=eng).json()["variance"] == 0.0
