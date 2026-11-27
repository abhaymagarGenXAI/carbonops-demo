from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.document import DocumentRepository
from app.repositories.facility import FacilityRepository
from app.repositories.submission import SubmissionRepository
from app.schemas.document import DocumentCreate
from app.services import iam, periods, uploads
from app.services.common import audit, conflict, forbidden, not_found, unprocessable
from app.utils.time import to_display, utcnow


def create_document(db: Database, user: Mapping[str, Any], p: DocumentCreate) -> dict[str, Any]:
    facility = FacilityRepository(db).get(p.facility_id)
    if facility is None:
        raise not_found("Facility", p.facility_id)
    now = utcnow()
    stamp = to_display(now) or ""
    doc = {
        "id": DocumentRepository.new_id(facility["code"]),
        "name": p.name,
        "type": p.type,
        "facilityId": p.facility_id,
        "month": p.month,
        "size": p.size,
        "format": p.format,
        "uploadedBy": user["name"],
        "uploadedById": user["id"],
        "uploadedAt": stamp,
        "linkedRecord": p.linked_record,
        "version": "v1.0",
        "versions": [{"version": "v1.0", "at": stamp[:10], "by": user["name"], "note": "Initial upload"}],
    }
    out = DocumentRepository(db).create(doc)
    audit(db, user, "Uploaded", out["id"], f"{p.name} ({p.size}) added to repository.")
    return out


def upload_document(
    db: Database, user: Mapping[str, Any], *, filename: str, content: bytes, doc_type: str,
    facility_id: str, month: str, linked_record: str = "",
) -> dict[str, Any]:
    """Validates, stores the file on local disk and registers it. Size comes from the real bytes."""
    facility = FacilityRepository(db).get(facility_id)
    if facility is None:
        raise not_found("Facility", facility_id)
    periods.assert_accepts_submissions(db, month)
    name = uploads.clean_name(filename)
    ext = uploads.extension(name)
    uploads.verify_content(ext, content)
    uploads.scan(content)
    if linked_record:
        sub = SubmissionRepository(db).get(linked_record)
        if sub is None or sub["facilityId"] != facility_id or sub["month"] != month:
            raise unprocessable(f"{linked_record} is not a submission of {facility['name']} for {month}")
    doc_id = DocumentRepository.new_id(facility["code"])
    stored, digest = uploads.store(doc_id, ext, content)
    stamp = to_display(utcnow()) or ""
    try:
        out = DocumentRepository(db).create({
            "id": doc_id, "name": name, "type": doc_type, "facilityId": facility_id, "month": month,
            "size": uploads.human_size(len(content)), "format": uploads.ALLOWED[ext][0],
            "uploadedBy": user["name"], "uploadedById": user["id"], "uploadedAt": stamp, "linkedRecord": linked_record, "version": "v1.0",
            "versions": [{"version": "v1.0", "at": stamp[:10], "by": user["name"], "note": "Initial upload"}],
            "sizeBytes": len(content), "sha256": digest, "storedName": stored, "hasFile": True,
        })
    except Exception:
        uploads.remove(stored)
        raise
    audit(db, user, "Uploaded", out["id"], f"{name} ({uploads.human_size(len(content))}) stored; SHA-256 {digest[:12]}….")
    return out


def file_for_download(db: Database, document_id: str) -> tuple[Any, str, str]:
    raw = DocumentRepository(db).get_raw(document_id)
    if raw is None:
        raise not_found("Document", document_id)
    path = uploads.path_of(raw["storedName"]) if raw.get("storedName") else None
    if path is None:
        raise not_found("Stored file for document", document_id)  # legacy metadata-only record, or file missing
    return path, raw["name"], uploads.ALLOWED[path.suffix.lstrip(".").lower()][1]


def delete_document(db: Database, user: Mapping[str, Any], document_id: str) -> None:
    """Managers/administrators may remove any file; anyone else only their own upload. Never after the linked
    submission is approved or once the period is locked (the evidence is part of the audited record)."""
    repo = DocumentRepository(db)
    raw = repo.get_raw(document_id)
    if raw is None:
        raise not_found("Document", document_id)
    privileged = "activity.review" in iam.permissions_for(db, user)  # reviewers (by default Sustainability Manager + Administrator)
    if not privileged and raw.get("uploadedBy") != user["name"]:
        raise forbidden("You can only remove files you uploaded yourself")
    periods.assert_accepts_submissions(db, raw["month"])
    sub = SubmissionRepository(db).get_by_facility_month(raw["facilityId"], raw["month"])
    if sub is not None and sub["status"] == "Approved":
        raise conflict(f"{sub['submissionId']} is approved; its evidence can no longer be removed")
    if not repo.delete(document_id):
        raise not_found("Document", document_id)
    uploads.remove(raw.get("storedName"))
    audit(db, user, "Deleted", document_id, f"Evidence file '{raw['name']}' removed.")


# ---------------------------------------------------------------------------------- repository view (Administrator)
def repository(db: Database) -> dict[str, Any]:
    """Every document with the record it is attached to, so an Administrator can audit the whole evidence store.

    Attachment: `linkedRecord` (a submission id chosen at upload) when it points at a real submission; otherwise the
    facility + month submission it is evidence for (flagged `inferred`); otherwise `none`. Also reports whether the file
    is really on disk (legacy seeded records are metadata only)."""
    from app.repositories.reference import ReferenceRepository

    subs = SubmissionRepository(db).list()
    by_id = {s["id"]: s for s in subs}
    by_fm = {(s["facilityId"], s["month"]): s for s in subs}
    fac = {f["id"]: f for f in FacilityRepository(db).list()}
    periods_ = {p["period"]: p["status"] for p in (ReferenceRepository(db).get_items("reportingPeriods") or [])}
    items: list[dict[str, Any]] = []
    for d in DocumentRepository(db).list():
        raw = DocumentRepository(db).get_raw(d["id"]) or {}
        linked = (d.get("linkedRecord") or "").strip()
        sub, how = (by_id.get(linked), "linked") if linked in by_id else (None, "none")
        if sub is None and (d["facilityId"], d["month"]) in by_fm:
            sub, how = by_fm[(d["facilityId"], d["month"])], "inferred"
        stored = raw.get("storedName")
        on_disk = bool(stored and uploads.path_of(stored))
        items.append({
            **{k: d.get(k) for k in ("id", "name", "type", "format", "size", "sizeBytes", "sha256", "version", "uploadedBy", "uploadedAt", "month", "facilityId", "linkedRecord")},
            "facilityName": fac.get(d["facilityId"], {}).get("name", d["facilityId"]),
            "versionCount": len(d.get("versions") or []) or 1,
            "hasFile": bool(d.get("hasFile")), "fileOnDisk": on_disk, "fileMissing": bool(stored) and not on_disk,
            "attachment": how, "submissionId": sub["id"] if sub else None, "submissionStatus": sub["status"] if sub else None,
            "unit": sub.get("unit") if sub else None, "periodStatus": periods_.get(d["month"]),
            "versions": d.get("versions") or [],
        })
    items.sort(key=lambda x: (x["uploadedAt"] or "", x["id"]), reverse=True)
    by_type: dict[str, int] = {}
    for x in items:
        by_type[x["type"]] = by_type.get(x["type"], 0) + 1
    return {
        "summary": {
            "total": len(items), "withFile": sum(1 for x in items if x["fileOnDisk"]),
            "metadataOnly": sum(1 for x in items if not x["hasFile"] and not x["fileMissing"]),
            "missingFiles": sum(1 for x in items if x["fileMissing"]),
            "unattached": sum(1 for x in items if x["attachment"] == "none"),
            "totalBytes": sum(x["sizeBytes"] or 0 for x in items), "byType": by_type,
        },
        "items": items,
    }
