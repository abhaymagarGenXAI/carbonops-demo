"""Keeps energy records in step with submissions (one source of truth) and reconciles legacy data."""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.energy import EnergyRecordRepository
from app.repositories.facility import FacilityRepository
from app.repositories.reference import ReferenceRepository
from app.repositories.submission import SubmissionRepository
from app.services import carbon_engine as ce
from app.db import collections as C
from app.services import energy_engine as ee
from app.services import rules_config
from app.services.common import audit, conflict
from app.utils.time import to_display, utcnow

COMPARE = ("quantity", "unit", "variance", "validation", "energyGj", "submissionId", "excluded", "submissionStatus")


def _apply(repo: EnergyRecordRepository, rec: Mapping[str, Any], *, dry_run: bool) -> tuple[str, dict[str, Any] | None]:
    """Create or update one derived record, preserving user-owned meter/invoice/cost. Returns (action, old)."""
    old = repo.get_raw(rec["id"])
    if old is None:
        if not dry_run:
            sid = repo.col.database[C.ENERGY_STREAMS].find_one({"streamName": rec.get("stream")}, {"_id": 0, "streamId": 1})
            repo.create({**rec, "energyStreamId": sid["streamId"] if sid else None, "meterRef": "", "invoiceRef": "", "cost": 0})
        return "create", None
    if all(old.get(k, False if k == "excluded" else None) == rec[k] for k in COMPARE):
        return "unchanged", old
    if not dry_run:
        repo.update(rec["id"], {k: rec[k] for k in COMPARE})
    return "update", old


def _derive(subs_by_month: Mapping[str, Mapping[str, Any]], facility: Mapping[str, Any], month: str, band: float = ee.VARIANCE_BAND_PCT):
    sub = subs_by_month[month]
    prev = subs_by_month.get(ce.prev_month(month))
    if prev is not None and prev["status"] in ee.EXCLUDED_STATUSES:
        prev = None  # never compare against unfinished / rejected figures
    return ee.derive_records(facility_id=facility["id"], facility_code=facility["code"], submission=sub,
                             prev_data=prev["data"] if prev else None, band=band)


def sync_submission_energy(db: Database, sub: Mapping[str, Any]) -> None:
    """Called whenever a submission is saved/reviewed. Also refreshes the next month's variance."""
    facility = FacilityRepository(db).get(sub["facilityId"])
    if facility is None:
        return
    band = rules_config.load(db).energy_variance_pct
    subs = {s["month"]: s for s in SubmissionRepository(db).list({"facilityId": sub["facilityId"]})}
    repo = EnergyRecordRepository(db)
    for month in (sub["month"], ce.next_month(sub["month"])):
        if month in subs:
            for rec in _derive(subs, facility, month, band):
                _apply(repo, rec, dry_run=False)


def reconcile(db: Database, user: Mapping[str, Any], *, month: str | None, facility_id: str | None, dry_run: bool) -> dict[str, Any]:
    """Recompute every energy record from submissions. Locked periods are skipped; dry_run writes nothing."""
    filters = {k: v for k, v in {"facilityId": facility_id}.items() if v}
    facilities = {f["id"]: f for f in FacilityRepository(db).list()}
    locked = {p.get("period") for p in (ReferenceRepository(db).get_items("reportingPeriods") or []) if p.get("status") == "Locked"}
    all_subs: dict[str, dict[str, Any]] = {}
    for s in SubmissionRepository(db).list(filters):
        all_subs.setdefault(s["facilityId"], {})[s["month"]] = s
    repo = EnergyRecordRepository(db)
    band = rules_config.load(db).energy_variance_pct
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    items: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    locked_skips: dict[str, int] = {}
    evaluated = 0
    for fid, by_month in all_subs.items():
        facility = facilities.get(fid)
        if facility is None:
            skipped.append({"target": fid, "reason": f"Facility {fid} not found"})
            continue
        for m in sorted(by_month):
            if (month and m != month):
                continue
            if m in locked:
                locked_skips[m] = locked_skips.get(m, 0) + 1
                continue
            evaluated += 1
            for rec in _derive(by_month, facility, m, band):
                action, old = _apply(repo, rec, dry_run=dry_run)
                counts[{"create": "created", "update": "updated", "unchanged": "unchanged"}[action]] += 1
                if action != "unchanged" and len(items) < 500:
                    items.append({
                        "id": rec["id"], "facilityId": fid, "month": m, "stream": rec["stream"], "action": action,
                        "oldQuantity": old.get("quantity") if old else None, "newQuantity": rec["quantity"],
                        "oldValidation": old.get("validation") if old else None, "newValidation": rec["validation"],
                        "oldVariance": old.get("variance") if old else None, "newVariance": rec["variance"],
                        "excluded": rec["excluded"],
                    })
    skipped += [{"target": m, "reason": f"Reporting period {m} is locked; {n} submission(s) not reconciled"} for m, n in sorted(locked_skips.items())]
    if not dry_run and (counts["created"] or counts["updated"]):
        audit(db, user, "Reconciled", "energy-records",
              f"{counts['updated']} updated, {counts['created']} created from submissions ({month or 'all periods'}).")
    return {"dryRun": dry_run, "evaluated": evaluated, **counts, "skipped": skipped, "items": items}


def guard_derived_edit(current: Mapping[str, Any], changes: Mapping[str, Any]) -> None:
    touched = [k for k in ee.DERIVED_FIELDS if k in changes]
    if touched and current.get("submissionId"):
        raise conflict(f"{', '.join(touched)} are derived from submission {current['submissionId']}; "
                       "correct the submission instead. Only meter reference, invoice reference and cost can be edited here.")
