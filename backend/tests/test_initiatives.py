import pytest

from app.services import initiatives_engine as ie
from tests.conftest import ENGINEER, MANAGER, auth_headers

API = "/api/v1"
A = {"carbonValuePerTonne": 2200.0, "discountRatePct": 8.0, "lifetimeYears": 10}


def init(**kw):
    return {"id": "I", "name": "n", "facilityId": "FAC-001", "status": "In Progress", "investment": 1_000_000,
            "expectedReduction": 100, "actualReduction": 0, "annualSavings": 0, **kw}


# ------------------------------------------------------------------ pure engine
def test_economics_follow_the_assumptions():
    assert ie.crf(8, 10) == pytest.approx(0.1490295, abs=1e-6) and ie.crf(0, 10) == 0.1
    e = ie.economics(init(), A)
    assert e == {"annualCost": pytest.approx(149029.5, abs=0.1), "maccCost": pytest.approx(1490.29, abs=0.01), "roi": 22.0, "paybackYears": 4.5}
    saver = ie.economics(init(annualSavings=300_000), A)  # savings exceed the annualised cost -> negative MACC (pays for itself)
    assert saver["maccCost"] < 0 and saver["roi"] == 52.0 and saver["paybackYears"] == pytest.approx(1.9, abs=0.05)
    assert ie.economics(init(), {**A, "carbonValuePerTonne": 4400})["roi"] == 44.0  # no hardcoded 2200 any more


def test_progress_derives_from_milestones():
    ms = lambda *d: [{"name": str(i), "date": "2026-01-01", "done": x} for i, x in enumerate(d)]
    assert ie.derive_progress([], "Planned") == {}
    assert ie.derive_progress(ms(False, False), "Planned") == {"completion": 0.0}
    assert ie.derive_progress(ms(True, False, False), "Planned") == {"completion": 33.0, "status": "In Progress"}
    assert ie.derive_progress(ms(True, True), "In Progress") == {"completion": 100.0, "status": "Completed", "timeline": "Complete"}
    assert ie.derive_progress(ms(True, False), "On Hold") == {"completion": 50.0}  # on hold stays on hold


def test_macc_order_and_target_coverage():
    items = [init(id="A", investment=2_000_000), init(id="B"), init(id="C", status="Completed"), init(id="D", status="On Hold", actualReduction=0)]
    curve = ie.macc_curve(items, A)
    assert [r["id"] for r in curve] == ["B", "A"] and curve[1]["cumulativeReduction"] == 200  # open ones only, cheapest first
    cov = ie.target_coverage(
        [init(id="X", actualReduction=40, expectedReduction=100), init(id="Y", status="Planned", expectedReduction=50), init(id="Z", status="On Hold", expectedReduction=30)],
        {"baselineAnnual": 1000, "targetAnnual": 700, "targetYear": 2027, "reductionPct": 30})
    assert (cov["gapAnnual"], cov["delivered"], cov["pipeline"], cov["onHold"], cov["coveragePct"], cov["uncovered"]) == (300, 40, 110, 30, 50.0, 150)


# ------------------------------------------------------------------ API
def test_assumptions_api_and_live_roi(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert client.get(f"{API}/initiatives/assumptions", headers=eng).json() == {"carbonValuePerTonne": 2200, "discountRatePct": 8, "lifetimeYears": 10}
    ok = {"carbonValuePerTonne": 4400, "discountRatePct": 10, "lifetimeYears": 15}
    assert client.put(f"{API}/initiatives/assumptions", headers=eng, json=ok).status_code == 403
    for bad in ({**ok, "discountRatePct": 50}, {**ok, "lifetimeYears": 0}, {**ok, "carbonValuePerTonne": -1}):
        assert client.put(f"{API}/initiatives/assumptions", headers=mgr, json=bad).status_code == 422
    before = {i["id"]: i["roi"] for i in client.get(f"{API}/initiatives", headers=eng).json()}
    assert client.put(f"{API}/initiatives/assumptions", headers=mgr, json=ok).status_code == 200
    after = client.get(f"{API}/initiatives", headers=eng).json()
    assert all(i["roi"] != before[i["id"]] for i in after if i["investment"] > 0)  # derived on read, never stale
    i = after[0]
    assert i["maccCost"] is not None and i["annualCost"] > 0
    assert client.get(f"{API}/audit", headers=mgr).json()[0]["target"] == "initiative-assumptions"


def test_milestones_drive_progress_and_actuals_are_not_invented(client):
    mgr = auth_headers(client, MANAGER)
    new = client.post(f"{API}/initiatives", headers=mgr, json={
        "name": "Solar roof", "type": "Solar Installation", "facilityId": "FAC-002", "expectedReduction": 1000,
        "investment": 5_000_000, "annualSavings": 200_000, "startDate": "2026-09-01", "endDate": "2027-03-31"}).json()
    assert new["annualSavings"] == 200_000 and new["roi"] > 0 and new["actualReduction"] == 0
    ms = new["milestones"]
    ms[0]["done"] = True
    up = client.patch(f"{API}/initiatives/{new['id']}", headers=mgr, json={"milestones": ms}).json()
    assert up["completion"] == 33 and up["status"] == "In Progress"
    up = client.patch(f"{API}/initiatives/{new['id']}", headers=mgr, json={"milestones": [{**m, "done": True} for m in ms]}).json()
    assert up["completion"] == 100 and up["status"] == "Completed" and up["timeline"] == "Complete"
    assert up["actualReduction"] == 0  # completing does not fabricate a measured saving
    assert client.patch(f"{API}/initiatives/{new['id']}", headers=mgr, json={"actualReduction": 640}).json()["actualReduction"] == 640
    assert client.patch(f"{API}/initiatives/{new['id']}", headers=mgr, json={"milestones": [{"name": "", "date": "2026-01-01"}]}).status_code == 422
    adv = client.post(f"{API}/initiatives/INIT-105/advance", headers=mgr).json()
    assert adv["actualReduction"] == 0  # the old "expected x completion x 0.92" invention is gone


def test_analysis_links_initiatives_to_baseline_and_targets(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    plain = client.get(f"{API}/initiatives/analysis", headers=eng).json()
    assert plain["targetCoverage"] is None and plain["facilityMeasured"] == [] and plain["baselineSet"] is False
    costs = [r["maccCost"] for r in plain["macc"]]
    assert costs == sorted(costs) and plain["macc"][-1]["cumulativeReduction"] == pytest.approx(sum(r["expectedReduction"] for r in plain["macc"]))
    assert {r["status"] for r in plain["macc"]} <= {"Planned", "In Progress"}
    client.put(f"{API}/targets/baseline", headers=mgr, json={"start": "2026-01", "end": "2026-03"})
    client.put(f"{API}/targets", headers=mgr, json={"targets": [{"scope": "Total", "reductionPct": 10, "targetYear": 2027}]})
    a = client.get(f"{API}/initiatives/analysis", headers=eng).json()
    tgt = client.get(f"{API}/targets", headers=eng).json()
    cov = a["targetCoverage"]
    assert cov["gapAnnual"] == pytest.approx(tgt["progress"][0]["baselineAnnual"] - tgt["progress"][0]["targetAnnual"], abs=0.05)
    assert cov["delivered"] == a["portfolio"]["verified"] and cov["coveragePct"] > 0
    fac = {f["facilityId"]: f for f in a["facilityMeasured"]}
    assert set(fac) == {i["facilityId"] for i in client.get(f"{API}/initiatives", headers=eng).json()}
    one = fac["FAC-001"]
    base = client.get(f"{API}/targets", headers=eng).json()["baseline"]
    assert one["baselineMonthly"] == pytest.approx(base["byFacility"]["FAC-001"] / 3, abs=0.01) and one["monthsEvaluated"] == 2
    assert one["measuredAnnualReduction"] == pytest.approx((one["baselineMonthly"] - one["actualMonthly"]) * 12, abs=0.05)
    assert client.get(f"{API}/initiatives/analysis").status_code == 401
