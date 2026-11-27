from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from app.core.config import get_settings
from app.core.deps import CurrentUser, Db, require_permission
from app.services import master_import as svc
from app.services import uploads
from app.services.common import unprocessable

router = APIRouter(prefix="/master-data", tags=["master-data"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/template", summary="Excel template for uploading facilities and assets")
def template(_: dict = Depends(require_permission("master.import"))):
    return Response(svc.template_xlsx(), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="facilities-assets-template.xlsx"'})


@router.get("/export", summary="All facilities and assets as an Excel workbook (same layout as the upload template)")
def export(db: Db, _: CurrentUser):
    return Response(svc.export_xlsx(db), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="facilities-assets.xlsx"'})


@router.post("/import", summary="Validate (dryRun=true, default) or apply (dryRun=false) a facilities/assets workbook")
def import_workbook(
    db: Db, user: dict = Depends(require_permission("master.import")), file: UploadFile = File(...), dry_run: bool = Form(True, alias="dryRun"),
):
    name = uploads.clean_name(file.filename or "")
    if not name.lower().endswith(".xlsx"):
        raise unprocessable("Upload an .xlsx workbook (use the template)")
    content = uploads.read_limited(file.file, get_settings().max_import_mb * 1024 * 1024)
    return svc.run(db, user, content, apply=not dry_run)
