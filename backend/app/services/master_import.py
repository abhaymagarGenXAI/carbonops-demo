"""Excel upload / export of facilities and assets (openpyxl).

One workbook, two sheets - "Facilities" and "Assets" - used for the template, the export and the upload, so an export can
be edited and uploaded again. Rows are matched by business key: a facility by its code, an asset by its Asset ID (blank =
new asset). Existing rows are updated, unknown ones created; nothing is ever deleted by an upload.
An upload is all-or-nothing: if any row is invalid nothing is written and every problem is reported with its sheet row.
"""
from __future__ import annotations

import datetime as dt
import io
import random
import re
import time
from typing import Any, Mapping

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.repositories.asset import AssetRepository
from app.repositories.facility import FacilityRepository
from app.schemas.asset import AssetCreate
from app.schemas.facility import FacilityCreate
from app.services import facilities as fac
from app.services import iam, masters
from app.services.common import audit, unprocessable
from app.utils.safe_cell import append_row

MAX_ROWS = 2000
STATUSES = ("Operational", "Under Maintenance", "Shutdown", "Standby")
SCOPES = ("Scope 1", "Scope 2", "Scope 3")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# field, header, width, required
FAC_COLS = [("code", "Facility code*", 14), ("name", "Facility name*", 28), ("region", "Region*", 20), ("type", "Facility type*", 28),
            ("manager", "Manager*", 20), ("units", "Production units* (separate with ;)", 44),
            ("commissioned", "Commissioned (YYYY-MM-DD)*", 24), ("employees", "Employees", 12)]
AST_COLS = [("assetId", "Asset ID (blank = new asset)", 22), ("facilityCode", "Facility code*", 14), ("name", "Asset name*", 28),
            ("unit", "Production unit*", 26), ("type", "Asset type*", 22), ("status", "Status*", 18), ("energySource", "Energy source*", 18),
            ("operatingHours", "Operating hours", 16), ("engineer", "Engineer*", 18), ("lastInspection", "Last inspection (YYYY-MM-DD)*", 26),
            ("carbonCategory", "Carbon category* (Scope 1/2/3)", 24), ("emissionSourceType", "Emission source type*", 28), ("capacity", "Capacity*", 16)]
_FAC_REQ = {"code", "name", "region", "type", "manager", "units", "commissioned"}
_AST_REQ = {"facilityCode", "name", "unit", "type", "status", "energySource", "engineer", "lastInspection", "carbonCategory",
            "emissionSourceType", "capacity"}
_ALIASES = {"facility": "facilityCode", "facility_id": "facilityCode", "production_units": "units", "units": "units",
            "commissioned": "commissioned", "commissioned_on": "commissioned", "asset_id": "assetId", "id": "assetId",
            "asset_name": "name", "facility_name": "name", "facility_type": "type", "asset_type": "type", "production_unit": "unit",
            "facility_code": "code"}


def _norm(h: Any) -> str:
    s = re.sub(r"\(.*?\)|\*", "", str(h if h is not None else "")).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _lookup(cols: list[tuple[str, str, int]], sheet: str) -> dict[str, str]:
    m = {_norm(h): f for f, h, _ in cols}
    for alias, field in _ALIASES.items():
        # "facility code" means the facility key on the Assets sheet and the code itself on the Facilities sheet
        if alias in ("facility_code", "facility") and sheet == "Assets":
            m[alias] = "facilityCode"
        elif alias == "facility_code" and sheet == "Facilities":
            m[alias] = "code"
        elif alias not in ("facility_code", "facility", "facility_name", "facility_type") or sheet == "Facilities":
            if field in {f for f, _, _ in cols}:
                m.setdefault(alias, field)
    return m


# ------------------------------------------------------------------------------------------- workbook building
def _style(ws, cols: list[tuple[str, str, int]]) -> None:
    ws.append([h for _, h, _ in cols])
    for i, (_, h, w) in enumerate(cols, 1):
        c = ws.cell(row=1, column=i)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E79" if h.endswith("*") or "*" in h else "5B7C99")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"


def _workbook(facilities: list[dict[str, Any]], assets: list[dict[str, Any]], *, template: bool) -> bytes:
    wb = Workbook()
    wf = wb.active
    wf.title = "Facilities"
    _style(wf, FAC_COLS)
    wa = wb.create_sheet("Assets")
    _style(wa, AST_COLS)
    code_of = {f["id"]: f["code"] for f in facilities}
    for f in facilities:
        append_row(wf, [f["code"], f["name"], f["region"], f["type"], f["manager"], "; ".join(f.get("units") or []), f["commissioned"], f.get("employees", 0)])
    for a in assets:
        append_row(wa, [a["id"], code_of.get(a["facilityId"], ""), a["name"], a["unit"], a["type"], a["status"], a["energySource"],
                   a.get("operatingHours", 0), a["engineer"], a["lastInspection"], a["carbonCategory"], a["emissionSourceType"], a["capacity"]])
    # dropdowns for the closed lists
    st = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=False, showErrorMessage=True)
    sc = DataValidation(type="list", formula1='"' + ",".join(SCOPES) + '"', allow_blank=False, showErrorMessage=True)
    wa.add_data_validation(st)
    wa.add_data_validation(sc)
    st.add("F2:F2000")
    sc.add("K2:K2000")
    for ws in (wf, wa):  # keep date-like cells as text so Excel does not reformat them
        col = "G" if ws is wf else "J"
        for r in range(2, max(ws.max_row, 2) + 1):
            ws[f"{col}{r}"].number_format = "@"
    if template:
        wi = wb.create_sheet("Instructions", 0)
        lines = [
            ("Facilities & assets upload template", True),
            ("", False),
            ("1. Fill the 'Facilities' sheet and/or the 'Assets' sheet below the header row. Columns marked * are required. Do not rename or reorder the sheets or headers.", False),
            ("2. Facilities are matched by Facility code: a new code creates a facility, an existing code updates it (name, region, type, manager, units, commissioned, employees). The code itself never changes.", False),
            ("3. Production units: list every unit of the facility, separated by ';' (for example: Unit A; Unit B). A unit that submissions or assets still use cannot be removed.", False),
            ("4. Assets are matched by Asset ID: leave it blank to create a new asset (an ID is generated), or give an existing ID to update that asset.", False),
            ("5. For an asset, 'Facility code' must be an existing facility or one on the Facilities sheet of this file, and 'Production unit' must be one of that facility's units.", False),
            (f"6. Status must be one of: {', '.join(STATUSES)}. Carbon category: {', '.join(SCOPES)}. Dates: YYYY-MM-DD (DD-MM-YYYY also works).", False),
            ("7. Upload in the app (Facilities & Assets > Upload Excel). The file is checked first and shown to you; nothing is saved unless every row is valid, and nothing is ever deleted by an upload.", False),
            ("", False),
            ("Example - Facilities sheet:  MOF2 | Mumbai Offshore 2 | Western Offshore | Offshore Production Complex | R. Deshpande | North Unit; South Unit | 2010-04-01 | 300", False),
            ("Example - Assets sheet:  (blank) | MOF2 | MOF2 Boiler B1 | North Unit | Boiler | Operational | Natural Gas | 720 | K. Iyer | 2026-01-01 | Scope 1 | Stationary Combustion | 40 TPH", False),
        ]
        for text, bold in lines:
            wi.append([text])
            wi.cell(row=wi.max_row, column=1).font = Font(bold=bold, size=14 if bold else 11)
            wi.cell(row=wi.max_row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
        wi.column_dimensions["A"].width = 140
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template_xlsx() -> bytes:
    return _workbook([], [], template=True)


def export_xlsx(db: Database) -> bytes:
    return _workbook(FacilityRepository(db).list(), AssetRepository(db).list(), template=False)


# ------------------------------------------------------------------------------------------- reading
def _cell(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _date(v: Any, label: str) -> str:
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    s = _cell(v)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"{label}: '{s}' is not a date - use YYYY-MM-DD")


def _read(content: bytes) -> dict[str, tuple[list[Any], list[tuple[int, list[Any]]]]]:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # bad zip, not xlsx, corrupt
        raise unprocessable("Could not read this file as an .xlsx workbook") from exc
    out: dict[str, tuple[list[Any], list[tuple[int, list[Any]]]]] = {}
    try:
        for ws in wb.worksheets:
            key = ws.title.strip().lower()
            if key not in ("facilities", "assets"):
                continue
            grid = [(i, list(r)) for i, r in enumerate(ws.iter_rows(values_only=True), start=1)]
            grid = [(i, r) for i, r in grid if any(_cell(c) for c in r)]
            if not grid:
                continue
            header, data = grid[0][1], grid[1:]
            if len(data) > MAX_ROWS:
                raise unprocessable(f"The '{ws.title}' sheet has {len(data)} rows; the limit is {MAX_ROWS} per upload")
            out[key] = (header, data)
    finally:
        wb.close()
    if not out:
        raise unprocessable("The workbook has no 'Facilities' or 'Assets' sheet with data - download the template and fill it in")
    return out


def _rows(header: list[Any], data: list[tuple[int, list[Any]]], cols: list[tuple[str, str, int]], sheet: str, required: set[str]):
    look = _lookup(cols, sheet)
    idx: dict[str, int] = {}
    for i, h in enumerate(header):
        f = look.get(_norm(h))
        if f and f not in idx:
            idx[f] = i
    missing = sorted(required - set(idx))
    if missing:
        names = {f: h for f, h, _ in cols}
        raise unprocessable(f"The '{sheet}' sheet is missing column(s): " + ", ".join(names[m].replace("*", "").strip() for m in missing))
    for rownum, cells in data:
        yield rownum, {f: (cells[i] if i < len(cells) else None) for f, i in idx.items()}


# ------------------------------------------------------------------------------------------- validation + apply
def _split_units(v: Any) -> list[str]:
    return list(dict.fromkeys(u.strip() for u in re.split(r"[;\n]", _cell(v)) if u.strip()))


def run(db: Database, user: Mapping[str, Any], content: bytes, *, apply: bool) -> dict[str, Any]:
    sheets = _read(content)
    report: list[dict[str, Any]] = []
    fac_repo, ast_repo = FacilityRepository(db), AssetRepository(db)
    existing = {fac.normalise_code(f["code"]): f for f in fac_repo.list()}
    seen_codes: set[str] = set()
    fac_plan: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []  # code, data, current
    units_of: dict[str, list[str]] = {c: list(f.get("units") or []) for c, f in existing.items()}
    inactive = {c for c, f in existing.items() if not fac.is_active(f)}

    def add(sheet: str, row: int, key: str, action: str, errors: list[str], warnings: list[str] | None = None) -> None:
        report.append({"sheet": sheet, "row": row, "key": key, "action": "error" if errors else action, "errors": errors, "warnings": warnings or []})

    if "facilities" in sheets:
        for row, v in _rows(*sheets["facilities"], FAC_COLS, "Facilities", _FAC_REQ):
            errs: list[str] = []
            code = fac.normalise_code(_cell(v.get("code")))
            try:
                data = {"code": code, "name": _cell(v.get("name")), "region": _cell(v.get("region")), "type": _cell(v.get("type")),
                        "manager": _cell(v.get("manager")), "units": _split_units(v.get("units")), "employees": 0,
                        "commissioned": ""}
                if _cell(v.get("commissioned")):
                    data["commissioned"] = _date(v.get("commissioned"), "Commissioned")
                emp = _cell(v.get("employees"))
                if emp:
                    try:
                        n = float(emp.replace(",", ""))
                        if n < 0 or n != int(n):
                            raise ValueError
                        data["employees"] = int(n)
                    except ValueError:
                        errs.append(f"Employees: '{emp}' must be a whole number, 0 or more")
                FacilityCreate.model_validate(data)
            except ValueError as e:
                errs.append(str(e).split("\n")[0] if not hasattr(e, "errors") else "; ".join(
                    f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))  # type: ignore[attr-defined]
                data = {"code": code, "units": _split_units(v.get("units"))}
            if not data.get("units") and not errs:
                errs.append("Production units: list at least one unit")
            if code in seen_codes:
                errs.append(f"Facility code '{code}' appears more than once in this file")
            seen_codes.add(code)
            cur = existing.get(code)
            if cur and not errs:
                try:
                    fac.assert_units_removable(db, cur["id"], data["units"])
                except HTTPException as e:
                    errs.append(str(e.detail))
            if code and not errs:
                units_of[code] = data["units"]
            fac_plan.append((code, data, cur))
            add("Facilities", row, code or "(no code)", "update" if cur else "create", errs)

    ast_plan: list[tuple[str, dict[str, Any], bool]] = []  # facility code, data, is_update
    seen_ids: set[str] = set()
    if "assets" in sheets:
        for row, v in _rows(*sheets["assets"], AST_COLS, "Assets", _AST_REQ):
            errs, warns = [], []
            fcode = fac.normalise_code(_cell(v.get("facilityCode")))
            aid = _cell(v.get("assetId"))
            status = next((s for s in STATUSES if s.lower() == _cell(v.get("status")).lower()), _cell(v.get("status")))
            scope = next((s for s in SCOPES if s.lower().replace(" ", "") == _cell(v.get("carbonCategory")).lower().replace(" ", "")), _cell(v.get("carbonCategory")))
            hours = 0.0
            try:
                if _cell(v.get("operatingHours")):
                    hours = float(_cell(v.get("operatingHours")).replace(",", ""))
            except ValueError:
                errs.append(f"Operating hours: '{_cell(v.get('operatingHours'))}' is not a number")
            data: dict[str, Any] = {"name": _cell(v.get("name")), "unit": _cell(v.get("unit")), "type": _cell(v.get("type")), "status": status,
                                    "energySource": _cell(v.get("energySource")), "operatingHours": hours, "engineer": _cell(v.get("engineer")),
                                    "carbonCategory": scope, "emissionSourceType": _cell(v.get("emissionSourceType")), "capacity": _cell(v.get("capacity")),
                                    "lastInspection": "", "facilityId": fcode}
            try:
                if _cell(v.get("lastInspection")):
                    data["lastInspection"] = _date(v.get("lastInspection"), "Last inspection")
            except ValueError as e:
                errs.append(str(e))
            if fcode in inactive:
                errs.append(f"Facility {fcode} is deactivated; reactivate it before adding or changing its assets")
            elif fcode not in units_of:
                errs.append(f"Facility code '{fcode}' is not an existing facility or on the Facilities sheet")
            elif data["unit"] and data["unit"] not in units_of[fcode]:
                errs.append(f"Production unit '{data['unit']}' is not a unit of facility {fcode} (units: {', '.join(units_of[fcode]) or 'none'})")
            if status and status not in STATUSES:
                errs.append(f"Status '{status}' must be one of: {', '.join(STATUSES)}")
            if scope and scope not in SCOPES:
                errs.append(f"Carbon category '{scope}' must be one of: {', '.join(SCOPES)}")
            if aid and not _ID_RE.match(aid):
                errs.append(f"Asset ID '{aid}' may only contain letters, numbers, '-' and '_'")
            if aid and aid in seen_ids:
                errs.append(f"Asset ID '{aid}' appears more than once in this file")
            if aid:
                seen_ids.add(aid)
            if not errs:
                try:
                    AssetCreate.model_validate({**data, "facilityId": fcode or "x"})
                except ValueError as e:
                    errs.append("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in getattr(e, "errors", lambda: [])()) or str(e))
            is_update = bool(aid) and ast_repo.exists(aid)
            if data["type"] and not errs and not masters_has_type(db, data["type"]):
                warns.append(f"New asset type '{data['type']}' will be added to the master list")
            data["id"] = aid
            ast_plan.append((fcode, data, is_update))
            add("Assets", row, aid or f"(new) {data['name']}", "update" if is_update else "create", errs, warns)

    def count(sheet: str, action: str) -> int:
        return sum(1 for r in report if r["sheet"] == sheet and r["action"] == action)

    summary = {s: {a: count(s, a) for a in ("create", "update", "error")} for s in ("Facilities", "Assets")}
    has_errors = any(r["action"] == "error" for r in report)
    applied = False
    if apply and not has_errors:
        from app.db import collections as C
        from app.db.atomic import atomic

        with atomic(db, {C.FACILITIES: {}, C.ASSETS: {}, C.PRODUCTION_UNITS: {}}):
            _write(db, user, fac_plan, ast_plan)
        applied = True
    return {"applied": applied, "canApply": not has_errors, "summary": summary, "rows": report}


def masters_has_type(db: Database, name: str) -> bool:
    from app.db import collections as C

    return db[C.ASSET_TYPES].find_one({"typeName": name}, {"_id": 1}) is not None


def _write(db: Database, user: Mapping[str, Any], fac_plan, ast_plan) -> None:
    fac_repo, ast_repo = FacilityRepository(db), AssetRepository(db)
    id_of: dict[str, str] = {fac.normalise_code(f["code"]): f["id"] for f in fac_repo.list()}
    stamp = int(time.time() * 1000)
    nf = na = 0
    for i, (code, data, cur) in enumerate(fac_plan):
        if cur:
            changes = {k: data[k] for k in ("name", "region", "type", "manager", "units", "commissioned", "employees")}
            fac_repo.update(cur["id"], changes)
            masters.sync_units(db, cur["id"], data["units"])
            if cur["name"] != data["name"]:
                iam.refresh_facility_labels(db, cur["id"])
            id_of[code] = cur["id"]
        else:
            fid = f"{code}-{stamp + i}"
            fac_repo.create({**data, "id": fid})
            masters.sync_units(db, fid, data["units"])
            id_of[code] = fid
        nf += 1
    for fcode, data, is_update in ast_plan:
        body = {k: v for k, v in data.items() if k != "id"}
        body["facilityId"] = id_of[fcode]
        aid = data["id"]
        if is_update:
            ast_repo.update(aid, body)
        else:
            if aid:
                ast_repo.create({**body, "id": aid})
            else:
                code = fac.normalise_code(fcode)
                for _ in range(20):
                    aid = f"{code}-AST-{random.randint(200, 9999)}"
                    try:
                        ast_repo.create({**body, "id": aid})
                        break
                    except DuplicateKeyError:
                        continue
                else:
                    raise HTTPException(409, "Could not allocate a unique asset id, please retry")
        masters.link_asset(db, aid)
        na += 1
    audit(db, user, "Imported", "MASTER-DATA", f"Excel upload applied: {nf} facility row(s), {na} asset row(s).")
