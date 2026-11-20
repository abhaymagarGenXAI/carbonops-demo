from app.services import rules, validation
from tests.conftest import MANAGER, auth_headers

API = "/api/v1"

BASE = {"electricity": 1000, "diesel": 100, "naturalGas": 500, "steam": 10, "flareGas": 50, "methaneLeak": 5}


def _hist(n=3, **over):
    return [{**BASE, **over} for _ in range(n)]


def test_no_history_only_control_limit():
    assert validation.check_activity(BASE, []) == []
    assert [f.code for f in validation.check_activity({"diesel": 250_001}, [])] == ["DIESEL_LIMIT"]


def test_spike_thresholds_and_direction():
    f = validation.check_activity({**BASE, "electricity": 1299}, _hist())  # +29.9% -> below threshold
    assert f == []
    f = validation.check_activity({**BASE, "electricity": 1300}, _hist())  # +30% -> Medium
    assert [(x.code, x.severity) for x in f] == [("SPIKE", "Medium")]
    f = validation.check_activity({**BASE, "diesel": 40}, _hist())  # -60% -> High
    assert f[0].severity == "High" and f[0].deviation_pct == -60.0 and "below" in f[0].message


def test_zero_against_positive_history_and_zero_history_ignored():
    f = validation.check_activity({**BASE, "steam": 0}, _hist())
    assert [x.code for x in f] == ["ZERO"]
    assert validation.check_activity({**BASE, "steam": 999}, _hist(steam=0)) == []  # no reference -> no finding


def test_only_three_most_recent_months_used():
    hist = _hist(1, electricity=1000) + _hist(2, electricity=1000) + _hist(1, electricity=9_999_999)
    assert validation.check_activity(BASE, hist) == []


def test_history_before_skips_drafts_and_future():
    subs = [{"month": "2026-01", "status": "Approved", "data": {"a": 1}}, {"month": "2026-02", "status": "Draft", "data": {"a": 2}},
            {"month": "2026-03", "status": "Submitted", "data": {"a": 3}}, {"month": "2026-05", "status": "Approved", "data": {"a": 5}}]
    assert validation.history_before(subs, "2026-04") == [{"a": 3}, {"a": 1}]


def test_rules_validate_activity_uses_history():
    assert rules.validate_activity("Submitted", {**BASE, "electricity": 5000}, _hist()) [0] == "Warnings"
    assert rules.validate_activity("Submitted", BASE, _hist()) == ("Passed", [])


def test_alerts_endpoint_live_and_traceable(client):
    mgr = auth_headers(client, MANAGER)
    r = client.get(f"{API}/alerts", headers=mgr)
    assert r.status_code == 200
    alerts = r.json()
    assert alerts and all({"id", "severity", "title", "detail", "action"} <= a.keys() for a in alerts)
    sevs = [a["severity"] for a in alerts]
    assert sevs == sorted(sevs, key=["High", "Medium", "Low"].index)  # High first
    assert not any(a["id"].startswith("AI-") for a in alerts)  # no static seed alerts
    assert client.get(f"{API}/alerts").status_code == 401  # auth still enforced


def test_alert_appears_after_anomalous_submission(client):
    from tests.test_workflows import DATA
    eng = auth_headers(client, "s.nair@carbonops.ongc")
    body = {"facilityId": "FAC-004", "unit": client.get(f"{API}/facilities/FAC-004", headers=eng).json()["units"][0],
            "month": "2026-07", "status": "Submitted", "data": {**DATA, "electricity": 90_000_000}}
    assert client.post(f"{API}/submissions", headers=eng, json=body).status_code == 200
    alerts = client.get(f"{API}/alerts", headers=eng).json()
    hit = [a for a in alerts if a["id"] == "ALR-SUB-" + client.get(f"{API}/facilities/FAC-004", headers=eng).json()["code"] + "-202607-electricity-SPIKE"]
    assert hit and hit[0]["severity"] == "High" and "above" in hit[0]["detail"]
