"""Excel export of the submission history (openpyxl, MIT)."""
from __future__ import annotations

import io
from typing import Any, Sequence

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.utils.safe_cell import append_row

FIELDS: list[tuple[str, str]] = [
    ("productionVolume", "Production volume (boe)"), ("electricity", "Electricity (kWh)"), ("diesel", "Diesel (L)"),
    ("naturalGas", "Natural gas (SCM)"), ("steam", "Steam (t)"), ("water", "Water (m³)"), ("flareGas", "Flare gas (SCM)"),
    ("methaneLeak", "Methane leakage (kg CH₄)"), ("renewable", "Renewable energy (kWh)"), ("operatingHours", "Operating hours"),
]


def submissions_xlsx(rows: Sequence[dict[str, Any]], facility_names: dict[str, str], evidence: dict[tuple[str, str], int]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Submission history"
    head = ["Submission", "Facility", "Unit", "Month", "Status", "Validation", "Completeness %", "Submitted by",
            "Reviewer", "Reviewer comments", "Last updated", "Evidence files", *[h for _, h in FIELDS], "Anomaly flags"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True)
    for s in rows:
        d = s.get("data", {})
        append_row(ws, [
            s["id"], facility_names.get(s["facilityId"], s["facilityId"]), s["unit"], s["month"], s["status"],
            s.get("validation", ""), s.get("completeness", 0), s.get("submittedBy", ""), s.get("reviewer", ""),
            s.get("reviewerComments", ""), str(s.get("updatedAt", "")), evidence.get((s["facilityId"], s["month"]), 0),
            *[d.get(k, 0) for k, _ in FIELDS], "; ".join(s.get("anomalies", [])),
        ])
    ws.freeze_panes = "A2"
    for i, col in enumerate(ws.columns, 1):
        ws.column_dimensions[get_column_letter(i)].width = min(40, max(12, max(len(str(c.value or "")) for c in col) + 2))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
