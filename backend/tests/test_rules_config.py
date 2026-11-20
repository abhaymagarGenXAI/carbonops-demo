from app.services import validation as v
from tests.conftest import ENGINEER, MANAGER, auth_headers
from tests.test_workflows import DATA

API = "/api/v1"
BASE = {"electricity": 1000, "diesel": 100, "naturalGas": 500, "steam": 10, "flareGas": 50, "methaneLeak": 5}
HIST = [dict(BASE) for _ in range(3)]


# ------------------------------------------------------------------ pure engine driven by config
def test_config_changes_thresholds_history_and_enables():
    cur = {**BASE, "electricity": 1400}  # +40%
    assert [f.severity for f in v.check_activity(cur, HIST)] == ["Medium"]
    assert v.check_activity(cur, HIST, v.ValidationConfig(spike_pct=50, high_pct=80)) == []
    assert [f.severity for f in v.check_activity(cur, HIST, v.ValidationConfig(spike_pct=10, high_pct=30))] == ["High"]
    assert v.check_activity(cur, HIST, v.ValidationConfig(spike_enabled=False)) == []
    zero = {**BASE, "steam": 0}
    assert v.check_activity(zero, HIST, v.ValidationConfig(zero_enabled=False)) == []
    one = [{**BASE, "electricity": 1000}] + [{**BASE, "electricity": 10}] * 2  # newest first
    assert v.check_activity({**BASE, "electricity": 1000}, one, v.ValidationConfig(history_months=1)) == []
    assert v.check_activity({**BASE, "electricity": 1000}, one, v.ValidationConfig(history_months=3))  # mean 340 -> spike


def test_limits_and_blocking_flags():
    cfg = v.ValidationConfig(limits=(v.Limit("electricity", 5000, block=True), v.Limit("diesel", 50, enabled=False)))
    f = v.check_activity({**BASE, "electricity": 5001, "diesel": 9e9}, (), cfg)
    assert [(x.code, x.blocking) for x in f] == [("ELECTRICITY_LIMIT", True)]  # disabled diesel limit ignored
    assert "5,000 kWh" in f[0].message
    spike = v.ValidationConfig(spike_block_high=True)
    medium = v.check_activity({**BASE, "electricity": 1400}, HIST, spike)[0]
    high = v.check_activity({**BASE, "electricity": 3000}, HIST, spike)[0]
    assert (medium.blocking, high.blocking) == (False, True)  # only High spikes block
    assert v.check_activity({**BASE, "steam": 0}, HIST, v.ValidationConfig(zero_block=True))[0].blocking


# ------------------------------------------------------------------ endpoints
def _rules(**over):
    return {"spikeEnabled": True, "spikePct": 30, "highPct": 50, "historyMonths": 3, "spikeBlockHigh": False,
            "zeroEnabled": True, "zeroBlock": False, "limits": [{"field": "diesel", "max": 250000, "enabled": True, "block": False}],
            "inspectionIntervalDays": 150, **over}


def test_get_defaults_put_permissions_and_validation(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    d = client.get(f"{API}/validation-rules", headers=eng).json()
    assert d == _rules()  # defaults reproduce the previous hard-coded behaviour
    assert client.get(f"{API}/validation-rules").status_code == 401
    assert client.put(f"{API}/validation-rules", headers=eng, json=_rules()).status_code == 403
    for bad in (_rules(spikePct=60, highPct=40), _rules(historyMonths=0), _rules(spikePct=0),
                _rules(limits=[{"field": "diesel", "max": 1}, {"field": "diesel", "max": 2}]),
                _rules(limits=[{"field": "water", "max": 1}]), _rules(limits=[{"field": "diesel", "max": 0}]),
                _rules(inspectionIntervalDays=5)):
        assert client.put(f"{API}/validation-rules", headers=mgr, json=bad).status_code == 422, bad
    ok = client.put(f"{API}/validation-rules", headers=mgr, json=_rules(spikePct=45, highPct=90, inspectionIntervalDays=200))
    assert ok.status_code == 200 and client.get(f"{API}/validation-rules", headers=eng).json()["spikePct"] == 45
    assert client.get(f"{API}/audit", headers=mgr).json()[0]["target"] == "validation-rules"


def _submit(client, h, status="Submitted", **data):
    fac = client.get(f"{API}/facilities/FAC-004", headers=h).json()
    return client.post(f"{API}/submissions", headers=h, json={
        "facilityId": "FAC-004", "unit": fac["units"][0], "month": "2026-07", "status": status, "data": {**DATA, **data}})


def test_blocking_limit_stops_submission_but_not_draft(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    cfg = _rules(limits=[{"field": "electricity", "max": 5000000, "enabled": True, "block": True}])
    assert client.put(f"{API}/validation-rules", headers=mgr, json=cfg).status_code == 200
    r = _submit(client, eng, electricity=6_000_000)
    assert r.status_code == 422 and "blocked by validation rules" in r.json()["detail"] and "5,000,000 kWh" in r.json()["detail"]
    assert _submit(client, eng, "Draft", electricity=6_000_000).status_code == 200  # drafts are always allowed
    assert _submit(client, eng, electricity=4_000_000).status_code == 200  # within the limit
    client.post(f"{API}/submissions/SUB-KGB-202607/review", headers=mgr, json={"status": "Rejected", "comment": "redo"})  # reopens it for the engineer
    # turning the block off (warn only) lets the same data through, recorded as a warning
    cfg["limits"][0]["block"] = False
    client.put(f"{API}/validation-rules", headers=mgr, json=cfg)
    ok = _submit(client, eng, electricity=6_000_000).json()
    assert ok["validation"] == "Warnings" and any("control limit" in a for a in ok["anomalies"])


def test_thresholds_change_stored_anomalies_and_alerts(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    row = _submit(client, eng, electricity=6_120_000).json()  # ~+54% vs seeded history
    assert any("Electricity" in a for a in row["anomalies"])
    client.put(f"{API}/validation-rules", headers=mgr, json=_rules(spikePct=200, highPct=300))
    client.post(f"{API}/submissions/SUB-KGB-202607/review", headers=mgr, json={"status": "Rejected", "comment": "redo"})
    quiet = _submit(client, eng, electricity=6_120_000).json()
    assert not any("Electricity" in a for a in quiet["anomalies"])
    assert not [a for a in client.get(f"{API}/alerts", headers=eng).json() if "SUB-KGB-202607-electricity" in a["id"]]


def test_failed_status_is_gone_and_import_flags_blockers(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert {s["validation"] for s in client.get(f"{API}/submissions", headers=eng).json()} <= {"Passed", "Warnings", "Not Run"}
    client.put(f"{API}/validation-rules", headers=mgr, json=_rules(limits=[{"field": "electricity", "max": 1000, "block": True}]))
    head = "facility,unit,month,production_volume,electricity,diesel,natural_gas,steam,water,flare_gas,methane_leak,renewable,operating_hours"
    csv = f"{head}\nKG Basin,Vashishta Field,2026-07,1,9999,1,1,1,1,1,1,1,1\n".encode()
    p = client.post(f"{API}/submissions/import/preview", headers=eng, files={"file": ("a.csv", csv)}).json()
    assert p["rows"][0]["importable"] and any(w.startswith("Blocks submission") for w in p["rows"][0]["warnings"])
    row = {k: p["rows"][0][k] for k in ("facilityId", "unit", "month", "data")}
    res = client.post(f"{API}/submissions/import", headers=eng, json={"status": "Submitted", "rows": [row]}).json()
    assert res["failed"] == 1 and "blocked by validation rules" in res["results"][0]["detail"]
    assert client.post(f"{API}/submissions/import", headers=eng, json={"status": "Draft", "rows": [row]}).json()["saved"] == 1


# ------------------------------------------------------------------ review transitions (Approval queue vs Decision history)
def test_only_pending_submissions_can_be_decided(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    rv = lambda sid, st, c="note": client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": st, "comment": c})
    assert rv("SUB-KGB-202607", "Approved").status_code in (404, 409)  # nothing submitted yet for this month
    _submit(client, eng, electricity=4_000_000)
    assert rv("SUB-KGB-202607", "Under Review", "please re-check meter").status_code == 200  # rework request
    assert rv("SUB-KGB-202607", "Under Review", "still unclear").status_code == 200  # may be asked repeatedly
    assert rv("SUB-KGB-202607", "Approved", "ok").status_code == 200
    for st in ("Rejected", "Approved", "Under Review"):  # decided = history: read-only
        r = rv("SUB-KGB-202607", st)
        assert r.status_code == 409 and "approved submissions are final" in r.json()["detail"]
    rej = rv("SUB-ASM-202606", "Approved")  # seeded Rejected submission
    assert rej.status_code == 409 and "resubmit" in rej.json()["detail"]
    draft = client.get(f"{API}/submissions", headers=eng).json()
    d = next(s for s in draft if s["status"] == "Draft")
    r = rv(d["id"], "Approved")
    assert r.status_code == 409 and "not been submitted" in r.json()["detail"]


# ------------------------------------------------------------------ assets in alerts; energy basis
def test_inspection_alerts_follow_configured_interval(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    ids = lambda: [a for a in client.get(f"{API}/alerts", headers=eng).json() if a["id"].startswith("ALR-INSP-")]
    assets = client.get(f"{API}/assets", headers=eng).json()
    client.put(f"{API}/validation-rules", headers=mgr, json=_rules(inspectionIntervalDays=30))
    tight = ids()
    assert tight and all(a["kind"] == "inspection" and "Interval is 30 days" in a["detail"] for a in tight)
    assert len(tight) <= 4  # one alert per facility, not per asset
    counted = sum(int(a["title"].split(" ")[0]) for a in tight)
    live = [a for a in assets if a["status"] != "Shutdown"]
    assert 0 < counted <= len(live)  # shut-down assets are never chased
    client.put(f"{API}/validation-rules", headers=mgr, json=_rules(inspectionIntervalDays=730))
    assert ids() == []


def test_energy_records_carry_submission_status(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    _submit(client, eng, electricity=4_000_000)
    rid = "EN-KGB-ELE-202607"
    assert client.get(f"{API}/energy-records/{rid}", headers=eng).json()["submissionStatus"] == "Submitted"
    client.post(f"{API}/submissions/SUB-KGB-202607/review", headers=mgr, json={"status": "Approved", "comment": "ok"})
    assert client.get(f"{API}/energy-records/{rid}", headers=eng).json()["submissionStatus"] == "Approved"


def test_alerts_work_without_an_open_period_and_follow_selected_period(client):
    from tests.conftest import open_periods

    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    open_periods(client, "2026-09")
    for p in client.get(f"{API}/reporting-periods", headers=mgr).json():  # everything moved to review
        if p["status"] == "Open":
            assert client.post(f"{API}/reporting-periods/{p['period']}/status", headers=mgr, json={"status": "In Review"}).status_code == 200
    kinds = lambda **q: {a["kind"] for a in client.get(f"{API}/alerts", headers=eng, params=q).json()}
    assert "due" in kinds()  # default = latest In Review period, deadlines still tracked
    sep = [a for a in client.get(f"{API}/alerts", headers=eng, params={"period": "2026-09"}).json() if a["kind"] == "due"]
    assert sep and all("2026-09" in a["title"] for a in sep)
    jul = [a for a in client.get(f"{API}/alerts", headers=eng, params={"period": "2026-07"}).json() if a["kind"] == "due"]
    assert all("2026-07" in a["title"] for a in jul)
    assert client.get(f"{API}/alerts", headers=eng, params={"period": "bad"}).status_code == 422
    # rework requested in a period other than the selected one is still shown to the data owner, with its submission id
    _submit(client, eng, electricity=4_000_000)
    client.post(f"{API}/emission-records/EM-KGB-202607-1/review", headers=mgr, json={"status": "Under Review", "comment": "check meter"})
    rw = [a for a in client.get(f"{API}/alerts", headers=eng, params={"period": "2026-09"}).json() if a["kind"] == "rework"]
    assert rw and rw[0]["submissionId"] == "SUB-KGB-202607" and "check meter" in rw[0]["detail"]
