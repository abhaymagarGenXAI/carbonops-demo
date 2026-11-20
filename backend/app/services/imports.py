"""Bulk activity import: preview (parse + validate, writes nothing) and commit (saves through the normal path)."""
from __future__ import annotations

from typing import Any, Mapping

from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.database import Database

from app.core.config import get_settings
from app.repositories.facility import FacilityRepository
from app.repositories.submission import SubmissionRepository
from app.schemas.imports import ImportCommitRequest
from app.schemas.submission import ActivityDataIn, SubmissionSave
from app.services import importer as imp
from app.services import periods, rules_config, submissions, validation
from app.services.common import audit, unprocessable

_FIELD_CAMEL = {  # for translating pydantic locations back to labels
    "productionVolume": "production_volume", "naturalGas": "natural_gas", "flareGas": "flare_gas",
    "methaneLeak": "methane_leak", "operatingHours": "operating_hours",
}


def template_csv() -> str:
    return ",".join(imp.TEMPLATE_HEADERS) + "\r\n"


def preview(db: Database, *, filename: str, content: bytes, default_facility_id: str | None, default_month: str | None) -> dict[str, Any]:
    cfg = get_settings()
    header, data_rows, sheet = imp.read_table(filename, content, cfg.max_import_rows)
    cols, unmapped = imp.map_columns(header)
    required = list(imp.NUMERIC) + ([] if default_facility_id else ["facility"]) + ([] if default_month else ["month"])
    missing = [f for f in required if f not in cols]
    if missing:
        raise unprocessable("Missing required column(s): " + ", ".join(missing)
                            + ". Download the template for the expected layout.")

    config = rules_config.load(db)
    facilities = FacilityRepository(db).list()
    index = {k.lower(): f for f in facilities for k in (f["id"], f["code"], f["name"])}
    by_id = {f["id"]: f for f in facilities}
    default_fac = by_id.get(default_facility_id) if default_facility_id else None
    if default_facility_id and default_fac is None:
        raise unprocessable(f"Facility {default_facility_id} not found")
    repo = SubmissionRepository(db)
    existing = {(s["facilityId"], s["month"]): s for s in repo.list()}
    history_cache: dict[str, list[dict[str, Any]]] = {}

    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for rownum, cells in data_rows:
        def cell(field: str) -> Any:
            i = cols.get(field)
            return cells[i] if i is not None and i < len(cells) else None

        errors: list[str] = []
        warnings: list[str] = []
        fac = unit = month = None

        # --- facility / unit / month
        fval = imp.cell_text(cell("facility"))
        if fval:
            fac = index.get(fval.lower())
            if fac is None:
                errors.append(f"Facility '{fval}' not found (use facility name, code or id)")
        elif default_fac is not None:
            fac = default_fac
        else:
            errors.append("Facility is required")
        mval = cell("month")
        if mval is not None and imp.cell_text(mval):
            try:
                month = imp.parse_month(mval)
            except ValueError as exc:
                errors.append(str(exc))
        elif default_month:
            month = default_month
        else:
            errors.append("Month is required")
        if fac is not None:
            uval = imp.cell_text(cell("unit"))
            valid_units = fac["units"]
            if uval:
                unit = next((u for u in valid_units if u.lower() == uval.lower()), None)
                if unit is None:
                    errors.append(f"'{uval}' is not a unit of {fac['name']} (valid: {', '.join(valid_units)})")
            elif len(valid_units) == 1:
                unit = valid_units[0]
            else:
                errors.append(f"Unit is required for {fac['name']} (valid: {', '.join(valid_units)})")

        # --- numbers
        nums: dict[str, float] = {}
        for field in imp.NUMERIC:
            try:
                nums[field] = imp.parse_number(cell(field))
            except ValueError as exc:
                errors.append(f"{imp.LABELS[field]}: {exc}")
        activity: dict[str, Any] | None = None
        if len(nums) == len(imp.NUMERIC):
            try:
                model = ActivityDataIn.model_validate(
                    {**nums, "remarks": imp.cell_text(cell("remarks")), "notes": imp.cell_text(cell("notes"))})
                activity = model.model_dump(by_alias=True)
            except ValidationError as exc:
                for e in exc.errors():
                    loc = str(e["loc"][0]) if e["loc"] else ""
                    label = imp.LABELS.get(_FIELD_CAMEL.get(loc, loc), loc)
                    errors.append(f"{label}: {e['msg']}")

        # --- business checks that need the database
        existing_status = None
        replace_note = None
        if fac is not None and month is not None:
            key = (fac["id"], month)
            if key in seen:
                errors.append(f"Duplicate of an earlier row for {fac['name']} {month}")
            seen.add(key)
            try:
                periods.assert_accepts_submissions(db, month)
            except HTTPException as exc:
                errors.append(str(exc.detail))
            cur = existing.get(key)
            if cur is not None:
                existing_status = cur["status"]
                if cur["status"] == "Approved":
                    errors.append(f"{cur['id']} is already approved and locked for editing")
                elif cur["status"] in ("Submitted", "Under Review"):
                    replace_note = f"Replaces {cur['id']}, which is currently {cur['status']}"
                else:
                    replace_note = f"Replaces the existing {cur['status'].lower()} {cur['id']}"
        if replace_note and not errors:  # only meaningful for rows that will actually be imported
            warnings.append(replace_note)
        if activity is not None and fac is not None and month is not None and not errors:
            hist = history_cache.get(fac["id"])
            if hist is None:
                hist = history_cache[fac["id"]] = repo.list({"facilityId": fac["id"]})
            warnings += [("Blocks submission (save as draft instead): " if f.blocking else "") + f.message
                         for f in validation.check_activity(activity, validation.history_before(hist, month), config)]

        rows.append({
            "row": rownum, "facilityId": fac["id"] if fac else None, "facilityName": fac["name"] if fac else None,
            "unit": unit, "month": month, "data": activity, "errors": errors, "warnings": warnings,
            "existingStatus": existing_status, "importable": not errors and activity is not None,
        })
    ok = sum(1 for r in rows if r["importable"])
    return {"fileName": filename, "sheet": sheet, "rowCount": len(rows), "importableRows": ok,
            "errorRows": len(rows) - ok, "unmappedColumns": unmapped, "rows": rows}


def commit(db: Database, user: Mapping[str, Any], req: ImportCommitRequest) -> dict[str, Any]:
    """Saves each row through the normal submission path (same validation, emissions and audit)."""
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for r in req.rows:
        base = {"facilityId": r.facility_id, "month": r.month}
        key = (r.facility_id, r.month)
        if key in seen:
            results.append({**base, "ok": False, "submissionId": None, "detail": "Duplicate facility/month in this import"})
            continue
        seen.add(key)
        try:
            out = submissions.save_submission(db, user, SubmissionSave(
                facility_id=r.facility_id, unit=r.unit, month=r.month, status=req.status, data=r.data))
            results.append({**base, "ok": True, "submissionId": out["id"], "detail": ""})
        except HTTPException as exc:
            results.append({**base, "ok": False, "submissionId": None, "detail": str(exc.detail)})
    saved = sum(1 for x in results if x["ok"])
    if saved:
        audit(db, user, "Imported", "bulk-import", f"{saved} of {len(results)} facility-month row(s) imported as {req.status}.")
    return {"saved": saved, "failed": len(results) - saved, "results": results}
