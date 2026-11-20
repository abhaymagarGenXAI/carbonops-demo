from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response

from app.core.deps import PLANT_ENGINEER, SUSTAINABILITY_MANAGER, CurrentUser, Db, require_roles
from app.repositories.submission import SubmissionRepository
from app.core.config import get_settings
from app.schemas.common import MONTH_PATTERN
from app.schemas.imports import ImportCommitOut, ImportCommitRequest, ImportPreviewOut
from app.schemas.submission import ReviewRequest, SubmissionOut, SubmissionSave
from app.services import imports as import_svc
from app.services import submissions as svc
from app.services import uploads
from app.repositories.document import DocumentRepository
from app.repositories.facility import FacilityRepository
from app.services import exports
from app.services.common import not_found, unprocessable

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.get("", response_model=list[SubmissionOut])
def list_submissions(
    db: Db, _: CurrentUser, facility_id: str | None = None, month: str | None = None, status: str | None = None
):
    filters = {k: v for k, v in {"facilityId": facility_id, "month": month, "status": status}.items() if v}
    return SubmissionRepository(db).list(filters)


@router.get("/export", summary="Submission history as an Excel workbook (optional month range, facility, status)")
def export_history(
    db: Db, _: CurrentUser, from_month: str | None = Query(None, alias="from", pattern=MONTH_PATTERN),
    to_month: str | None = Query(None, alias="to", pattern=MONTH_PATTERN), facility_id: str | None = None,
    status: str | None = None,
):
    if from_month and to_month and to_month < from_month:
        raise unprocessable("'to' month must not be before 'from' month")
    rows = [s for s in SubmissionRepository(db).list({k: v for k, v in {"facilityId": facility_id, "status": status}.items() if v})
            if (not from_month or s["month"] >= from_month) and (not to_month or s["month"] <= to_month)]
    rows.sort(key=lambda s: (s["month"], s["facilityId"]), reverse=True)
    evidence: dict[tuple[str, str], int] = {}
    for d in DocumentRepository(db).list({}):
        evidence[(d["facilityId"], d["month"])] = evidence.get((d["facilityId"], d["month"]), 0) + 1
    names = {f["id"]: f["name"] for f in FacilityRepository(db).list()}
    stamp = f"{from_month or 'start'}_to_{to_month or 'latest'}"
    return Response(exports.submissions_xlsx(rows, names, evidence),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="submission-history-{stamp}.xlsx"'})


@router.get("/import/template", summary="CSV template with the expected column headers")
def import_template(_: CurrentUser):
    return Response(import_svc.template_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="activity-import-template.csv"'})


@router.post("/import/preview", response_model=ImportPreviewOut, summary="Parse and validate a CSV/XLSX file (writes nothing)")
def import_preview(
    db: Db,
    user: dict = Depends(require_roles(PLANT_ENGINEER)),
    file: UploadFile = File(...),
    facility_id: str | None = Form(None, alias="facilityId"),
    month: str | None = Form(None, pattern=MONTH_PATTERN),
):
    content = uploads.read_limited(file.file, get_settings().max_import_mb * 1024 * 1024)
    return import_svc.preview(db, filename=uploads.clean_name(file.filename or ""), content=content,
                              default_facility_id=facility_id or None, default_month=month or None)


@router.post("/import", response_model=ImportCommitOut, summary="Save previewed rows as drafts or submissions")
def import_commit(body: ImportCommitRequest, db: Db, user: dict = Depends(require_roles(PLANT_ENGINEER))):
    return import_svc.commit(db, user, body)


@router.get("/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: str, db: Db, _: CurrentUser):
    row = SubmissionRepository(db).get(submission_id)
    if row is None:
        raise not_found("Submission", submission_id)
    return row


@router.post("", response_model=SubmissionOut, summary="Save draft or submit for review (upsert by facility + month)")
def save_submission(body: SubmissionSave, db: Db, user: dict = Depends(require_roles(PLANT_ENGINEER))):
    return svc.save_submission(db, user, body)


@router.post("/{submission_id}/review", response_model=SubmissionOut, summary="Approve / reject / request clarification")
def review_submission(
    submission_id: str, body: ReviewRequest, db: Db, user: dict = Depends(require_roles(SUSTAINABILITY_MANAGER))
):
    return svc.review_submission(db, user, submission_id, body)
