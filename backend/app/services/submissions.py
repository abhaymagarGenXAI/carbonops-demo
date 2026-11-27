from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.facility import FacilityRepository
from app.repositories.submission import SubmissionRepository
from app.schemas.submission import ReviewRequest, SubmissionSave, UnitDataIn
from app.db import collections as C
from app.db.atomic import atomic
from app.services import carbon, energy, masters, facilities as facilities_svc, periods, rules, rules_config, validation
from app.services.common import audit, conflict, forbidden, not_found, unprocessable
from app.utils.time import utcnow


_SUM = ("productionVolume", "electricity", "diesel", "naturalGas", "steam", "water", "flareGas", "methaneLeak", "renewable")


def combine_units(parts: list[dict[str, Any]], names: list[str]) -> dict[str, Any]:
    """Facility figures of a month = the sum of its production units' figures (operating hours: the longest-running unit,
    since units run in parallel). A single unit is passed through unchanged."""
    if len(parts) == 1:
        return dict(parts[0])
    out: dict[str, Any] = {k: round(sum(float(p.get(k) or 0) for p in parts), 4) for k in _SUM}
    out["operatingHours"] = max(float(p.get("operatingHours") or 0) for p in parts)
    for key, limit in (("remarks", 500), ("notes", 1000)):
        joined = " | ".join(f"{n}: {p[key]}" for n, p in zip(names, parts) if p.get(key))
        out[key] = joined[:limit]
    return out


def save_submission(db: Database, user: Mapping[str, Any], payload: SubmissionSave) -> dict[str, Any]:
    """Save draft / submit for review. One submission per facility + month (upsert)."""
    facility = FacilityRepository(db).get(payload.facility_id)
    if facility is None:
        raise not_found("Facility", payload.facility_id)
    if not facilities_svc.is_active(facility):
        raise conflict(f"{facility['name']} is deactivated; reactivate it before adding data to it")
    lines = payload.unit_data or [UnitDataIn(unit=payload.unit, data=payload.data)]
    names = [ln.unit for ln in lines]
    for u in names:
        if u not in facility["units"]:
            raise unprocessable(f"'{u}' is not a production unit of {facility['name']}")
    if len(set(names)) != len(names):
        raise unprocessable("Each production unit can appear only once in a submission")

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

    unit_data = [{"unit": ln.unit, "unitId": masters.unit_id(db, payload.facility_id, ln.unit), "data": ln.data.model_dump(by_alias=True)} for ln in lines]
    data = combine_units([ln["data"] for ln in unit_data], names)
    subs_before = repo.list({"facilityId": payload.facility_id})
    history = validation.history_before(subs_before, payload.month)
    config = rules_config.load(db)
    per_unit = validation.unit_findings([(u["unit"], u["data"]) for u in unit_data], subs_before, payload.month, config)
    if payload.status == "Submitted":
        blockers = rules.blocking_findings(data, history, config) + [f"{u}: {f.message}" for u, f in per_unit if f.blocking]
        if blockers:
            raise unprocessable("Submission blocked by validation rules — correct the data or save it as a draft: "
                                + "; ".join(blockers))
    validation_status, anomalies = rules.validate_activity(payload.status, data, history, config)
    if payload.status != "Draft" and per_unit:
        anomalies = anomalies + [f"{u}: {f.message}" for u, f in per_unit]
        validation_status = "Warnings"
    is_draft = payload.status == "Draft"
    now = utcnow()
    doc: dict[str, Any] = {
        "facilityId": payload.facility_id,
        "unit": ", ".join(names),
        "unitId": unit_data[0]["unitId"] if len(unit_data) == 1 else None,
        "unitData": unit_data,
        "month": payload.month,
        "status": payload.status,
        "reviewAction": "None",
        "submittedBy": user["name"],
        "submittedById": user["id"],
        "submittedAt": None if is_draft else now,
        "reviewedAt": None,
        "reviewer": "—" if is_draft else "Pending assignment",
        "reviewerId": None,
        "reviewerComments": "",
        "validation": validation_status,
        "completeness": rules.completeness(data),
        "anomalies": anomalies,
        "data": data,
    }
    # the submission and everything derived from it are saved together or not at all
    with atomic(db, {C.SUBMISSIONS: {"facilityId": payload.facility_id, "month": payload.month},
                     C.ENERGY_RECORDS: {"facilityId": payload.facility_id},
                     C.EMISSION_RECORDS: {"facilityId": payload.facility_id}}):
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
    if current.get("submittedById") == user["id"]:
        # segregation of duties: whoever entered or last saved the figures cannot decide on them (same rule as Scope 3 entries)
        raise forbidden(f"You submitted {submission_id}, so you cannot approve, reject or query it; another reviewer must decide")
    comment = req.comment.strip()
    if req.status == "Rejected" and not comment:
        raise unprocessable("A comment is required when rejecting a submission")

    changes: dict[str, Any] = {
        "status": req.status,
        # Mirrors the Mongoose model: clarification = "Under Review" + reviewAction flag
        "reviewAction": "Clarification Required" if req.status == "Under Review" else "None",
        "reviewer": user["name"],
        "reviewerId": user["id"],
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
