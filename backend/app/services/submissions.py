from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.facility import FacilityRepository
from app.repositories.submission import SubmissionRepository
from app.schemas.submission import ReviewRequest, SubmissionSave
from app.services import carbon, energy, periods, rules, rules_config, validation
from app.services.common import audit, conflict, not_found, unprocessable
from app.utils.time import utcnow


def save_submission(db: Database, user: Mapping[str, Any], payload: SubmissionSave) -> dict[str, Any]:
    """Save draft / submit for review. One submission per facility + month (upsert)."""
    facility = FacilityRepository(db).get(payload.facility_id)
    if facility is None:
        raise not_found("Facility", payload.facility_id)
    if payload.unit not in facility["units"]:
        raise unprocessable(f"'{payload.unit}' is not a production unit of {facility['name']}")

    periods.assert_accepts_submissions(db, payload.month)
    repo = SubmissionRepository(db)
    existing = repo.get_by_facility_month(payload.facility_id, payload.month)
    if existing:
        sid = existing["submissionId"]
        if existing.get("status") == "Approved":
            raise conflict(f"{sid} is already approved and locked for editing")
        awaiting = existing.get("status") == "Submitted" or (existing.get("status") == "Under Review" and existing.get("reviewAction") != "Clarification Required")
        if awaiting:
            raise conflict(f"{sid} is awaiting review and cannot be changed until the reviewer rejects it or asks for clarification")
        if payload.revision is not None and payload.revision != int(existing.get("revision") or 0):
            raise conflict(f"{sid} was changed by someone else after you opened it (revision {existing.get('revision') or 0}); reload and try again")

    data = payload.data.model_dump(by_alias=True)
    history = validation.history_before(repo.list({"facilityId": payload.facility_id}), payload.month)
    config = rules_config.load(db)
    if payload.status == "Submitted":
        blockers = rules.blocking_findings(data, history, config)
        if blockers:
            raise unprocessable("Submission blocked by validation rules — correct the data or save it as a draft: "
                                + "; ".join(blockers))
    validation_status, anomalies = rules.validate_activity(payload.status, data, history, config)
    is_draft = payload.status == "Draft"
    now = utcnow()
    doc: dict[str, Any] = {
        "facilityId": payload.facility_id,
        "unit": payload.unit,
        "month": payload.month,
        "status": payload.status,
        "reviewAction": "None",
        "submittedBy": user["name"],
        "submittedAt": None if is_draft else now,
        "reviewedAt": None,
        "reviewer": "—" if is_draft else "Pending assignment",
        "reviewerComments": "",
        "validation": validation_status,
        "completeness": rules.completeness(data),
        "anomalies": anomalies,
        "data": data,
    }
    if existing:
        out = repo.update(existing["submissionId"], doc)
    else:
        out = repo.create({**doc, "id": rules.submission_id(facility["code"], payload.month)})
    assert out is not None
    energy.sync_submission_energy(db, out)
    carbon.sync_submission_emissions(db, user, out)  # before the user-facing audit entry so that stays the latest
    audit(
        db, user,
        "Saved draft" if is_draft else "Submitted",
        out["id"],
        f"Activity data for {payload.month} {payload.status.lower()}.",
    )
    return out


def review_submission(db: Database, user: Mapping[str, Any], submission_id: str, req: ReviewRequest) -> dict[str, Any]:
    repo = SubmissionRepository(db)
    current = repo.get_raw(submission_id)
    if current is None:
        raise not_found("Submission", submission_id)
    periods.assert_accepts_submissions(db, current["month"])
    if req.revision is not None and req.revision != int(current.get("revision") or 0):
        raise conflict(f"{submission_id} changed after you opened it (now revision {current.get('revision') or 0}); reload before deciding")
    if current["status"] not in ("Submitted", "Under Review"):
        hint = {
            "Draft": "it has not been submitted yet",
            "Approved": "approved submissions are final",
            "Rejected": "the data owner must correct and resubmit it first",
        }.get(current["status"], "it is not awaiting review")
        raise conflict(f"{submission_id} is {current['status']} and cannot be reviewed: {hint}")
    comment = req.comment.strip()
    if req.status == "Rejected" and not comment:
        raise unprocessable("A comment is required when rejecting a submission")

    changes: dict[str, Any] = {
        "status": req.status,
        # Mirrors the Mongoose model: clarification = "Under Review" + reviewAction flag
        "reviewAction": "Clarification Required" if req.status == "Under Review" else "None",
        "reviewer": user["name"],
        "reviewerComments": comment,
    }
    if req.status in ("Approved", "Rejected"):
        changes["reviewedAt"] = utcnow()
    out = repo.update(submission_id, changes)
    assert out is not None
    energy.sync_submission_energy(db, out)
    carbon.sync_submission_emissions(db, user, out)
    audit(db, user, req.status, submission_id, comment or f"Submission moved to {req.status}.")
    return out
