import pytest

from app.services import scope3_engine as eng
from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, open_periods

API = "/api/v1"
FACTOR = {"source": "Air travel – short haul", "scope": "Scope 3", "value": 0.15, "unit": "kgCO₂e/passenger-km",
          "reference": "Test ref", "validFrom": "2026-01-01", "status": "Active", "category": "6 Business travel"}


# ------------------------------------------------------------------ pure engine
def f(**kw):
    return {"id": "EF-90", **FACTOR, **kw}


def test_activity_based_calculation_is_traceable():
    r = eng.calculate(month="2026-05", category="6 Business travel", source=FACTOR["source"], activity=12000, factors=[f()])
    assert r["co2e"] == 1.8 and r["unit"] == "passenger-km" and r["factorId"] == "EF-90" and r["method"] == "Activity-based"
    assert "12,000 passenger-km × 0.15" in r["formula"]


def test_spend_based_and_version_selection():
    old = f(id="EF-91", source="Steel", unit="kgCO₂e/INR", value=0.5, validFrom="2026-01-01", category="1 Purchased goods and services")
    new = f(id="EF-92", source="Steel", unit="kgCO₂e/INR", value=0.4, validFrom="2026-06-01", category="1 Purchased goods and services")
    a = eng.calculate(month="2026-05", category="1 Purchased goods and services", source="Steel", activity=1_000_000, factors=[old, new])
    b = eng.calculate(month="2026-06", category="1 Purchased goods and services", source="Steel", activity=1_000_000, factors=[old, new])
    assert (a["factorId"], a["co2e"], a["method"]) == ("EF-91", 500.0, "Spend-based")
    assert (b["factorId"], b["co2e"]) == ("EF-92", 400.0)


@pytest.mark.parametrize("kw,msg", [
    (dict(source="Nope"), "No Scope 3 emission factor"),
    (dict(category="7 Employee commuting"), "belongs to category"),
    (dict(category="99 Bogus"), "Unknown Scope 3 category"),
])
def test_engine_refuses_instead_of_guessing(kw, msg):
    args = dict(month="2026-05", category="6 Business travel", source=FACTOR["source"], activity=1, factors=[f()])
    with pytest.raises(eng.Scope3Error, match=msg):
        eng.calculate(**{**args, **kw})


def test_scope1_factor_is_never_used_for_scope3():
    with pytest.raises(eng.Scope3Error):
        eng.calculate(month="2026-05", category="6 Business travel", source="Diesel Combustion", activity=1,
                      factors=[f(source="Diesel Combustion", scope="Scope 1")])


# ------------------------------------------------------------------ API
@pytest.fixture()
def setup(client):
    open_periods(client, "2026-11")
    adm, mgr, eng_ = (auth_headers(client, e) for e in (ADMIN, MANAGER, ENGINEER))
    r = client.post(f"{API}/emission-factors", headers=adm, json={k: v for k, v in {**FACTOR, "validFrom": "2026-01-01"}.items()})
    assert r.status_code == 201, r.text
    return adm, mgr, eng_, r.json()


def body(**kw):
    return {"month": "2026-11", "category": "6 Business travel", "source": FACTOR["source"], "activityValue": 12000, **kw}


def test_factor_category_round_trips_and_factor_admin_only(client, setup):
    adm, mgr, eng_, fac = setup
    assert fac["category"] == "6 Business travel"
    assert client.post(f"{API}/emission-factors", headers=eng_, json=FACTOR).status_code == 403


def test_entry_lifecycle_with_four_eyes(client, setup):
    adm, mgr, eng_, fac = setup
    r = client.post(f"{API}/scope3", headers=eng_, json=body(description="Q3 flights"))
    assert r.status_code == 201, r.text
    e = r.json()
    assert (e["co2e"], e["status"], e["factorId"], e["unit"]) == (1.8, "Submitted", fac["id"], "passenger-km")
    # the author cannot decide; reject needs a comment; manager can
    assert client.post(f"{API}/scope3/{e['id']}/review", headers=eng_, json={"decision": "Approve"}).status_code == 403
    assert client.post(f"{API}/scope3/{e['id']}/review", headers=mgr, json={"decision": "Reject"}).status_code == 422
    rej = client.post(f"{API}/scope3/{e['id']}/review", headers=mgr, json={"decision": "Reject", "comment": "Check distance"}).json()
    assert rej["status"] == "Rejected" and rej["reviewComment"] == "Check distance"
    # author corrects -> resubmitted, review fields cleared
    up = client.put(f"{API}/scope3/{e['id']}", headers=eng_, json=body(activityValue=20000)).json()
    assert (up["status"], up["co2e"], up["reviewer"]) == ("Submitted", 3.0, None)
    ok = client.post(f"{API}/scope3/{e['id']}/review", headers=mgr, json={"decision": "Approve"}).json()
    assert ok["status"] == "Approved" and ok["reviewer"]
    # approved is final
    assert client.put(f"{API}/scope3/{e['id']}", headers=eng_, json=body()).status_code == 409
    assert client.delete(f"{API}/scope3/{e['id']}", headers=eng_).status_code == 409
    assert client.post(f"{API}/scope3/{e['id']}/review", headers=mgr, json={"decision": "Approve"}).status_code == 409


def test_validation_and_permissions(client, setup):
    adm, mgr, eng_, _ = setup
    assert client.post(f"{API}/scope3", headers=eng_, json=body(source="Unknown")).status_code == 422
    assert client.post(f"{API}/scope3", headers=eng_, json=body(activityValue=0)).status_code == 422
    assert client.post(f"{API}/scope3", headers=eng_, json=body(facilityId="NOPE")).status_code == 422
    assert client.post(f"{API}/scope3", headers=eng_, json=body(month="2030-01")).status_code == 422  # no such period
    assert client.post(f"{API}/scope3", headers=eng_, json=body(month="2026-01")).status_code == 409  # locked period
    e = client.post(f"{API}/scope3", headers=eng_, json=body()).json()
    assert client.post(f"{API}/scope3/{e['id']}/review", headers=eng_, json={"decision": "Approve"}).status_code == 403
    assert client.delete(f"{API}/scope3/{e['id']}", headers=mgr).status_code == 200  # manager may remove a pending one


def test_report_includes_approved_scope3_only(client, setup):
    adm, mgr, eng_, _ = setup
    a = client.post(f"{API}/scope3", headers=eng_, json=body()).json()
    client.post(f"{API}/scope3", headers=eng_, json=body(activityValue=100000))  # stays pending
    params = {"from": "2026-11", "to": "2026-11"}
    r0 = client.get(f"{API}/reports/inventory", headers=eng_, params=params).json()
    assert r0["summary"]["totals"]["scope3"] == 0 and "Under Review" in str(r0["summary"]["coverage"]["leftOut"])
    client.post(f"{API}/scope3/{a['id']}/review", headers=mgr, json={"decision": "Approve"})
    r1 = client.get(f"{API}/reports/inventory", headers=eng_, params=params).json()
    t = r1["summary"]["totals"]
    assert t["scope3"] == 1.8 and t["total"] == round(t["scope1"] + t["scope2"] + 1.8, 2)
    assert any("partial" in w for w in r1["warnings"])
    csv = client.get(f"{API}/reports/inventory.csv", headers=eng_, params=params).text
    assert any(line.count("Scope 3") and a["id"] in line for line in csv.splitlines())
    rp = client.get(f"{API}/reports/inventory", headers=eng_, params={**params, "basis": "pending"}).json()
    assert rp["summary"]["totals"]["scope3"] == pytest.approx(1.8 + 15.0)
    # facility filter excludes corporate (facility-less) entries
    fac = client.get(f"{API}/facilities", headers=eng_).json()[0]["id"]
    rf = client.get(f"{API}/reports/inventory", headers=eng_, params={**params, "facility_id": fac}).json()
    assert rf["summary"]["totals"]["scope3"] == 0


def test_targets_and_baseline_remain_scope_1_2(client, setup):
    adm, mgr, eng_, _ = setup
    before = client.get(f"{API}/targets", headers=mgr).json()
    a = client.post(f"{API}/scope3", headers=eng_, json=body()).json()
    client.post(f"{API}/scope3/{a['id']}/review", headers=mgr, json={"decision": "Approve"})
    assert client.get(f"{API}/targets", headers=mgr).json() == before


def test_factor_cited_by_a_scope3_entry_is_frozen(client, setup):
    adm, mgr, eng_, fac = setup
    client.post(f"{API}/scope3", headers=eng_, json=body())
    r = client.patch(f"{API}/emission-factors/{fac['id']}", headers=adm, json={"value": 9.9})
    assert r.status_code == 409 and "cited by" in r.json()["detail"]
    assert client.delete(f"{API}/emission-factors/{fac['id']}", headers=adm).status_code == 409
    # a new version is allowed and applies only from its date
    nv = client.post(f"{API}/emission-factors", headers=adm, json={**FACTOR, "value": 0.2, "validFrom": "2026-12-01"})
    assert nv.status_code == 201
