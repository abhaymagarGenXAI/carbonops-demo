import datetime as dt
import io

import pytest
from fastapi import HTTPException

from app.services import importer as imp
from tests.conftest import ENGINEER, MANAGER, auth_headers, open_periods

API = "/api/v1"
HEAD = "facility,unit,month,production_volume,electricity,diesel,natural_gas,steam,water,flare_gas,methane_leak,renewable,operating_hours,remarks"
OK = "KG Basin,Vashishta Field,2026-07,1000,6120000,172400,2980000,44800,198000,88600,392,298000,700,from meter"


def _csv(*rows, head=HEAD):
    return ("\n".join([head, *rows]) + "\n").encode()


def _preview(client, h, content, name="in.csv", **form):
    return client.post(f"{API}/submissions/import/preview", headers=h, data=form, files={"file": (name, content)})


def _xlsx(rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


# ------------------------------------------------------------------ pure parsing
def test_number_parsing():
    assert imp.parse_number("6,120,000") == 6120000 and imp.parse_number("61,20,000") == 6120000
    assert imp.parse_number(" 1 234.5 ") == 1234.5 and imp.parse_number(7) == 7.0
    for bad in ("", None, "abc", "1e999", "inf", "#DIV/0!", True):
        with pytest.raises(ValueError):
            imp.parse_number(bad)


def test_month_parsing_and_header_aliases():
    assert imp.parse_month("2026-07") == "2026-07" and imp.parse_month("2026/7".replace("/7", "/07")) == "2026-07"
    assert imp.parse_month(dt.datetime(2026, 7, 1)) == "2026-07" and imp.parse_month("2026-07-15") == "2026-07"
    for bad in ("July 2026", "2026-13", "07-2026", ""):
        with pytest.raises(ValueError):
            imp.parse_month(bad)
    cols, unmapped = imp.map_columns(["Facility", "Natural Gas (SCM)", "Electricity_kWh", "Diesel (L)", "Mystery", "diesel"])
    assert cols["natural_gas"] == 1 and cols["electricity"] == 2 and cols["diesel"] == 3
    assert unmapped == ["Mystery", "diesel"]  # unknown + duplicate are reported, never silently used


def test_read_table_limits_and_file_types():
    with pytest.raises(HTTPException):
        imp.read_table("a.xls", b"x", 10)
    with pytest.raises(HTTPException):
        imp.read_table("a.csv", b"\n\n", 10)
    with pytest.raises(HTTPException):
        imp.read_table("a.csv", b"a,b\n", 10)  # header only
    with pytest.raises(HTTPException) as e:
        imp.read_table("a.csv", b"a,b\n1,2\n3,4\n5,6\n", 2)
    assert "limit" in e.value.detail
    h, rows, _ = imp.read_table("a.csv", "a;b\n1;2\n".encode(), 5)  # semicolon (European Excel) + row numbers
    assert h == ["a", "b"] and rows == [(2, ["1", "2"])]


# ------------------------------------------------------------------ preview
def test_preview_valid_csv_writes_nothing(client):
    eng = auth_headers(client, ENGINEER)
    before = client.get(f"{API}/submissions", headers=eng).json()
    r = _preview(client, eng, _csv(OK))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["rowCount"] == 1 and p["importableRows"] == 1 and p["errorRows"] == 0 and p["sheet"] is None
    row = p["rows"][0]
    assert row["importable"] and row["row"] == 2 and row["facilityId"] == "FAC-004" and row["unit"] == "Vashishta Field"
    assert row["data"]["electricity"] == 6120000 and row["data"]["remarks"] == "from meter"
    assert client.get(f"{API}/submissions", headers=eng).json() == before  # preview is read-only


def test_preview_reports_every_kind_of_row_error(client):
    eng = auth_headers(client, ENGINEER)
    rows = [
        OK,  # row 2 ok
        "Nowhere,X,2026-07,1,1,1,1,1,1,1,1,1,1,",  # unknown facility
        "KG Basin,Nope,2026-07,1,1,1,1,1,1,1,1,1,1,",  # bad unit
        "KG Basin,,2026-07,1,1,1,1,1,1,1,1,1,1,",  # unit required (3 units)
        "KG Basin,Vashishta Field,July,1,1,1,1,1,1,1,1,1,1,",  # bad month
        "Hazira Processing Plant,LPG Train A,2026-03,1,1,1,1,1,1,1,1,1,1,",  # locked period
        "Hazira Processing Plant,LPG Train A,2026-09,1,1,1,1,1,1,1,1,1,1,",  # period not opened
        "Assam Asset,Geleki CTF,2026-07,1,abc,1,1,1,1,1,1,1,1,",  # not a number
        "Assam Asset,Geleki CTF,2026-07,1,,1,1,1,1,1,1,1,1,",  # missing (never defaulted to 0)
        "Assam Asset,Geleki CTF,2026-07,1,1,-5,1,1,1,1,1,1,1,",  # negative
        "Assam Asset,Geleki CTF,2026-07,1,1,1,1,1,1,1,1,1,800,",  # hours > 744
        OK,  # duplicate of row 2
    ]
    p = _preview(client, eng, _csv(*rows)).json()
    errs = {r["row"]: " | ".join(r["errors"]) for r in p["rows"]}
    assert p["importableRows"] == 1 and p["errorRows"] == 11
    assert "not found" in errs[3] and "not a unit of KG Basin" in errs[4] and "Unit is required" in errs[5]
    assert "not a month" in errs[6] and "locked" in errs[7] and "does not exist" in errs[8]
    assert "Electricity" in errs[9] and "not a number" in errs[9]
    assert "Electricity: value is missing" in errs[10]
    assert "Diesel" in errs[11] and "Operating hours" in errs[12] and "Duplicate" in errs[13]
    assert all(not r["importable"] for r in p["rows"][1:])


def test_preview_existing_submission_rules_and_anomaly_warnings(client):
    eng = auth_headers(client, ENGINEER)
    approved = "Mumbai Offshore,Bombay High North,2026-06,1,1,1,1,1,1,1,1,1,1,"  # SUB-MOF-202606 is Approved
    hzr = "Hazira Processing Plant,LPG Train A,2026-06,1,1,1,1,1,1,1,1,1,1,"  # under review
    p = _preview(client, eng, _csv(approved, hzr)).json()
    assert "already approved" in p["rows"][0]["errors"][0] and p["rows"][0]["existingStatus"] == "Approved"
    assert p["rows"][1]["importable"] is True and p["rows"][1]["existingStatus"] == "Under Review"
    assert any("Replaces SUB-HZR-202606" in w and "Under Review" in w for w in p["rows"][1]["warnings"])
    spike = "KG Basin,Vashishta Field,2026-07,1,99999999,1,1,1,1,1,1,1,1,"
    row = _preview(client, eng, _csv(spike)).json()["rows"][0]
    assert row["importable"] and any("Electricity" in w and "above" in w for w in row["warnings"])  # same engine as submissions


def test_preview_defaults_missing_column_and_unmapped(client):
    eng = auth_headers(client, ENGINEER)
    no_ctx = "production_volume,electricity,diesel,natural_gas,steam,water,flare_gas,methane_leak,renewable,operating_hours,Extra"
    body = _csv("1,1,1,1,1,1,1,1,1,1,zzz", head=no_ctx)
    r = _preview(client, eng, body)
    assert r.status_code == 422 and "facility" in r.json()["detail"] and "month" in r.json()["detail"]
    r = _preview(client, eng, body, facilityId="FAC-004", month="2026-07")  # supplied from the form instead
    p = r.json()
    assert r.status_code == 200 and p["unmappedColumns"] == ["Extra"] and p["rows"][0]["errors"] == ["Unit is required for KG Basin (valid: Cluster-2 Onshore Terminal, Vashishta Field, S1 Process Unit)"]
    r = _preview(client, eng, _csv(OK, head=HEAD.replace(",diesel", "")))
    assert r.status_code == 422 and "diesel" in r.json()["detail"]
    assert _preview(client, eng, b"x", name="a.xls").status_code == 422
    assert _preview(client, eng, b"not a zip", name="a.xlsx").status_code == 422


def test_preview_xlsx_with_excel_date_and_numbers(client):
    eng = auth_headers(client, ENGINEER)
    rows = [HEAD.split(","), ["KG Basin", "Vashishta Field", dt.datetime(2026, 7, 1), 1000, 6120000, 172400, 2980000, 44800, 198000, 88600, 392, 298000, 700, None]]
    p = _preview(client, eng, _xlsx(rows), name="plan.xlsx").json()
    assert p["sheet"] and p["importableRows"] == 1 and p["rows"][0]["month"] == "2026-07"


def test_preview_and_commit_permissions(client):
    mgr = auth_headers(client, MANAGER)
    assert _preview(client, mgr, _csv(OK)).status_code == 403
    row = {"facilityId": "FAC-004", "unit": "Vashishta Field", "month": "2026-07", "data": {k: 1 for k in (
        "productionVolume", "electricity", "diesel", "naturalGas", "steam", "water", "flareGas", "methaneLeak", "renewable", "operatingHours")}}
    assert client.post(f"{API}/submissions/import", headers=mgr, json={"rows": [row]}).status_code == 403
    assert client.post(f"{API}/submissions/import/preview", files={"file": ("a.csv", b"x")}).status_code == 401


def test_template_has_every_importable_column(client):
    eng = auth_headers(client, ENGINEER)
    r = client.get(f"{API}/submissions/import/template", headers=eng)
    assert r.status_code == 200 and r.text.strip().split(",") == HEAD.split(",")[:-1] + ["remarks", "notes"]
    cols, unmapped = imp.map_columns(r.text.strip().split(","))
    assert not unmapped and len(cols) == 15


# ------------------------------------------------------------------ commit
def test_commit_saves_through_normal_path_with_emissions_and_reports_failures(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    open_periods(client, "2026-08")
    p = _preview(client, eng, _csv(OK, OK.replace("2026-07", "2026-08"))).json()
    rows = [{"facilityId": r["facilityId"], "unit": r["unit"], "month": r["month"], "data": r["data"]} for r in p["rows"]]
    rows.append({**rows[0], "month": "2026-03"})  # locked -> fails alone, others still saved
    res = client.post(f"{API}/submissions/import", headers=eng, json={"status": "Submitted", "rows": rows}).json()
    assert res["saved"] == 2 and res["failed"] == 1
    assert [x["ok"] for x in res["results"]] == [True, True, False]
    assert "locked" in res["results"][2]["detail"]
    sub = client.get(f"{API}/submissions/SUB-KGB-202607", headers=eng).json()
    assert sub["status"] == "Submitted" and sub["data"]["electricity"] == 6120000 and sub["submittedBy"]
    em = client.get(f"{API}/emission-records", headers=mgr, params={"facility_id": "FAC-004", "month": "2026-08"}).json()
    assert len(em) == 6  # emissions were calculated, same as a manual submission
    en = client.get(f"{API}/energy-records", headers=eng, params={"facility_id": "FAC-004", "month": "2026-08"}).json()
    assert len(en) == 5
    assert client.get(f"{API}/audit", headers=eng).json()[0]["action"] == "Imported"


def test_commit_as_draft_and_schema_rejection(client):
    eng = auth_headers(client, ENGINEER)
    p = _preview(client, eng, _csv(OK)).json()["rows"][0]
    row = {"facilityId": p["facilityId"], "unit": p["unit"], "month": p["month"], "data": p["data"]}
    res = client.post(f"{API}/submissions/import", headers=eng, json={"rows": [row]}).json()  # default status Draft
    assert res["saved"] == 1 and client.get(f"{API}/submissions/SUB-KGB-202607", headers=eng).json()["status"] == "Draft"
    bad = {**row, "data": {**row["data"], "electricity": -1}}
    assert client.post(f"{API}/submissions/import", headers=eng, json={"rows": [bad]}).status_code == 422
    assert client.post(f"{API}/submissions/import", headers=eng, json={"rows": []}).status_code == 422


def test_several_unit_rows_of_one_facility_month_become_one_multi_unit_submission(client):
    eng = auth_headers(client, ENGINEER)
    open_periods(client, "2026-08")
    units = next(f for f in client.get(f"{API}/facilities", headers=eng).json() if f["id"] == "FAC-004")["units"]
    assert len(units) >= 2
    a = OK.replace("Vashishta Field", units[0]).replace("2026-07", "2026-08")
    b = OK.replace("Vashishta Field", units[1]).replace("2026-07", "2026-08")
    p = _preview(client, eng, _csv(a, b)).json()
    assert p["importableRows"] == 2 and p["errorRows"] == 0  # two units of the same month are NOT duplicates
    dup = _preview(client, eng, _csv(a, a)).json()
    assert dup["errorRows"] == 1 and "Duplicate" in dup["rows"][1]["errors"][0]
    rows = [{"facilityId": r["facilityId"], "unit": r["unit"], "month": r["month"], "data": r["data"]} for r in p["rows"]]
    res = client.post(f"{API}/submissions/import", headers=eng, json={"status": "Draft", "rows": rows}).json()
    assert res["saved"] == 1 and res["failed"] == 0
    sub = client.get(f"{API}/submissions/{res['results'][0]['submissionId']}", headers=eng).json()
    assert [u["unit"] for u in sub["unitData"]] == units[:2]
    assert sub["data"]["electricity"] == 2 * 6120000
