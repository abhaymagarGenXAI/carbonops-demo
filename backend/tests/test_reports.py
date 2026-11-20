import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.services import report_engine as re_
from tests.conftest import ENGINEER, MANAGER, auth_headers

API = "/api/v1"


def rec(month, fac, scope, source, co2e, status="Approved", **kw):
    return {"id": f"{month}-{fac}-{source}", "month": month, "facilityId": fac, "scope": scope, "source": source, "unit": "kWh",
            "co2e": co2e, "activityValue": 100, "reviewStatus": status, "factorId": "EF-1", "formula": "f", "submissionId": "S", **kw}


FACS = [{"id": "A", "name": "Alpha"}, {"id": "B", "name": "Beta"}]
FACTORS = {"EF-1": {"source": "x", "scope": "Scope 1", "value": 2.0, "unit": "kg", "reference": "r", "validFrom": "2026-01-01"}}


# ------------------------------------------------------------------ pure engine
def test_totals_are_exact_sums_and_basis_filters():
    recs = [rec("2026-01", "A", "Scope 1", "Diesel", 0.1), rec("2026-01", "A", "Scope 2", "Grid", 0.2), rec("2026-01", "B", "Scope 1", "Diesel", 0.3),
            rec("2026-01", "B", "Scope 2", "Grid", 10, "Under Review"), rec("2026-01", "A", "Scope 1", "Flare", 99, "Rejected")]
    appr = re_.select(recs, "approved", None, None, None)
    s = re_.summarise(appr, recs, FACS, FACTORS, None, None, None)
    assert s["totals"] == {"scope1": 0.4, "scope2": 0.2, "scope3": 0.0, "total": 0.6}  # 0.1+0.3 exact, not 0.4000000000000001
    assert s["coverage"]["leftOut"] == {"Under Review": 1, "Rejected": 1}
    assert [x["source"] for x in s["bySource"]] == ["Diesel", "Grid"] and s["bySource"][0]["sharePct"] == 66.7
    pend = re_.select(recs, "pending", None, None, None)
    assert re_.summarise(pend, recs, FACS, FACTORS, None, None, None)["totals"]["total"] == 10.6
    assert re_.select(recs, "approved", "2026-02", None, None) == [] and len(re_.select(recs, "approved", None, None, "B")) == 1


def test_incomplete_months_and_warnings():
    recs = [rec("2026-01", "A", "Scope 1", "D", 1), rec("2026-01", "B", "Scope 1", "D", 1), rec("2026-02", "A", "Scope 1", "D", 1)]
    s = re_.summarise(re_.select(recs, "approved", None, None, None), recs, FACS, FACTORS, None, None, None)
    assert s["coverage"]["incompleteMonths"] == ["2026-02"]
    w = " ".join(re_.warnings(s, "approved"))
    assert "2026-02" in w and "No approved Scope 3 entries" in w
    assert "awaiting approval" in " ".join(re_.warnings(s, "pending"))


# ------------------------------------------------------------------ API
def test_inventory_preview_matches_ledger(client):
    eng = auth_headers(client, ENGINEER)
    r = client.get(f"{API}/reports/inventory", headers=eng, params={"from": "2026-01", "to": "2026-03"})
    assert r.status_code == 200
    j = r.json()
    ledger = [x for x in client.get(f"{API}/emission-records", headers=eng).json() if x["reviewStatus"] == "Approved" and "2026-01" <= x["month"] <= "2026-03"]
    assert j["summary"]["totals"]["total"] == float(sum(Decimal(str(x["co2e"])) for x in ledger))
    assert j["summary"]["coverage"]["recordCount"] == len(ledger)
    assert sum(x["total"] for x in j["summary"]["byMonth"]) == pytest.approx(j["summary"]["totals"]["total"], abs=0.02)
    assert sum(x["total"] for x in j["summary"]["byFacility"]) == pytest.approx(j["summary"]["totals"]["total"], abs=0.02)
    assert client.get(f"{API}/reports/inventory", headers=eng, params={"basis": "bogus"}).status_code == 422
    assert client.get(f"{API}/reports/inventory", headers=eng, params={"from": "2026-03", "to": "2026-01"}).status_code == 422
    assert client.get(f"{API}/reports/inventory", headers=eng, params={"facility_id": "NOPE"}).status_code == 422
    assert client.get(f"{API}/reports/inventory").status_code == 401
    one = client.get(f"{API}/reports/inventory", headers=eng, params={"facility_id": "FAC-001"}).json()
    assert [f["facilityId"] for f in one["summary"]["byFacility"]] == ["FAC-001"]
    pend = client.get(f"{API}/reports/inventory", headers=eng, params={"basis": "pending"}).json()
    assert pend["summary"]["totals"]["total"] > client.get(f"{API}/reports/inventory", headers=eng).json()["summary"]["totals"]["total"]
    assert any("awaiting approval" in w for w in pend["warnings"])


def test_excel_csv_pdf_exports_and_audit(client):
    mgr = auth_headers(client, MANAGER)
    p = {"from": "2026-01", "to": "2026-03"}
    x = client.get(f"{API}/reports/inventory.xlsx", headers=mgr, params=p)
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"] and "ghg-inventory-2026-01_to_2026-03_approved.xlsx" in x.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames == ["Summary", "By source", "By facility", "By month", "Calculation trace", "Emission factors"]
    rows = list(wb["Calculation trace"].iter_rows(values_only=True))
    total = client.get(f"{API}/reports/inventory", headers=mgr, params=p).json()["summary"]["totals"]["total"]
    assert float(sum(Decimal(str(r[11])) for r in rows[1:])) == pytest.approx(total, abs=0.02)  # trace sums to the headline total
    assert rows[0][11] == "tCO2e" and len(rows) > 1
    c = client.get(f"{API}/reports/inventory.csv", headers=mgr, params=p)
    assert c.status_code == 200 and c.content.startswith(b"\xef\xbb\xbfRecord,Facility") and c.text.count("\n") == len(rows)
    pdf = client.get(f"{API}/reports/inventory.pdf", headers=mgr, params=p)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-" and len(pdf.content) > 1500
    audit = client.get(f"{API}/audit", headers=mgr).json()[:3]
    assert {a["action"] for a in audit} == {"Exported"} and {a["target"] for a in audit} == {"ghg-inventory"}
