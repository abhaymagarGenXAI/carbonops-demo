"""Scope 3 entries: engineer/manager enters activity or spend data, a *different* manager approves it.

Calculation uses the factor version effective for the month (versioned like Scope 1/2); the factor id, value, reference and the
formula are stored on the entry so every figure stays traceable even if factors change later.
"""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.emission_factor import EmissionFactorRepository
from app.repositories.facility import FacilityRepository
from app.repositories.scope3 import Scope3Repository
from app.services import iam, masters, periods
from app.services import scope3_engine as eng
from app.services import facilities as facilities_svc
from app.services.common import audit, conflict, forbidden, not_found, unprocessable
from app.utils.time import to_iso, utcnow


def _calc(db: Database, month: str, category: str, source: str, activity: float) -> dict[str, Any]:
    try:
        return eng.calculate(month=month, category=category, source=source, activity=activity,
                             factors=EmissionFactorRepository(db).list(),
                             source_id=masters.source_ids(db).get(source))
    except eng.Scope3Error as exc:
        raise unprocessable(str(exc)) from exc


def _check_facility(db: Database, facility_id: str | None) -> None:
    if facility_id and not FacilityRepository(db).exists(facility_id):
        raise unprocessable(f"Unknown facility {facility_id}")
    if facility_id:
        facilities_svc.assert_active(db, facility_id)


def _own_or_manager(db: Database, user: Mapping[str, Any], row: Mapping[str, Any]) -> None:
    """Own entries, or anyone whose role may approve Scope 3 (by default Sustainability Manager + Administrator)."""
    if "scope3.approve" not in iam.permissions_for(db, user) and row["createdById"] != user["id"]:
        raise forbidden("Only the person who entered this record or someone who can approve Scope 3 entries can change it")


def list_entries(db: Database, month: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    f = {k: v for k, v in {"month": month, "status": status}.items() if v}
    return sorted(Scope3Repository(db).list(f), key=lambda e: (e["month"], e["id"]), reverse=True)


def create(db: Database, user: Mapping[str, Any], body: Mapping[str, Any]) -> dict[str, Any]:
    periods.assert_accepts_submissions(db, body["month"])
    _check_facility(db, body.get("facilityId"))
    repo = Scope3Repository(db)
    row = {**body, **_calc(db, body["month"], body["category"], body["source"], body["activityValue"]),
           "id": repo.next_id(), "status": "Submitted", "createdBy": user["name"], "createdById": user["id"],
           "createdAt": utcnow(), "reviewer": None, "reviewComment": None, "reviewedAt": None}
    out = repo.create(row)
    audit(db, user, "Created", out["id"], f"Scope 3 entry {out['category']} / {out['source']} {out['month']}: {out['co2e']:,.2f} tCO₂e.")
    return out


def update(db: Database, user: Mapping[str, Any], entry_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
    repo = Scope3Repository(db)
    row = repo.get(entry_id)
    if row is None:
        raise not_found("Scope 3 entry", entry_id)
    _own_or_manager(db, user, row)
    if row["status"] == "Approved":
        raise conflict("An approved Scope 3 entry is final and cannot be edited")
    periods.assert_accepts_submissions(db, body["month"])
    _check_facility(db, body.get("facilityId"))
    changes = {**body, **_calc(db, body["month"], body["category"], body["source"], body["activityValue"]),
               "status": "Submitted", "reviewer": None, "reviewComment": None, "reviewedAt": None}
    out = repo.update(entry_id, changes)
    assert out is not None
    audit(db, user, "Updated", entry_id, f"Scope 3 entry resubmitted: {out['co2e']:,.2f} tCO₂e.")
    return out


def delete(db: Database, user: Mapping[str, Any], entry_id: str) -> None:
    repo = Scope3Repository(db)
    row = repo.get(entry_id)
    if row is None:
        raise not_found("Scope 3 entry", entry_id)
    _own_or_manager(db, user, row)
    if row["status"] == "Approved":
        raise conflict("An approved Scope 3 entry is final and cannot be deleted")
    repo.delete(entry_id)
    audit(db, user, "Deleted", entry_id, "Scope 3 entry removed.")


def review(db: Database, user: Mapping[str, Any], entry_id: str, decision: str, comment: str) -> dict[str, Any]:
    repo = Scope3Repository(db)
    row = repo.get(entry_id)
    if row is None:
        raise not_found("Scope 3 entry", entry_id)
    if row["status"] != "Submitted":
        raise conflict(f"Entry is {row['status']}; only submitted entries can be decided")
    if row["createdById"] == user["id"]:
        raise forbidden("You cannot approve or reject an entry you entered yourself")
    period = next((p for p in periods.list_periods(db) if p["period"] == row["month"]), None)
    if period is not None and period["status"] == "Locked":
        raise conflict(f"Reporting period {row['month']} is locked")
    if decision == "Reject" and not comment.strip():
        raise unprocessable("A comment is required when rejecting an entry")
    out = repo.update(entry_id, {"status": "Approved" if decision == "Approve" else "Rejected", "reviewer": user["name"], "reviewerId": user["id"],
                                 "reviewComment": comment.strip() or None, "reviewedAt": to_iso(utcnow())})
    assert out is not None
    audit(db, user, "Approved" if decision == "Approve" else "Rejected", entry_id, f"Scope 3 entry {decision.lower()}d. {comment.strip()}".strip())
    return out
