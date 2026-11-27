import io

from openpyxl import Workbook, load_workbook

from app.services import master_import as mi
from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers

API = "/api/v1/master-data"
XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _book(facilities=None, assets=None, fac_header=None, ast_header=None) -> bytes:
    wb = Workbook()
    wf = wb.active
    wf.title = "Facilities"
    wf.append(fac_header or [h for _, h, _ in mi.FAC_COLS])
    for r in facilities or []:
        wf.append(r)
    wa = wb.create_sheet("Assets")
    wa.append(ast_header or [h for _, h, _ in mi.AST_COLS])
    for r in assets or []:
        wa.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


FAC = ["NEW1", "Nova Plant", "West", "Processing Plant", "A. Rao", "Unit A; Unit B", "2012-04-01", 120]
AST = [None, "NEW1", "Nova Boiler", "Unit A", "Boiler", "operational", "Natural Gas", 700, "K. Iyer", "01-01-2026", "scope 1", "Stationary Combustion", "40 TPH"]


def _post(client, h, content, dry=True, name="x.xlsx"):
    return client.post(f"{API}/import", headers=h, data={"dryRun": str(dry).lower()}, files={"file": (name, content, XL)})


def test_template_and_export_are_admin_and_signed_in_gated_and_round_trip(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    assert client.get(f"{API}/template").status_code == 401
    assert client.get(f"{API}/template", headers=eng).status_code == 403
    t = client.get(f"{API}/template", headers=adm)
    assert t.status_code == 200 and "spreadsheetml" in t.headers["content-type"]
    wb = load_workbook(io.BytesIO(t.content))
    assert wb.sheetnames == ["Instructions", "Facilities", "Assets"] and wb["Facilities"]["A1"].value.startswith("Facility code")
    # export is readable by any signed-in user and lists every facility and asset
    ex = client.get(f"{API}/export", headers=eng)
    assert ex.status_code == 200
    wb = load_workbook(io.BytesIO(ex.content))
    n_f, n_a = len(client.get("/api/v1/facilities", headers=eng).json()), len(client.get("/api/v1/assets", headers=eng).json())
    assert wb["Facilities"].max_row == n_f + 1 and wb["Assets"].max_row == n_a + 1
    # the export can be uploaded unchanged: all rows are updates, none invalid
    rep = _post(client, adm, ex.content).json()
    assert rep["canApply"] is True and rep["summary"]["Facilities"]["error"] == 0 and rep["summary"]["Assets"]["error"] == 0
    assert rep["summary"]["Facilities"]["update"] == n_f and rep["summary"]["Assets"]["update"] == n_a


def test_upload_is_admin_only_and_dry_run_writes_nothing(client):
    adm, mgr = auth_headers(client, ADMIN), auth_headers(client, MANAGER)
    book = _book([FAC], [AST])
    assert _post(client, mgr, book).status_code == 403
    before = len(client.get("/api/v1/facilities", headers=adm).json())
    rep = _post(client, adm, book, dry=True).json()
    assert rep["applied"] is False and rep["canApply"] is True
    assert rep["summary"]["Facilities"]["create"] == 1 and rep["summary"]["Assets"]["create"] == 1
    assert len(client.get("/api/v1/facilities", headers=adm).json()) == before


def test_apply_creates_facility_units_and_assets_and_updates_existing(client):
    adm = auth_headers(client, ADMIN)
    rep = _post(client, adm, _book([FAC], [AST]), dry=False).json()
    assert rep["applied"] is True
    f = next(x for x in client.get("/api/v1/facilities", headers=adm).json() if x["code"] == "NEW1")
    assert f["name"] == "Nova Plant" and f["units"] == ["Unit A", "Unit B"] and f["employees"] == 120
    a = next(x for x in client.get("/api/v1/assets", headers=adm).json() if x["name"] == "Nova Boiler")
    assert a["facilityId"] == f["id"] and a["id"].startswith("NEW1-AST-") and a["status"] == "Operational"
    assert a["carbonCategory"] == "Scope 1" and a["lastInspection"] == "2026-01-01"
    assert client.get("/api/v1/audit", headers=adm).json()[0]["action"] == "Imported"
    # second upload: same facility code + the asset id -> updates, not duplicates
    fac2 = [*FAC[:4], "New Manager", *FAC[5:]]
    ast2 = [a["id"], *AST[1:2], "Nova Boiler", *AST[3:7], 500, *AST[8:]]
    rep = _post(client, adm, _book([fac2], [ast2]), dry=False).json()
    assert rep["applied"] and rep["summary"]["Facilities"]["update"] == 1 and rep["summary"]["Assets"]["update"] == 1
    assert len([x for x in client.get("/api/v1/facilities", headers=adm).json() if x["code"] == "NEW1"]) == 1
    assert client.get(f"/api/v1/assets/{a['id']}", headers=adm).json()["operatingHours"] == 500
    assert next(x for x in client.get("/api/v1/facilities", headers=adm).json() if x["code"] == "NEW1")["manager"] == "New Manager"


def test_any_invalid_row_blocks_everything_and_is_reported_with_its_row(client):
    adm = auth_headers(client, ADMIN)
    before = (len(client.get("/api/v1/facilities", headers=adm).json()), len(client.get("/api/v1/assets", headers=adm).json()))
    bad_assets = [
        [None, "NEW1", "Ok asset", "Unit A", "Boiler", "Operational", "Natural Gas", 1, "E", "2026-01-01", "Scope 1", "Stationary Combustion", "1"],
        [None, "NOPE", "Orphan", "Unit A", "Boiler", "Operational", "Natural Gas", 1, "E", "2026-01-01", "Scope 1", "Stationary Combustion", "1"],
        [None, "NEW1", "Wrong unit", "Unit Z", "Boiler", "Broken", "Natural Gas", "abc", "E", "yesterday", "Scope 9", "Stationary Combustion", "1"],
    ]
    rep = _post(client, adm, _book([FAC, FAC], bad_assets), dry=False).json()
    assert rep["applied"] is False and rep["canApply"] is False
    errs = {(r["sheet"], r["row"]): " | ".join(r["errors"]) for r in rep["rows"] if r["errors"]}
    assert "more than once" in errs[("Facilities", 3)] and ("Facilities", 2) not in errs
    assert "not an existing facility" in errs[("Assets", 3)]
    e = errs[("Assets", 4)]
    assert "Unit Z" in e and "Status" in e and "Operating hours" in e and "date" in e and "Scope 9" in e
    assert ("Assets", 2) not in errs
    assert (len(client.get("/api/v1/facilities", headers=adm).json()), len(client.get("/api/v1/assets", headers=adm).json())) == before  # nothing saved


def test_units_in_use_cannot_be_dropped_and_bad_files_are_refused(client):
    adm = auth_headers(client, ADMIN)
    f = client.get("/api/v1/facilities", headers=adm).json()[0]
    row = [f["code"], f["name"], f["region"], f["type"], f["manager"], f["units"][0], f["commissioned"], f["employees"]]
    rep = _post(client, adm, _book([row])).json()
    assert rep["canApply"] is False and "still in use" in rep["rows"][0]["errors"][0]
    assert _post(client, adm, b"not a workbook").status_code == 422
    assert _post(client, adm, b"a,b\n1,2", name="x.csv").status_code == 422
    missing = _book([["X"]], fac_header=["Facility code*"])
    assert _post(client, adm, missing).status_code == 422
    wb = Workbook(); wb.active.title = "Other"; b = io.BytesIO(); wb.save(b)
    assert _post(client, adm, b.getvalue()).status_code == 422


def test_multi_unit_submission_does_not_block_unit_list_edits(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    fac = next(f for f in client.get("/api/v1/facilities", headers=eng).json() if f["id"] == "FAC-001")
    u = fac["units"]
    base = dict(productionVolume=1, electricity=1, diesel=1, naturalGas=1, steam=1, water=1, flareGas=0, methaneLeak=0, renewable=0, operatingHours=100, remarks="", notes="")
    r = client.post("/api/v1/submissions", headers=eng, json={"facilityId": "FAC-001", "month": "2026-07", "status": "Draft",
                                                              "unitData": [{"unit": u[0], "data": base}, {"unit": u[1], "data": base}]})
    assert r.status_code in (200, 201), r.text
    ok = client.patch("/api/v1/facilities/FAC-001", headers=adm, json={"units": [*u, "Extra Unit"]})
    assert ok.status_code == 200, ok.text
    assert client.patch("/api/v1/facilities/FAC-001", headers=adm, json={"units": [u[0]]}).status_code == 409  # u[1] still used
