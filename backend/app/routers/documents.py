from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser, Db, require_permission
from app.repositories.document import DocumentRepository
from app.core.config import get_settings
from app.schemas.common import MONTH_PATTERN, DeleteResult
from app.schemas.document import DocumentCreate, DocumentOut
from app.services import documents as svc
from app.services import uploads
from app.services.common import audit, not_found

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(
    db: Db, _: CurrentUser, facility_id: str | None = None, month: str | None = None, type: str | None = None
):
    filters = {k: v for k, v in {"facilityId": facility_id, "month": month, "type": type}.items() if v}
    return DocumentRepository(db).list(filters)


@router.get("/repository", summary="Every document with the record it is attached to (needs page.documents)")
def repository(db: Db, _: dict = Depends(require_permission("page.documents"))):
    return svc.repository(db)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED, summary="Register document metadata")
def create_document(body: DocumentCreate, db: Db, user: CurrentUser):
    return svc.create_document(db, user, body)


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED,
             summary="Upload an evidence file (stored on local disk)")
def upload_document(
    db: Db,
    user: CurrentUser,
    file: UploadFile = File(...),
    type: str = Form(..., min_length=1, max_length=80),
    facility_id: str = Form(..., alias="facilityId", min_length=1),
    month: str = Form(..., pattern=MONTH_PATTERN),
    linked_record: str = Form("", alias="linkedRecord", max_length=60),
):
    content = uploads.read_limited(file.file, get_settings().max_upload_mb * 1024 * 1024)
    return svc.upload_document(db, user, filename=file.filename or "", content=content, doc_type=type.strip(),
                               facility_id=facility_id, month=month, linked_record=linked_record.strip())


@router.get("/{document_id}/download", summary="Download the stored file")
def download_document(document_id: str, db: Db, _: CurrentUser):
    path, name, media_type = svc.file_for_download(db, document_id)
    return FileResponse(path, media_type=media_type, filename=name,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.delete("/{document_id}", response_model=DeleteResult)
def delete_document(document_id: str, db: Db, user: CurrentUser):
    svc.delete_document(db, user, document_id)
    return DeleteResult(id=document_id, deleted=True)
