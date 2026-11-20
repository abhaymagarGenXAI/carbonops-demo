from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.emission import EmissionRecordRepository
from app.schemas.submission import ReviewRequest
from app.repositories.submission import SubmissionRepository
from app.services.common import audit, conflict, not_found
from app.utils.time import to_display, utcnow


def review_emission(db: Database, user: Mapping[str, Any], emission_id: str, req: ReviewRequest) -> dict[str, Any]:
    repo = EmissionRecordRepository(db)
    current = repo.get_raw(emission_id)
    if current is None:
        raise not_found("Emission record", emission_id)
    comment = req.comment.strip()
    sid = current.get("submissionId")
    if sid and (sub := SubmissionRepository(db).get(sid)) is not None:
        # A calculation line is only a view of its submission: the decision belongs to the submission, so the
        # ledger, the Approvals queue and the data owner's alerts can never disagree.
        if sub["status"] not in ("Submitted", "Under Review"):
            raise conflict(f"{emission_id} belongs to {sid} which is {sub['status']}; calculation decisions can only be "
                           "made while the submission is awaiting review")
        if req.status == "Approved":
            raise conflict(f"Approve the whole submission {sid} in Approvals; a single calculation cannot be approved on its own")
        from app.services import submissions  # local import: submissions -> carbon -> emissions layering
        submissions.review_submission(db, user, sid, ReviewRequest(status=req.status, comment=f"[{emission_id}] {comment}".strip()))
        out = repo.get(emission_id)
        assert out is not None
        return out
    comments = list(current.get("comments", []))
    if comment:
        comments.insert(0, {"by": user["name"], "at": to_display(utcnow()), "text": comment})
    out = repo.update(emission_id, {"reviewStatus": req.status, "comments": comments})
    assert out is not None
    audit(db, user, req.status, emission_id, comment or f"Calculation review status set to {req.status}.")
    return out
