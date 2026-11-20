"""GHG inventory reports: JSON summary, Excel workbook, CSV trace and PDF — all built from the same summary."""
from __future__ import annotations

import csv
import io
from typing import Any, Mapping

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from pymongo.database import Database
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.repositories.emission import EmissionRecordRepository
from app.repositories.emission_factor import EmissionFactorRepository
from app.repositories.facility import FacilityRepository
from app.repositories.scope3 import Scope3Repository
from app.repositories.submission import SubmissionRepository
from app.services import report_engine as re_
from app.services import scope3_engine as s3
from app.services.common import audit, unprocessable
from app.utils.time import to_display, utcnow

TRACE_HEAD = ["Record", "Facility", "Month", "Scope", "Source", "Activity", "Unit", "Factor", "Factor unit", "Factor ID",
              "Factor reference", "tCO2e", "Formula", "Submission", "Submission status", "Reviewer", "Record status"]


def build(db: Database, month_from: str | None, month_to: str | None, basis: str, facility_id: str | None) -> dict[str, Any]:
    if basis not in re_.BASES:
        raise unprocessable("basis must be 'approved' or 'pending'")
    if month_from and month_to and month_to < month_from:
        raise unprocessable("'to' month must not be before 'from' month")
    facilities = FacilityRepository(db).list()
    if facility_id and not any(f["id"] == facility_id for f in facilities):
        raise unprocessable(f"Unknown facility {facility_id}")
    allrecs = EmissionRecordRepository(db).list()
    chosen = re_.select(allrecs, basis, month_from, month_to, facility_id)
    factors = {f["id"]: f for f in EmissionFactorRepository(db).list()}
    entries = [e for e in Scope3Repository(db).list() if (not facility_id or e.get("facilityId") == facility_id)]
    e_rows = [s3.as_record(e) for e in entries]
    s3_chosen = re_.select(e_rows, basis, month_from, month_to, None)
    s3_left: dict[str, int] = {}
    for r in e_rows:
        if r not in s3_chosen and r["reviewStatus"] != "Rejected" and (not month_from or r["month"] >= month_from) and (not month_to or r["month"] <= month_to):
            s3_left[r["reviewStatus"]] = s3_left.get(r["reviewStatus"], 0) + 1
    chosen = chosen + s3_chosen
    summary = re_.summarise(chosen, allrecs, facilities, factors, month_from, month_to, facility_id, s3_left)
    subs = {s["id"]: s for s in SubmissionRepository(db).list()}
    names = {f["id"]: f["name"] for f in facilities} | {"CORP": "Corporate / not facility-specific"}
    ent = {e["id"]: e for e in entries}
    trace = []
    for r in sorted(chosen, key=lambda r: (r["month"], r["facilityId"], r["scope"], r["source"])):
        s = subs.get(r.get("submissionId") or "", {}) or (ent.get(r.get("entryId") or "") or {})
        trace.append([r["id"], names.get(r["facilityId"], r["facilityId"]), r["month"], r["scope"], r["source"], r["activityValue"], r["unit"],
                      r["factor"], r["factorUnit"], r.get("factorId") or "", r["factorRef"], r["co2e"], r.get("formula") or "",
                      r.get("submissionId") or r.get("entryId") or "", s.get("status", ""), s.get("reviewer") or "", r["reviewStatus"]])
    scope = {"from": month_from, "to": month_to, "basis": basis, "facilityId": facility_id,
             "facility": names.get(facility_id) if facility_id else "All facilities"}
    return {"scope": scope, "summary": summary, "warnings": re_.warnings(summary, basis), "trace": trace}


def _label(rep: Mapping[str, Any]) -> str:
    s = rep["scope"]
    return f"{s['from'] or 'start'}_to_{s['to'] or 'latest'}_{s['basis']}"


def _stamp(user: Mapping[str, Any]) -> str:
    return f"Generated {to_display(utcnow())} by {user['name']}"


def _log(db: Database, user: Mapping[str, Any], rep: Mapping[str, Any], fmt: str) -> None:
    s, t = rep["scope"], rep["summary"]["totals"]
    audit(db, user, "Exported", "ghg-inventory",
          f"{fmt.upper()} inventory {s['from'] or 'start'}…{s['to'] or 'latest'} · {s['facility']} · basis {s['basis']} · "
          f"{rep['summary']['coverage']['recordCount']} records · {t['total']:,.2f} tCO₂e.")


# ------------------------------------------------------------------ CSV
def to_csv(db: Database, user: Mapping[str, Any], rep: Mapping[str, Any]) -> tuple[bytes, str]:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TRACE_HEAD)
    w.writerows(rep["trace"])
    _log(db, user, rep, "csv")
    return ("﻿" + buf.getvalue()).encode("utf-8"), f"ghg-calculation-trace-{_label(rep)}.csv"  # BOM so Excel reads ₂ etc.


# ------------------------------------------------------------------ Excel
def to_xlsx(db: Database, user: Mapping[str, Any], rep: Mapping[str, Any]) -> tuple[bytes, str]:
    sm, sc = rep["summary"], rep["scope"]
    wb = Workbook()
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DDE7EE")

    def sheet(title: str, head: list[str], rows: list[list[Any]], first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(head)
        for c in ws[1]:
            c.font, c.fill = bold, head_fill
        for r in rows:
            ws.append(r)
        ws.freeze_panes = "A2"
        for i, col in enumerate(ws.columns, 1):
            ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, max(len(str(c.value or "")) for c in col) + 2))
        return ws

    t = sm["totals"]
    ws = sheet("Summary", ["Item", "Value"], [
        ["GHG inventory", ""], ["Period", f"{sc['from'] or 'all'} to {sc['to'] or 'all'}"], ["Facilities", sc["facility"]],
        ["Basis", "Approved records only" if sc["basis"] == "approved" else "Approved + pending review"], ["Generated", _stamp(user)], ["", ""],
        ["Scope 1 (tCO2e)", t["scope1"]], ["Scope 2 (tCO2e)", t["scope2"]], ["Scope 3 (tCO2e, entered categories only)", t["scope3"]], ["Total (tCO2e)", t["total"]], ["", ""],
        ["Records included", sm["coverage"]["recordCount"]], ["Records with stored calculation trace", sm["coverage"]["tracedRecords"]], ["", ""],
        ["Notes and warnings", ""], *[["", w] for w in rep["warnings"]], ["", ""], ["Method", ""], *[["", m] for m in re_.METHOD],
    ], first=True)
    for row in ws.iter_rows(min_row=2):
        if row[0].value in ("GHG inventory", "Notes and warnings", "Method", "Total (tCO2e)"):
            row[0].font = bold
    sheet("By source", ["Source", "Scope", "Activity", "Unit", "tCO2e", "Share %"],
          [[x["source"], x["scope"], x["activity"], x["unit"], x["co2e"], x["sharePct"]] for x in sm["bySource"]])
    sheet("By facility", ["Facility", "Scope 1", "Scope 2", "Scope 3", "Total tCO2e"], [[x["facility"], x["scope1"], x["scope2"], x["scope3"], x["total"]] for x in sm["byFacility"]])
    sheet("By month", ["Month", "Scope 1", "Scope 2", "Scope 3", "Total tCO2e"], [[x["month"], x["scope1"], x["scope2"], x["scope3"], x["total"]] for x in sm["byMonth"]])
    sheet("Calculation trace", TRACE_HEAD, rep["trace"])
    sheet("Emission factors", ["Factor ID", "Source", "Scope", "Value", "Unit", "Reference", "Valid from", "Records using it"],
          [[f["factorId"], f["source"], f["scope"], f["value"], f["unit"], f["reference"], f["validFrom"], f["records"]] for f in sm["factorsUsed"]])
    out = io.BytesIO()
    wb.save(out)
    _log(db, user, rep, "xlsx")
    return out.getvalue(), f"ghg-inventory-{_label(rep)}.xlsx"


# ------------------------------------------------------------------ PDF
def to_pdf(db: Database, user: Mapping[str, Any], rep: Mapping[str, Any]) -> tuple[bytes, str]:
    sm, sc = rep["summary"], rep["scope"]
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8, leading=10)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="GHG inventory", author=user["name"])

    def table(rows: list[list[Any]], widths: list[float] | None = None):
        tb = Table(rows, colWidths=widths, repeatRows=1)
        tb.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE7EE")),
                                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                                ("ALIGN", (-1, 1), (-1, -1), "RIGHT")]))
        return tb

    f2 = lambda x: f"{x:,.2f}"
    t = sm["totals"]
    story: list[Any] = [
        Paragraph("GHG Emissions Inventory", ss["Title"]),
        Paragraph(f"Period: {sc['from'] or 'all'} to {sc['to'] or 'all'} &nbsp;|&nbsp; Facilities: {sc['facility']} &nbsp;|&nbsp; "
                  f"Basis: {'Approved records only' if sc['basis'] == 'approved' else 'Approved + pending review'}", ss["BodyText"]),
        Paragraph(_stamp(user), small), Spacer(1, 6),
        table([["Scope", "tCO2e"], ["Scope 1 (direct)", f2(t["scope1"])], ["Scope 2 (purchased energy, location-based)", f2(t["scope2"])],
               ["Scope 3 (entered categories only)", f2(t["scope3"])], ["Total", f2(t["total"])]], [110 * mm, 40 * mm]),
        Spacer(1, 8), Paragraph("Notes and warnings", ss["Heading3"]), *[Paragraph("• " + w, small) for w in rep["warnings"]],
        Spacer(1, 8), Paragraph("By source", ss["Heading3"]),
        table([["Source", "Scope", "Activity", "Unit", "tCO2e", "%"]] + [[x["source"], x["scope"], f"{x['activity']:,.0f}", x["unit"], f2(x["co2e"]), f"{x['sharePct']}"] for x in sm["bySource"]]),
        Spacer(1, 8), Paragraph("By facility", ss["Heading3"]),
        table([["Facility", "Scope 1", "Scope 2", "Scope 3", "Total"]] + [[x["facility"], f2(x["scope1"]), f2(x["scope2"]), f2(x["scope3"]), f2(x["total"])] for x in sm["byFacility"]]),
        Spacer(1, 8), Paragraph("By month", ss["Heading3"]),
        table([["Month", "Scope 1", "Scope 2", "Scope 3", "Total"]] + [[x["month"], f2(x["scope1"]), f2(x["scope2"]), f2(x["scope3"]), f2(x["total"])] for x in sm["byMonth"]]),
        Spacer(1, 8), Paragraph("Emission factors used", ss["Heading3"]),
        table([["ID", "Source", "Value", "Unit", "Reference", "Valid from"]] + [[f["factorId"], f["source"], f["value"], f["unit"].replace("₂", "2"), f["reference"], f["validFrom"]] for f in sm["factorsUsed"]]),
        Spacer(1, 8), Paragraph("Method", ss["Heading3"]), *[Paragraph("• " + m, small) for m in re_.METHOD],
        Paragraph("The full record-level calculation trace is available in the Excel / CSV export.", small),
    ]

    def footer(c, d):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.drawString(16 * mm, 9 * mm, "CarbonOps AI - GHG inventory")
        c.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {d.page}")
        c.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    _log(db, user, rep, "pdf")
    return buf.getvalue(), f"ghg-inventory-{_label(rep)}.pdf"
