from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers

API = "/api/v1"
BASE = dict(productionVolume=1, electricity=1, diesel=1, naturalGas=1, steam=1, water=1, flareGas=0, methaneLeak=0, renewable=0,
            operatingHours=100, remarks="", notes="")
NEW = {"code": "ZZZ", "name": "Temp Plant", "region": "West", "type": "Plant", "manager": "X", "employees": 1, "commissioned": "2020-01-01", "units": ["U1"]}


def _asset(fid):
    return {"facilityId": fid, "name": "A", "unit": "U1", "type": "Boiler", "status": "Operational", "energySource": "Natural Gas", "operatingHours": 1,
            "engineer": "E", "lastInspection": "2026-01-01", "carbonCategory": "Scope 1", "emissionSourceType": "Stationary Combustion", "capacity": "1"}


def test_there_is_no_delete_and_deactivate_needs_permission(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    assert client.delete(f"{API}/facilities/FAC-001", headers=adm).status_code == 405
    fid = client.post(f"{API}/facilities", headers=adm, json=NEW).json()["id"]
    assert client.post(f"{API}/facilities/{fid}/deactivate", headers=eng).status_code == 403
    assert client.post(f"{API}/facilities/NOPE/deactivate", headers=adm).status_code == 404


def test_deactivate_keeps_history_hides_from_entry_and_is_reversible(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    fid = client.post(f"{API}/facilities", headers=adm, json=NEW).json()["id"]
    assert client.get(f"{API}/facilities/{fid}", headers=adm).json()["active"] is True
    assert client.post(f"{API}/assets", headers=adm, json=_asset(fid)).status_code == 201
    r = client.post(f"{API}/facilities/{fid}/deactivate", headers=adm)
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["deactivatedBy"]
    assert client.get(f"{API}/audit", headers=adm).json()[0]["action"] == "Deactivated"
    # history stays readable
    assert fid in {f["id"] for f in client.get(f"{API}/facilities", headers=eng).json()}
    assert len(client.get(f"{API}/assets?facility_id={fid}", headers=eng).json()) == 1
    # but no new data can be added
    assert client.post(f"{API}/assets", headers=adm, json=_asset(fid)).status_code == 409
    assert client.post(f"{API}/submissions", headers=eng, json={"facilityId": fid, "month": "2026-07", "status": "Draft", "unitData": [{"unit": "U1", "data": BASE}]}).status_code == 409
    assert client.post(f"{API}/initiatives", headers=adm, json={"facilityId": fid, "name": "x", "category": "Energy Efficiency", "owner": "o", "capex": 1, "annualSaving": 1, "emissionReduction": 1, "targetDate": "2027-01-01", "start": "2026-01-01"}).status_code in (409, 422)
    # an asset of another facility cannot be moved into it
    other = client.get(f"{API}/assets?facility_id=FAC-001", headers=adm).json()[0]
    assert client.patch(f"{API}/assets/{other['id']}", headers=adm, json={"facilityId": fid}).status_code == 409
    # reactivate
    r = client.post(f"{API}/facilities/{fid}/reactivate", headers=adm)
    assert r.json()["active"] is True and r.json()["deactivatedAt"] is None
    assert client.post(f"{API}/assets", headers=adm, json=_asset(fid)).status_code == 201


def test_cannot_deactivate_while_drafts_would_be_stranded(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    u = next(f for f in client.get(f"{API}/facilities", headers=eng).json() if f["id"] == "FAC-001")["units"][0]
    s = client.post(f"{API}/submissions", headers=eng, json={"facilityId": "FAC-001", "month": "2026-07", "status": "Draft", "unitData": [{"unit": u, "data": BASE}]})
    assert s.status_code in (200, 201), s.text
    r = client.post(f"{API}/facilities/FAC-001/deactivate", headers=adm)
    assert r.status_code == 409 and "SUB-MOF-202607" in r.json()["detail"]
    assert client.get(f"{API}/facilities/FAC-001", headers=adm).json()["active"] is True


def test_deactivated_facility_leaves_alerts_and_period_lock_checks_and_excel_upload_cannot_add_assets(client):
    import io
    from openpyxl import Workbook

    adm, mgr = auth_headers(client, ADMIN), auth_headers(client, MANAGER)
    fid = client.post(f"{API}/facilities", headers=adm, json=NEW).json()["id"]
    client.post(f"{API}/facilities/{fid}/deactivate", headers=adm)
    from app.services import master_import as mi
    wb = Workbook(); wf = wb.active; wf.title = "Facilities"; wf.append([h for _, h, _ in mi.FAC_COLS])
    wa = wb.create_sheet("Assets"); wa.append([h for _, h, _ in mi.AST_COLS])
    wa.append([None, "ZZZ", "Late asset", "U1", "Boiler", "Operational", "Natural Gas", 1, "E", "2026-01-01", "Scope 1", "Stationary Combustion", "1"])
    b = io.BytesIO(); wb.save(b)
    rep = client.post(f"{API}/master-data/import", headers=adm, data={"dryRun": "true"}, files={"file": ("x.xlsx", b.getvalue(), "application/octet-stream")}).json()
    assert rep["canApply"] is False and "deactivated" in rep["rows"][0]["errors"][0]
    assert not any("Temp Plant" in a["title"] for a in client.get(f"{API}/alerts", headers=mgr).json())
