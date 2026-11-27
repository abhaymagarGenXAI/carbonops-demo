"""Carbon accounting service: turns submission activity data into traceable emission records."""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.emission import EmissionRecordRepository
from app.repositories.emission_factor import EmissionFactorRepository
from app.repositories.scope3 import Scope3Repository
from app.repositories.facility import FacilityRepository
from app.repositories.reference import ReferenceRepository
from app.repositories.submission import SubmissionRepository
from app.services import carbon_engine as ce
from app.services import energy, masters
from app.services.common import audit, conflict, unprocessable
from app.utils.time import to_display, utcnow

TRACE_FIELDS = ("factorId", "submissionId", "formula", "calcNote", "calculatedAt")
NUMERIC_FIELDS = ("activityValue", "factor", "factorUnit", "factorRef", "co2e", "prevCo2e")
# Factor attributes that define what a number means; frozen once a record cites the factor.
FROZEN_FACTOR_FIELDS = ("source", "scope", "value", "unit", "validFrom")


def _index(record_id: str) -> int:
    return int(record_id.rsplit("-", 1)[1]) - 1


def _prev_co2e(repo: EmissionRecordRepository, code: str, month: str, idx: int, own: float) -> float:
    prev = repo.get_raw(ce.record_id(code, ce.prev_month(month), idx))
    return float(prev["co2e"]) if prev else own  # first period compares with itself (same as seed data)


def _relink_next_month(repo: EmissionRecordRepository, code: str, month: str, idx: int, co2e: float) -> None:
    repo.col.update_one({"emissionId": ce.record_id(code, ce.next_month(month), idx)}, {"$set": {"prevCo2e": co2e}})


def _build(db: Database, sub: Mapping[str, Any], factors: list[Mapping[str, Any]] | None = None):
    facility = FacilityRepository(db).get(sub["facilityId"])
    if facility is None:
        return None, [], [f"Facility {sub['facilityId']} not found"]
    factors = factors if factors is not None else EmissionFactorRepository(db).list()
    records, problems = ce.build_records(
        facility_id=sub["facilityId"], facility_code=facility["code"], month=sub["month"],
        submission_id=sub["id"], submission_status=sub["status"], data=sub["data"], factors=factors,
        source_ids=masters.source_ids(db),
    )
    return facility, records, problems


# --------------------------------------------------------------------------- sync (on submit / review)
def sync_submission_emissions(db: Database, user: Mapping[str, Any], sub: Mapping[str, Any]) -> list[str]:
    """Create/refresh the six emission records of a submission; statuses follow the submission status.

    Existing review comments are preserved. Returns calculation problems (e.g. missing factor), which
    never block data entry but are written to the audit trail.
    """
    facility, records, problems = _build(db, sub)
    repo = EmissionRecordRepository(db)
    stamp = to_display(utcnow())
    for rec in records:
        idx = _index(rec["id"])
        fields = {**rec, "prevCo2e": _prev_co2e(repo, facility["code"], rec["month"], idx, rec["co2e"]), "calculatedAt": stamp}
        if repo.get_raw(rec["id"]) is None:
            repo.create({**fields, "comments": []})
        else:
            repo.update(rec["id"], {k: v for k, v in fields.items() if k != "id"})
        _relink_next_month(repo, facility["code"], rec["month"], idx, rec["co2e"])
    if records:
        total = sum(r["co2e"] for r in records)
        audit(db, user, "Calculated", sub["id"], f"{len(records)} emission records for {sub['month']} calculated: {total:,.2f} tCO₂e.")
    if problems:
        audit(db, user, "Calculation warning", sub["id"], "Carbon calculation incomplete — " + "; ".join(problems))
    return problems


# --------------------------------------------------------------------------- recalculation
def recalculate(
    db: Database, user: Mapping[str, Any], *, month: str | None, facility_id: str | None, dry_run: bool
) -> dict[str, Any]:
    """Recompute emission records from stored activity data with the factors effective for each period.

    * dry_run=True reports what would change and writes nothing.
    * Locked reporting periods are skipped.
    * Review/calc statuses are left alone, except that an Approved record whose figure changes goes back
      to 'Under Review' with a system comment, so changed numbers are always re-approved.
    """
    filters = {k: v for k, v in {"facilityId": facility_id, "month": month}.items() if v}
    subs = sorted(SubmissionRepository(db).list(filters), key=lambda s: (s["facilityId"], s["month"]))
    locked = {p.get("period") for p in (ReferenceRepository(db).get_items("reportingPeriods") or []) if p.get("status") == "Locked"}
    factors = EmissionFactorRepository(db).list()
    repo = EmissionRecordRepository(db)
    stamp = to_display(utcnow())

    items: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    counts = {"created": 0, "updated": 0, "traceLinked": 0, "unchanged": 0}
    locked_skips: dict[str, int] = {}
    reopened: set[str] = set()

    for sub in subs:
        if sub["month"] in locked:
            locked_skips[sub["month"]] = locked_skips.get(sub["month"], 0) + 1
            continue
        facility, records, problems = _build(db, sub, factors)
        skipped += [{"target": sub["id"], "reason": p} for p in problems]
        for rec in records:
            old = repo.get_raw(rec["id"])
            idx = _index(rec["id"])
            if old is None:
                action = "create"
            elif ce.numerically_different(old, rec):
                action = "update"
            elif "factorId" not in old:
                action = "link"
            else:
                counts["unchanged"] += 1
                continue

            if action in ("create", "update"):
                reasons = []
                if old is not None:
                    if abs(float(old["factor"]) - float(rec["factor"])) > 1e-12:
                        reasons.append(f"factor {old['factor']} → {rec['factor']} ({rec['factorId']})")
                    if abs(float(old["activityValue"]) - rec["activityValue"]) > 1e-9:
                        reasons.append("activity data changed")
                items.append(
                    {
                        "id": rec["id"], "facilityId": rec["facilityId"], "month": rec["month"], "source": rec["source"],
                        "action": action, "oldCo2e": float(old["co2e"]) if old else None, "newCo2e": rec["co2e"],
                        "oldFactor": float(old["factor"]) if old else None, "newFactor": rec["factor"],
                        "factorId": rec["factorId"], "reason": "; ".join(reasons) or ("new record" if old is None else "recalculated"),
                    }
                )
            counts[{"create": "created", "update": "updated", "link": "traceLinked"}[action]] += 1
            if dry_run:
                continue

            if action == "create":
                prev = _prev_co2e(repo, facility["code"], rec["month"], idx, rec["co2e"])
                repo.create({**rec, "prevCo2e": prev, "calculatedAt": stamp, "comments": []})
            elif action == "update":
                prev = _prev_co2e(repo, facility["code"], rec["month"], idx, rec["co2e"])
                changes = {k: rec[k] for k in ("activityValue", "factor", "factorUnit", "factorRef", "co2e", *TRACE_FIELDS[:4], "factorVersionId", "emissionSourceId")}
                changes.update(prevCo2e=prev, calculatedAt=stamp)
                if old.get("reviewStatus") == "Approved":
                    changes["reviewStatus"] = "Under Review"
                    text = f"Recalculated: {float(old['co2e']):,.2f} → {rec['co2e']:,.2f} tCO₂e. Re-approval required."
                    changes["comments"] = [{"by": user["name"], "at": stamp, "text": text}, *old.get("comments", [])]
                repo.update(rec["id"], changes)
                if changes.get("reviewStatus") == "Under Review":
                    reopened.add(sub["id"])
            else:  # link: numbers identical, only backfill traceability
                repo.update(rec["id"], {k: rec[k] for k in (*TRACE_FIELDS[:4], "factorVersionId", "emissionSourceId")} | {"calculatedAt": stamp})
            _relink_next_month(repo, facility["code"], rec["month"], idx, rec["co2e"])

    # The submission is the unit of approval: a record sent back for re-approval must send its submission back too, otherwise the
    # submission stays "Approved" (final) and nobody can ever approve the record again.
    for sid in sorted(reopened):
        sub_repo = SubmissionRepository(db)
        cur = sub_repo.get_raw(sid)
        if cur is not None and cur["status"] == "Approved":
            note = "Recalculated with changed figures — re-approval required."
            out = sub_repo.update(sid, {"status": "Under Review", "reviewAction": "None", "reviewerComments": note})
            if out is not None:
                energy.sync_submission_energy(db, out)
            audit(db, user, "Under Review", sid, note)

    skipped += [
        {"target": m, "reason": f"Reporting period {m} is locked; {n} submission(s) not recalculated"}
        for m, n in sorted(locked_skips.items())
    ]
    scope_txt = ", ".join(f"{k}={v}" for k, v in {"facility": facility_id, "month": month}.items() if v) or "all periods"
    if not dry_run and (counts["created"] or counts["updated"] or counts["traceLinked"]):
        audit(db, user, "Recalculated", "carbon-inventory",
              f"{counts['updated']} updated, {counts['created']} created, {counts['traceLinked']} trace-linked ({scope_txt}).")
    return {"dryRun": dry_run, "evaluated": len(subs) - sum(locked_skips.values()), **counts, "skipped": skipped, "items": items[:500]}


# --------------------------------------------------------------------------- factor integrity
def validate_factor_definition(db: Database, data: Mapping[str, Any], self_id: str | None = None) -> None:
    try:
        ce.validate_factor(data["source"], data["scope"], data["unit"])
    except ce.FactorError as exc:
        raise unprocessable(str(exc)) from exc
    sid = masters.resolve_source(db, data["source"], data["scope"], data.get("category"), create=False)
    clash: dict[str, Any] = {"emissionSourceId": sid, "validFrom": data["validFrom"]} if sid else {"source": data["source"], "validFrom": data["validFrom"]}
    if self_id:
        clash["factorId"] = {"$ne": self_id}  # type: ignore[assignment]
    if EmissionFactorRepository(db).col.find_one(clash):
        raise conflict(f"A factor for '{data['source']}' valid from {data['validFrom']} already exists")


def _citations(db: Database, factor_id: str) -> int:
    """Emission records and Scope 3 entries that cite the factor version."""
    return EmissionRecordRepository(db).count({"factorId": factor_id}) + Scope3Repository(db).count({"factorId": factor_id})


def guard_factor_in_use(db: Database, current: Mapping[str, Any], changes: Mapping[str, Any]) -> None:
    touched = [k for k in FROZEN_FACTOR_FIELDS if k in changes and changes[k] != current.get(k)]
    if touched and _citations(db, current["id"]):
        raise conflict(
            f"Factor {current['id']} is cited by emission records; {', '.join(touched)} cannot be changed. "
            "Create a new factor version with a later 'valid from' date instead."
        )


def guard_factor_delete(db: Database, factor_id: str) -> None:
    n = _citations(db, factor_id)
    if n:
        raise conflict(f"Factor {factor_id} is cited by {n} emission record(s) and cannot be deleted")


def supersede_older(db: Database, factor: Mapping[str, Any]) -> None:
    """A newly active factor retires the older active versions of the same source."""
    if factor.get("status") != "Active":
        return
    sid = factor.get("emissionSourceId")
    EmissionFactorRepository(db).col.update_many(
        {**({"emissionSourceId": sid} if sid else {"source": factor["source"]}), "status": "Active", "validFrom": {"$lt": factor["validFrom"]}, "factorId": {"$ne": factor["id"]}},
        {"$set": {"status": "Superseded", "updatedAt": utcnow()}},
    )
