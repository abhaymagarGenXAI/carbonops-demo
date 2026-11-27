from tests.conftest import ENGINEER, auth_headers

API = "/api/v1"
BASE = dict(productionVolume=100, electricity=1000, diesel=10, naturalGas=50, steam=5, water=20,
            flareGas=1, methaneLeak=2, renewable=30, operatingHours=600, remarks="", notes="")


def _units(client, h):
    return next(f for f in client.get(f"{API}/facilities", headers=h).json() if f["id"] == "FAC-001")["units"]


def test_one_submission_carries_several_production_units_and_totals_them(client):
    h = auth_headers(client, ENGINEER)
    u = _units(client, h)
    assert len(u) >= 2
    body = {"facilityId": "FAC-001", "month": "2026-07", "status": "Draft", "unitData": [
        {"unit": u[0], "data": {**BASE, "remarks": "turnaround"}},
        {"unit": u[1], "data": {**BASE, "electricity": 500, "operatingHours": 700}},
    ]}
    r = client.post(f"{API}/submissions", headers=h, json=body)
    assert r.status_code == 200 or r.status_code == 201, r.text
    s = r.json()
    assert s["id"] == "SUB-MOF-202607" and s["unit"] == f"{u[0]}, {u[1]}" and len(s["unitData"]) == 2
    assert s["data"]["electricity"] == 1500 and s["data"]["diesel"] == 20 and s["data"]["operatingHours"] == 700
    assert s["data"]["remarks"] == f"{u[0]}: turnaround"
    # still exactly one submission for the facility + month, and the derived energy follows the TOTAL
    assert len([x for x in client.get(f"{API}/submissions", headers=h).json() if x["facilityId"] == "FAC-001" and x["month"] == "2026-07"]) == 1
    # saving again replaces the unit lines (no duplicates)
    body["unitData"] = body["unitData"][:1]
    s2 = client.post(f"{API}/submissions", headers=h, json={**body, "revision": s["revision"]}).json()
    assert s2["unit"] == u[0] and s2["data"]["electricity"] == 1000 and len(s2["unitData"]) == 1


def test_unit_validation_and_legacy_single_unit_form(client):
    h = auth_headers(client, ENGINEER)
    u = _units(client, h)
    mk = lambda lines: {"facilityId": "FAC-001", "month": "2026-07", "status": "Draft", "unitData": lines}
    assert client.post(f"{API}/submissions", headers=h, json=mk([{"unit": "Nope", "data": BASE}])).status_code == 422
    assert client.post(f"{API}/submissions", headers=h, json=mk([{"unit": u[0], "data": BASE}, {"unit": u[0], "data": BASE}])).status_code == 422
    assert client.post(f"{API}/submissions", headers=h, json={"facilityId": "FAC-001", "month": "2026-07", "status": "Draft"}).status_code == 422
    r = client.post(f"{API}/submissions", headers=h, json={"facilityId": "FAC-001", "month": "2026-07", "status": "Draft", "unit": u[2], "data": BASE})
    assert r.status_code in (200, 201) and r.json()["unit"] == u[2] and r.json()["data"]["electricity"] == 1000
    assert r.json()["unitData"][0]["unit"] == u[2]
