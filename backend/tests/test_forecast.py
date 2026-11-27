import pytest

from app.services import forecast_engine as fe
from tests.conftest import ENGINEER, MANAGER, auth_headers

API = "/api/v1"


def test_exact_line_is_recovered_with_zero_band():
    months = [f"2026-{m:02d}" for m in range(1, 7)]
    res = fe.forecast_series(months, [100, 110, 120, 130, 140, 150], 3)
    assert res["fit"]["slopePerMonth"] == 10 and res["fit"]["r2"] == 1.0 and res["fit"]["residualSd"] == 0
    assert [(r["month"], r["value"], r["low"], r["high"]) for r in res["projection"]] == [
        ("2026-07", 160, 160, 160), ("2026-08", 170, 170, 170), ("2026-09", 180, 180, 180)]


def test_year_rollover_and_noisy_band_widens_with_distance():
    months = ["2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]
    res = fe.forecast_series(months, [100, 112, 98, 111, 101], 12)
    assert res["projection"][2]["month"] == "2027-05"
    width = [r["high"] - r["low"] for r in res["projection"]]
    assert width[0] > 0 and width[-1] > width[0]
    assert all(r["low"] <= r["value"] <= r["high"] for r in res["projection"])


def test_prediction_interval_matches_hand_calculation():
    # y = 10, 12, 11, 13, 14 -> slope 0.9, intercept 10.1, SSE 1.9 -> s = sqrt(1.9/3); t(3)=3.182; x=5 -> yhat 14.7
    m = fe.fit([10, 12, 11, 13, 14])
    y, lo, hi = fe.predict(m, 5)
    assert m["slope"] == pytest.approx(0.9) and y == pytest.approx(14.7)
    s = (1.9 / 3) ** 0.5
    half = 3.182 * s * (1 + 1 / 5 + (5 - 2) ** 2 / 10) ** 0.5
    assert (hi - lo) / 2 == pytest.approx(half)


def test_only_consecutive_recent_months_are_used():
    assert fe.consecutive_tail(["2026-01", "2026-02", "2026-04", "2026-05", "2026-06"]) == ["2026-04", "2026-05", "2026-06"]
    assert len(fe.consecutive_tail([f"2026-{m:02d}" for m in range(1, 13)], 6)) == 6


def test_target_outlook_verdict_and_band_certainty():
    base = {"end": "2026-03", "months": 3, "byScope": {}, "scope1": 300.0, "scope2": 300.0, "total": 600.0}
    months = [f"2026-{m:02d}" for m in range(4, 10)]
    res = fe.forecast_series(months, [200, 200, 200, 200, 200, 200], 3)          # flat 200/month
    o = fe.target_outlook(res, base, {"scope": "Total", "reductionPct": 10, "targetYear": 2027})
    assert o["allowedMonthly"] == pytest.approx(180.0) and o["verdict"] == "Projected to miss" and o["gapMonthly"] == pytest.approx(20.0)
    assert o["certainty"].startswith("Misses the target even at the lower bound")
    low = fe.forecast_series(months, [170] * 6, 3)
    o2 = fe.target_outlook(low, base, {"scope": "Total", "reductionPct": 10, "targetYear": 2027})
    assert o2["verdict"] == "Projected to meet" and o2["certainty"].startswith("Meets")


def test_api_forecast_uses_only_complete_approved_months(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    f = client.get(f"{API}/forecast", headers=eng).json()
    assert f["available"] and f["usedMonths"] == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    assert "2026-06" not in f["usedMonths"] and len(f["scopes"]["Total"]["projection"]) == 12
    # history equals what the targets module calls complete+approved (single source of truth)
    t = client.get(f"{API}/targets", headers=mgr).json()
    assert f["usedMonths"][-1] == t["completeThrough"]
    hist = {h["month"]: h["value"] for h in f["scopes"]["Total"]["history"]}
    inv = client.get(f"{API}/reports/inventory", headers=mgr, params={"from": "2026-05", "to": "2026-05"}).json()
    assert hist["2026-05"] == pytest.approx(inv["summary"]["totals"]["scope1"] + inv["summary"]["totals"]["scope2"], abs=0.05)
    assert client.get(f"{API}/forecast", headers=eng, params={"horizon": 99}).status_code == 422


def test_api_outlook_follows_configured_targets(client):
    mgr = auth_headers(client, MANAGER)
    assert client.get(f"{API}/forecast", headers=mgr).json()["outlook"] == []
    assert client.put(f"{API}/targets/baseline", headers=mgr, json={"start": "2026-01", "end": "2026-03"}).status_code == 200
    assert client.put(f"{API}/targets", headers=mgr, json={"targets": [{"scope": "Total", "reductionPct": 20, "targetYear": 2028}]}).status_code == 200
    o = client.get(f"{API}/forecast", headers=mgr).json()["outlook"]
    assert len(o) == 1 and o[0]["verdict"] in ("Projected to meet", "Projected to miss") and o[0]["allowedMonthly"] > 0
