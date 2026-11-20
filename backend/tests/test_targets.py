import pytest

from app.services import targets_engine as te
from tests.conftest import ENGINEER, MANAGER, auth_headers

API = "/api/v1"
FACS = ["A", "B"]


def rec(month, fac, scope, co2e, status="Approved"):
    return {"month": month, "facilityId": fac, "scope": scope, "co2e": co2e, "reviewStatus": status}


# ------------------------------------------------------------------ pure engine
def test_baseline_needs_full_facility_coverage_and_only_approved():
    recs = [rec("2026-01", f, s, 10) for f in FACS for s in ("Scope 1", "Scope 2")]
    recs += [rec("2026-02", "A", "Scope 1", 10), rec("2026-02", "B", "Scope 1", 99, "Under Review")]
    agg = te.aggregate(recs)
    assert agg["2026-02"]["Total"] == 10  # pending record ignored
    gap = te.build_baseline(agg, FACS, "2026-01", "2026-02")
    assert gap["snapshot"] is None and gap["missing"] == [{"month": "2026-02", "facilityIds": ["B"]}]
    ok = te.build_baseline(agg, FACS, "2026-01", "2026-01")["snapshot"]
    assert (ok["scope1"], ok["scope2"], ok["total"], ok["annualTotal"], ok["recordCount"]) == (20, 20, 40, 480, 4)
    assert te.complete_months(agg, FACS) == ["2026-01"]


def test_linear_path_and_status_bands():
    base = {"start": "2026-01", "end": "2026-12", "months": 12, "scope1": 1200, "scope2": 0, "total": 1200}
    f = lambda m: te.allowed_monthly(base, "Total", 20, 2027, m)
    assert f("2026-12") == 100  # at the baseline level
    assert f("2027-06") == pytest.approx(100 * (1 - 0.2 * 6 / 12))  # halfway to Dec 2027
    assert f("2027-12") == pytest.approx(80) and f("2030-01") == pytest.approx(80)  # capped at the target
    t = {"scope": "Total", "reductionPct": 20, "targetYear": 2027}
    def status(actual):
        agg = {"2027-01": {"Total": actual, "Scope 1": actual, "Scope 2": 0, "facilities": {"A"}}}
        return te.progress(base, t, agg, ["2027-01"])["status"]
    allowed = f("2027-01")
    assert status(allowed) == "On track" and status(allowed * 1.04) == "At risk" and status(allowed * 1.06) == "Off track"
    assert te.progress(base, t, {}, [])["status"] == "No data yet"


# ------------------------------------------------------------------ API
def _approved(client, h):
    return [r for r in client.get(f"{API}/emission-records", headers=h).json() if r["reviewStatus"] == "Approved"]


def test_baseline_targets_and_progress_are_traceable(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    empty = client.get(f"{API}/targets", headers=eng).json()
    assert empty["baseline"] is None and empty["completeThrough"] == "2026-05" and "2026-06" in empty["incompleteMonths"]
    assert client.get(f"{API}/targets").status_code == 401
    assert client.put(f"{API}/targets/baseline", headers=eng, json={"start": "2026-01", "end": "2026-03"}).status_code == 403
    # incomplete month (June only partly approved) is refused with the gaps listed
    r = client.put(f"{API}/targets/baseline", headers=mgr, json={"start": "2026-01", "end": "2026-06"})
    assert r.status_code == 422 and "2026-06" in r.json()["detail"]
    for bad in ({"start": "2026-03", "end": "2026-01"}, {"start": "2025-01", "end": "2026-03"}, {"start": "bad", "end": "2026-03"}):
        assert client.put(f"{API}/targets/baseline", headers=mgr, json=bad).status_code == 422
    # targets need a baseline first
    tg = [{"scope": "Total", "reductionPct": 10, "targetYear": 2027}]
    assert client.put(f"{API}/targets", headers=mgr, json={"targets": tg}).status_code == 409

    ok = client.put(f"{API}/targets/baseline", headers=mgr, json={"start": "2026-01", "end": "2026-03"})
    assert ok.status_code == 200
    b = ok.json()["baseline"]
    recs = [x for x in _approved(client, mgr) if "2026-01" <= x["month"] <= "2026-03"]
    assert b["total"] == pytest.approx(sum(x["co2e"] for x in recs), abs=0.02) and b["recordCount"] == len(recs)
    assert b["annualTotal"] == pytest.approx(b["total"] * 4, abs=0.05) and b["setBy"] and b["basis"] == "Approved"

    for bad in ([{"scope": "Total", "reductionPct": 0, "targetYear": 2027}], [{"scope": "Total", "reductionPct": 10, "targetYear": 2026}],
                [{"scope": "Scope 3", "reductionPct": 10, "targetYear": 2030}], tg + tg):
        assert client.put(f"{API}/targets", headers=mgr, json={"targets": bad}).status_code == 422
    both = tg + [{"scope": "Scope 2", "reductionPct": 30, "targetYear": 2028}]
    res = client.put(f"{API}/targets", headers=mgr, json={"targets": both}).json()
    assert [p["scope"] for p in res["progress"]] == ["Total", "Scope 2"]
    # progress is exactly reproducible from approved records after the baseline (April, May are complete)
    after = [x for x in _approved(client, mgr) if "2026-04" <= x["month"] <= "2026-05"]
    p = res["progress"][0]
    assert p["monthsEvaluated"] == 2 and p["latestMonth"] == "2026-05"
    assert p["cumulativeActual"] == pytest.approx(sum(x["co2e"] for x in after), abs=0.05)
    base_m = b["total"] / 3
    allowed = sum(base_m * (1 - 0.10 * k / 21) for k in (1, 2))  # 21 months from 2026-03 to 2027-12
    assert p["cumulativeAllowed"] == pytest.approx(allowed, abs=0.05)
    assert p["status"] in ("On track", "At risk", "Off track")
    assert {r["month"] for r in res["series"]} == {"2026-01", "2026-02", "2026-03", "2026-04", "2026-05"}
    assert [r["phase"] for r in res["series"]][:3] == ["baseline"] * 3
    # audit trail
    acts = {a["target"] for a in client.get(f"{API}/audit", headers=mgr).json()[:4]}
    assert {"emission-baseline", "emission-targets"} <= acts
    # re-baselining cannot leave a target at/before the baseline year
    assert client.put(f"{API}/targets", headers=mgr, json={"targets": []}).json()["targets"] == []


def test_unapproving_a_month_removes_it_from_tracking(client):
    from app.db.client import get_database

    mgr = auth_headers(client, MANAGER)
    client.put(f"{API}/targets/baseline", headers=mgr, json={"start": "2026-01", "end": "2026-03"})
    client.put(f"{API}/targets", headers=mgr, json={"targets": [{"scope": "Total", "reductionPct": 5, "targetYear": 2027}]})
    assert client.get(f"{API}/targets", headers=mgr).json()["progress"][0]["monthsEvaluated"] == 2
    # if one facility's May records stop being approved, May is incomplete and no longer counts toward progress
    get_database()["emission_records"].update_many({"facilityId": "FAC-001", "month": "2026-05"}, {"$set": {"reviewStatus": "Under Review"}})
    got = client.get(f"{API}/targets", headers=mgr).json()
    assert "2026-05" in got["incompleteMonths"] and got["completeThrough"] == "2026-04"
    p = got["progress"][0]
    assert p["monthsEvaluated"] == 1 and p["latestMonth"] == "2026-04"
