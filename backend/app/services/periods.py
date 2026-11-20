"""Reporting-period lifecycle: Open -> In Review -> Locked (never reopened; locks protect approved figures).

Periods live in the `reportingPeriods` reference list. Business rules:
  * a new period can only be opened as the month after the latest one; the previously Open period moves to In Review
  * a period can be locked only when every facility has an Approved submission in it
  * data entry (submissions) is accepted only for existing, non-locked periods
"""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.facility import FacilityRepository
from app.repositories.reference import ReferenceRepository
from app.repositories.submission import SubmissionRepository
from app.services import carbon_engine as ce
from app.services.common import audit, conflict, unprocessable
from app.utils.time import to_display, utcnow

KEY = "reportingPeriods"
TRANSITIONS = {"Open": {"In Review", "Locked"}, "In Review": {"Locked"}, "Locked": set()}


def list_periods(db: Database) -> list[dict[str, Any]]:
    return sorted(ReferenceRepository(db).get_items(KEY) or [], key=lambda p: p["period"])


def assert_accepts_submissions(db: Database, month: str) -> None:
    period = next((p for p in list_periods(db) if p["period"] == month), None)
    if period is None:
        raise unprocessable(f"Reporting period {month} does not exist. A Sustainability Manager must open it first.")
    if period["status"] == "Locked":
        raise conflict(f"Reporting period {month} is locked; data can no longer be submitted for it")


def open_next_period(
    db: Database, user: Mapping[str, Any], *, submission_due: str | None, approval_due: str | None
) -> dict[str, Any]:
    periods = list_periods(db)
    if not periods:
        raise conflict("No reporting period exists to continue from")
    nxt = ce.next_month(periods[-1]["period"])
    sub_due, app_due = submission_due or f"{nxt}-15", approval_due or f"{nxt}-25"
    if app_due < sub_due:
        raise unprocessable("approvalDue must not be before submissionDue")
    for p in periods:
        if p["status"] == "Open":
            p["status"] = "In Review"
    new = {"id": f"RP-{nxt}", "period": nxt, "status": "Open", "submissionDue": sub_due, "approvalDue": app_due, "lockedOn": "—"}
    ReferenceRepository(db).set_items(KEY, [*periods, new])
    audit(db, user, "Opened", new["id"], f"Reporting period {nxt} opened; {periods[-1]['period']} moved to review.")
    return new


def set_status(db: Database, user: Mapping[str, Any], period: str, status: str) -> dict[str, Any]:
    periods = list_periods(db)
    target = next((p for p in periods if p["period"] == period), None)
    if target is None:
        raise unprocessable(f"Reporting period {period} does not exist")
    if status not in TRANSITIONS.get(target["status"], set()):
        raise conflict(f"Period {period} cannot move from {target['status']} to {status}")
    if status == "Locked":
        by_fac = {s["facilityId"]: s for s in SubmissionRepository(db).list({"month": period})}
        problems = [f"{s['id']} is {s['status']}" for s in by_fac.values() if s["status"] != "Approved"]
        problems += [f"{f['name']} has no submission" for f in FacilityRepository(db).list() if f["id"] not in by_fac]
        if problems:
            raise conflict(f"{period} cannot be locked until every facility has an approved submission: {'; '.join(problems[:5])}"
                           f"{'…' if len(problems) > 5 else ''}")
        target["lockedOn"] = (to_display(utcnow()) or "")[:10]
    target["status"] = status
    ReferenceRepository(db).set_items(KEY, periods)
    audit(db, user, "Locked" if status == "Locked" else "Saved", target["id"], f"Reporting period {period} set to {status}.")
    return target
