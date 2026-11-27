"""Stage 2: production units, asset types, UoM, energy streams, emission sources and versioned factors."""
from decimal import Decimal

from app.db import collections as C
from app.services import carbon_engine as ce
from app.services import masters
from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, open_periods

API = "/api/v1"
DATA = {"productionVolume": 1000, "electricity": 50000, "diesel": 2000, "naturalGas": 1000, "steam": 500, "water": 100,
        "flareGas": 10, "methaneLeak": 1, "renewable": 0, "operatingHours": 700}


def test_seeded_masters_exist_and_are_consistent(db):
    assert db[C.PRODUCTION_UNITS].count_documents({}) == 12            # 4 facilities x 3 units
    assert db[C.ENERGY_STREAMS].count_documents({}) == 5
    assert {s["sourceName"] for s in db[C.EMISSION_SOURCES].find({"isSystem": True})} == {s.name for s in ce.SOURCES}
    assert db[C.UNITS_OF_MEASURE].count_documents({}) == 9
    assert db[C.ASSET_TYPES].count_documents({}) == 10
    assert masters.verify(db) == {}                                    # no orphan/unlinked reference anywhere
    el = db[C.EMISSION_SOURCES].find_one({"sourceName": "Purchased Electricity"})
    assert el["energyStreamId"] == db[C.ENERGY_STREAMS].find_one({"streamName": "Electricity"})["streamId"]


def test_migration_from_pre_stage2_data_keeps_every_figure_and_is_idempotent(db):
    before = masters.total_co2e(db)
    n_records = db[C.EMISSION_RECORDS].count_documents({})
    for coll, fields in [(C.EMISSION_RECORDS, ["emissionSourceId", "factorVersionId"]), (C.SCOPE3_ENTRIES, ["emissionSourceId", "factorVersionId"]),
                         (C.EMISSION_FACTORS, ["emissionSourceId", "validTo"]), (C.ENERGY_RECORDS, ["energyStreamId"]),
                         (C.ASSETS, ["unitId", "assetTypeId", "energyStreamId"]), (C.SUBMISSIONS, ["unitId"])]:
        db[coll].update_many({}, {"$unset": {f: "" for f in fields}})
    for coll in (C.PRODUCTION_UNITS, C.ASSET_TYPES, C.ENERGY_STREAMS, C.EMISSION_SOURCES, C.UNITS_OF_MEASURE):
        db[coll].delete_many({})
    assert masters.verify(db)                                           # clearly "pre-Stage-2"
    made = masters.ensure_masters(db)
    assert made["productionUnits"] == 12 and made["factorsLinked"] > 0 and made["assetsLinked"] > 0
    assert masters.verify(db) == {}
    assert masters.total_co2e(db) == before                             # reconciliation: tCO2e identical before and after
    assert db[C.EMISSION_RECORDS].count_documents({}) == n_records
    assert masters.ensure_masters(db) == {}                             # second run changes nothing


def test_factor_versions_have_validity_ranges(client, db):
    ele = {f["factorId"]: f for f in db[C.EMISSION_FACTORS].find({"source": "Purchased Electricity"})}
    assert ele["EF-07"]["validTo"] == "2026-04-01" and ele["EF-05"]["validTo"] is None   # half-open [validFrom, validTo)
    assert ele["EF-05"]["emissionSourceId"] == ele["EF-07"]["emissionSourceId"]
    adm = auth_headers(client, ADMIN)
    body = {"source": "Purchased Electricity", "scope": "Scope 2", "value": 0.7, "unit": "kgCO₂e/kWh", "reference": "CEA v20",
            "validFrom": "2026-09-01", "status": "Active"}
    r = client.post(f"{API}/emission-factors", headers=adm, json=body)
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["emissionSourceId"] == ele["EF-05"]["emissionSourceId"] and new["validTo"] is None
    old = {f["id"]: f for f in client.get(f"{API}/emission-factors", headers=adm).json()}
    assert old["EF-05"]["validTo"] == "2026-09-01" and old["EF-05"]["status"] == "Superseded"
    assert client.post(f"{API}/emission-factors", headers=adm, json=body).status_code == 409   # same source + validFrom
    assert client.delete(f"{API}/emission-factors/{new['id']}", headers=adm).status_code == 200
    assert {f["id"]: f for f in client.get(f"{API}/emission-factors", headers=adm).json()}["EF-05"]["validTo"] is None
    assert masters.verify(db) == {}


def test_factor_is_selected_by_source_id_even_if_the_name_differs():
    fs = [{"id": "F1", "source": "Old name", "emissionSourceId": "SRC-X", "validFrom": "2026-01-01", "scope": "Scope 3", "value": 1, "unit": "kgCO₂e/INR", "reference": "r"},
          {"id": "F2", "source": "Other", "emissionSourceId": "SRC-Y", "validFrom": "2026-01-01", "scope": "Scope 3", "value": 2, "unit": "kgCO₂e/INR", "reference": "r"}]
    assert ce.select_factor(fs, "New name", "2026-03", "SRC-X")[0]["id"] == "F1"
    assert ce.select_factor(fs, "Old name", "2026-03")[0]["id"] == "F1"          # name fallback when no id is known
    assert ce.select_factor(fs, "Old name", "2026-03", "SRC-Y")[0]["id"] == "F2"


def test_new_records_carry_master_links(client, db):
    eng, mgr, adm = auth_headers(client, ENGINEER), auth_headers(client, MANAGER), auth_headers(client, ADMIN)
    open_periods(client, "2026-08")
    r = client.post(f"{API}/submissions", headers=eng, json={"facilityId": "FAC-001", "unit": "Bombay High North", "month": "2026-08", "status": "Submitted", "data": DATA})
    assert r.status_code == 200, r.text
    sub = db[C.SUBMISSIONS].find_one({"submissionId": "SUB-MOF-202608"})
    assert sub["unitId"] == masters.unit_id(db, "FAC-001", "Bombay High North")
    recs = list(db[C.EMISSION_RECORDS].find({"submissionId": "SUB-MOF-202608"}))
    assert len(recs) == 6 and all(x["emissionSourceId"] and x["factorVersionId"] == x["factorId"] for x in recs)
    assert {x["source"]: x["emissionSourceId"] for x in recs} == {s["sourceName"]: s["sourceId"] for s in db[C.EMISSION_SOURCES].find({"isSystem": True})}
    assert all(e["energyStreamId"] for e in db[C.ENERGY_RECORDS].find({"facilityId": "FAC-001", "month": "2026-08"}))
    # Scope 3: factor -> source is created on first use and entries cite both ids
    f = client.post(f"{API}/emission-factors", headers=adm, json={"source": "Taxi spend", "scope": "Scope 3", "value": 0.2, "unit": "kgCO₂e/INR",
                                                                  "reference": "Test ref", "validFrom": "2026-01-01", "status": "Active", "category": "6 Business travel"})
    assert f.status_code == 201, f.text
    e = client.post(f"{API}/scope3", headers=mgr, json={"month": "2026-08", "category": "6 Business travel", "source": "Taxi spend", "activityValue": 1000, "description": "taxis"})
    assert e.status_code == 201, e.text
    row = db[C.SCOPE3_ENTRIES].find_one({"entryId": e.json()["id"]})
    assert row["factorVersionId"] == f.json()["id"] and row["emissionSourceId"] == f.json()["emissionSourceId"]
    assert masters.verify(db) == {}


def test_facility_units_follow_production_units(client, db):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    f = client.post(f"{API}/facilities", headers=adm, json={"code": "ZZZ", "name": "Temp Plant", "region": "West", "type": "Plant", "manager": "X",
                                                           "employees": 1, "commissioned": "2020-01-01", "units": ["U1", "U2"]})
    assert f.status_code == 201, f.text
    fid = f.json()["id"]
    units = {u["unitName"]: u["unitId"] for u in client.get(f"{API}/production-units?facilityId={fid}", headers=eng).json()}
    assert set(units) == {"U1", "U2"}
    assert client.patch(f"{API}/facilities/{fid}", headers=adm, json={"units": ["U1", "U2", "U3"]}).status_code == 200
    now = {u["unitName"]: u["unitId"] for u in client.get(f"{API}/production-units?facilityId={fid}", headers=eng).json()}
    assert set(now) == {"U1", "U2", "U3"} and now["U1"] == units["U1"]          # surviving units keep their ids
    assert client.patch(f"{API}/facilities/{fid}", headers=adm, json={"units": ["U1", "U3"]}).status_code == 200
    assert {u["unitName"] for u in client.get(f"{API}/production-units?facilityId={fid}", headers=eng).json()} == {"U1", "U3"}
    assert client.delete(f"{API}/facilities/{fid}", headers=adm).status_code == 405


def test_asset_links_to_unit_type_and_stream(client, db):
    adm = auth_headers(client, ADMIN)
    body = {"facilityId": "FAC-001", "name": "New Chiller", "unit": "Bombay High North", "type": "Chiller Plant", "status": "Operational",
            "energySource": "Electricity", "operatingHours": 10, "engineer": "K. Iyer", "lastInspection": "2026-01-01",
            "carbonCategory": "Scope 2", "emissionSourceType": "Purchased Electricity", "capacity": "5 MW"}
    r = client.post(f"{API}/assets", headers=adm, json=body)
    assert r.status_code == 201, r.text
    a = db[C.ASSETS].find_one({"assetId": r.json()["id"]})
    assert a["unitId"] == masters.unit_id(db, "FAC-001", "Bombay High North")
    assert db[C.ASSET_TYPES].find_one({"assetTypeId": a["assetTypeId"]})["typeName"] == "Chiller Plant"     # new type is added, not rejected
    assert a["energyStreamId"] == db[C.ENERGY_STREAMS].find_one({"streamName": "Electricity"})["streamId"]
    r2 = client.patch(f"{API}/assets/{r.json()['id']}", headers=adm, json={"energySource": "Process Gas", "type": "Boiler"})
    a = db[C.ASSETS].find_one({"assetId": r.json()["id"]})
    assert a["energyStreamId"] is None                                           # free-text sources are not guessed
    assert db[C.ASSET_TYPES].find_one({"assetTypeId": a["assetTypeId"]})["typeName"] == "Boiler"
    assert masters.verify(db) == {}


def test_master_listing_endpoints(client):
    eng = auth_headers(client, ENGINEER)
    for path, n in [("production-units", 12), ("energy-streams", 5), ("units-of-measure", 9), ("asset-types", 10)]:
        r = client.get(f"{API}/{path}", headers=eng)
        assert r.status_code == 200 and len(r.json()) >= n, path
    srcs = client.get(f"{API}/emission-sources", headers=eng).json()
    assert {s["scope"] for s in srcs} >= {"Scope 1", "Scope 2", "Scope 3"}
    assert client.get(f"{API}/emission-sources").status_code == 401
