"""CSV / XLSX activity-data parsing — pure functions (no database).

One row = one facility-month. Header names are matched case-insensitively and ignore spaces/underscores/units,
so `Natural Gas (SCM)` and `natural_gas` both work. Numbers may carry thousands separators (6,120,000 or 61,20,000).
Nothing is ever defaulted to zero: a blank required value is an error, because a silent 0 would understate emissions.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
import re
import zipfile
from typing import Any, Iterable

from fastapi import HTTPException, status

NUMERIC = ("production_volume", "electricity", "diesel", "natural_gas", "steam", "water",
           "flare_gas", "methane_leak", "renewable", "operating_hours")
TEXT = ("remarks", "notes")
IDENTITY = ("facility", "unit", "month")
LABELS = {
    "facility": "Facility", "unit": "Unit", "month": "Month", "production_volume": "Production volume",
    "electricity": "Electricity", "diesel": "Diesel", "natural_gas": "Natural gas", "steam": "Steam",
    "water": "Water", "flare_gas": "Flare gas", "methane_leak": "Methane leak", "renewable": "Renewable",
    "operating_hours": "Operating hours", "remarks": "Remarks", "notes": "Notes",
}
TEMPLATE_HEADERS = ["facility", "unit", "month", *NUMERIC, *TEXT]

_ALIASES: dict[str, tuple[str, ...]] = {
    "facility": ("facility", "facility_code", "facility_name", "facility_id", "site", "asset"),
    "unit": ("unit", "production_unit"),
    "month": ("month", "reporting_month", "period", "reporting_period"),
    "production_volume": ("production_volume", "production", "volume"),
    "electricity": ("electricity", "electricity_kwh", "electricity_consumption", "grid_electricity", "power_kwh"),
    "diesel": ("diesel", "diesel_l", "diesel_litres", "diesel_liters"),
    "natural_gas": ("natural_gas", "natural_gas_scm", "gas_scm"),
    "steam": ("steam", "steam_t", "steam_tonnes", "steam_tons"),
    "water": ("water", "water_m3", "water_kl", "water_consumption"),
    "flare_gas": ("flare_gas", "flare_gas_scm", "flaring", "flared_gas"),
    "methane_leak": ("methane_leak", "methane_leakage", "methane_leak_kg", "fugitive_methane"),
    "renewable": ("renewable", "renewable_kwh", "renewable_energy", "renewable_energy_kwh"),
    "operating_hours": ("operating_hours", "hours", "run_hours"),
    "remarks": ("remarks", "remark", "comments"),
    "notes": ("notes", "note"),
}
_LOOKUP = {alias: field for field, aliases in _ALIASES.items() for alias in aliases}
_MONTH_RE = re.compile(r"^(\d{4})[-/](0[1-9]|1[0-2])(?:[-/]\d{1,2})?$")


def _fail(msg: str, code: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(code, msg)


def norm_header(h: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(h if h is not None else "").strip().lower()).strip("_")


# ------------------------------------------------------------------ reading files
def _is_blank(row: Iterable[Any]) -> bool:
    return all(c is None or (isinstance(c, str) and not c.strip()) for c in row)


def _read_csv(content: bytes) -> list[list[Any]]:
    if b"\x00" in content:
        raise _fail("This does not look like a CSV text file")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")  # Excel's "CSV (Comma delimited)"
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)]


def _read_xlsx(content: bytes) -> tuple[list[list[Any]], str]:
    from openpyxl import load_workbook  # local import: only needed for .xlsx

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise _fail("Could not read this file as an .xlsx workbook") from exc
    except Exception as exc:  # openpyxl raises several InvalidFileException-style errors
        raise _fail("Could not read this file as an .xlsx workbook") from exc
    try:
        ws = next((s for s in wb.worksheets if getattr(s, "sheet_state", "visible") == "visible"), None)
        if ws is None:
            raise _fail("The workbook has no visible sheet")
        return [list(r) for r in ws.iter_rows(values_only=True)], ws.title
    finally:
        wb.close()


def read_table(filename: str, content: bytes, max_rows: int) -> tuple[list[Any], list[tuple[int, list[Any]]], str | None]:
    """Returns (header cells, [(sheet row number, cells)], sheet name). Blank rows are skipped."""
    name = filename.lower()
    if name.endswith(".csv"):
        grid, sheet = _read_csv(content), None
    elif name.endswith(".xlsx"):
        grid, sheet = _read_xlsx(content)
    else:
        raise _fail("Import supports .csv and .xlsx files (save older .xls files as .xlsx first)")
    numbered = [(i, r) for i, r in enumerate(grid, start=1) if not _is_blank(r)]
    if not numbered:
        raise _fail("The file contains no data")
    (_, header), data = numbered[0], numbered[1:]
    if not data:
        raise _fail("The file has a header row but no data rows")
    if len(data) > max_rows:
        raise _fail(f"The file has {len(data)} data rows; the limit is {max_rows} per import")
    return header, data, sheet


def map_columns(header: list[Any]) -> tuple[dict[str, int], list[str]]:
    """field -> column index, plus header names that were not recognised (or duplicated)."""
    cols: dict[str, int] = {}
    unmapped: list[str] = []
    for i, h in enumerate(header):
        if h is None or str(h).strip() == "":
            continue
        field = _LOOKUP.get(norm_header(h))
        if field is None or field in cols:
            unmapped.append(str(h).strip())
        else:
            cols[field] = i
    return cols, unmapped


# ------------------------------------------------------------------ cell parsing
def parse_number(v: Any) -> float:
    if v is None or (isinstance(v, str) and not v.strip()):
        raise ValueError("value is missing")
    if isinstance(v, bool):
        raise ValueError(f"'{v}' is not a number")
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        s = re.sub(r"[,\s _]", "", str(v))
        try:
            x = float(s)
        except ValueError:
            raise ValueError(f"'{str(v).strip()}' is not a number") from None
    if not math.isfinite(x):
        raise ValueError(f"'{v}' is not a finite number")
    return x


def parse_month(v: Any) -> str:
    if isinstance(v, (dt.datetime, dt.date)):  # Excel turns "2026-07" into a date
        return f"{v.year}-{v.month:02d}"
    m = _MONTH_RE.match(str(v or "").strip())
    if not m:
        raise ValueError(f"'{str(v or '').strip()}' is not a month — use YYYY-MM, e.g. 2026-07")
    return f"{m.group(1)}-{m.group(2)}"


def cell_text(v: Any) -> str:
    return "" if v is None else str(v).strip()
