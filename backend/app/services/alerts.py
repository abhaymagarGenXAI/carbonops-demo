"""Live alerts computed from stored data (replaces the static `aiAlerts` seed list).

Rule-based, deterministic and traceable: every alert names the submission it came from.
An alert exists only while someone still has to act:
  * Rework requested / Rejected -> data owner must correct and resubmit (any unlocked period)
  * Draft / not started  -> overdue submission (once past the due date)
  * Submitted / Under Review -> data anomalies (reviewer must decide) and overdue approval
  * Under Review with a clarification request -> rework requested (data owner must act)
  * Rejected -> resubmission required (the rejected figures are not analysed any further)
  * Approved -> nothing: the reviewer has already accepted the data
  * Assets (not shut down) whose last inspection is older than the configured interval -> inspection overdue
Thresholds come from the editable validation configuration, never from constants.
"""
from __future__ import annotations

from typing import Any

from pymongo.database import Database

import datetime as dt
import hashlib

from app.db import collections as C
from app.repositories.asset import AssetRepository
from app.repositories.facility import FacilityRepository
from app.repositories.reference import ReferenceRepository
from app.repositories.submission import SubmissionRepository
from app.services import rules_config, validation
from app.utils.time import to_display, utcnow

_SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def _inspection_alerts(db: Database, facilities: list[dict[str, Any]], today: str, interval: int) -> list[dict[str, Any]]:
    """One alert per facility (not per asset, which would bury every other alert): count + the worst offender."""
    now = dt.date.fromisoformat(today) if today else dt.date.today()
    overdue: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for a in AssetRepository(db).list():
        if a.get("status") == "Shutdown":
            continue
        try:
            age = (now - dt.date.fromisoformat(str(a["lastInspection"])[:10])).days
        except (KeyError, ValueError):
            continue
        if age > interval:
            overdue.setdefault(a["facilityId"], []).append((age, a))
    out: list[dict[str, Any]] = []
    for f in facilities:
        items = sorted(overdue.get(f["id"], []), key=lambda t: -t[0])
        if not items:
            continue
        age, worst = items[0]
        out.append({
            "id": f"ALR-INSP-{f['id']}", "kind": "inspection", "severity": "High" if age > 2 * interval else "Medium",
            "title": f"{len(items)} asset(s) overdue for inspection — {f['name']}",
            "detail": f"Interval is {interval} days. Oldest: {worst['name']} ({worst['id']}), last inspected "
                      f"{worst['lastInspection']} ({age} days ago).",
            "action": "Schedule inspections and update each asset's last-inspection date",
        })
    return out


def _default_period(periods: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The period people are working on: the Open one, else the latest In Review one, else none."""
    open_ = [p for p in periods if p.get("status") == "Open"]
    if open_:
        return open_[-1]
    review = [p for p in periods if p.get("status") == "In Review"]
    return review[-1] if review else None


def fingerprint(alert: dict[str, Any]) -> str:
    """Identity of an alert's CONTENT. A discard only covers this exact condition: if the data changes so the alert reads
    differently (new figures, a new rejection comment) it is a new alert and shows up again."""
    return hashlib.sha1(f"{alert['title']}|{alert['detail']}|{alert['severity']}".encode()).hexdigest()[:16]


def build_alerts(db: Database, period: str | None = None) -> list[dict[str, Any]]:
    """Live alerts minus the ones an Administrator has discarded (see `discard`)."""
    gone = {(d["alertId"], d["fingerprint"]) for d in db[C.ALERT_DISMISSALS].find({}, {"_id": 0, "alertId": 1, "fingerprint": 1})}
    return [a for a in _compute(db, period) if (a["id"], fingerprint(a)) not in gone]


def discard(db: Database, user: dict[str, Any], alert_id: str, period: str | None = None) -> dict[str, Any] | None:
    """Permanently discard one alert (stored as a dismissal record; the alert is never shown again unless its content changes)."""
    alert = next((a for a in build_alerts(db, period) if a["id"] == alert_id), None)
    if alert is None:
        return None
    db[C.ALERT_DISMISSALS].insert_one({
        "alertId": alert["id"], "fingerprint": fingerprint(alert), "kind": alert.get("kind", ""), "severity": alert["severity"],
        "title": alert["title"], "detail": alert["detail"], "period": period, "dismissedBy": user["name"], "dismissedById": user["id"],
        "dismissedAt": utcnow(),
    })
    return alert


def _compute(db: Database, period: str | None = None) -> list[dict[str, Any]]:
    """`period` selects the reporting month for the period-specific checks (overdue deadlines, data anomalies);
    default = the open / latest in-review period. Rejections and rework requests are action items for the data owner
    in *any* unlocked period, so they are always listed; inspection alerts do not depend on a period."""
    config = rules_config.load(db)
    periods = ReferenceRepository(db).get_items("reportingPeriods") or []
    unlocked = {p["period"] for p in periods if p.get("status") != "Locked"}
    chosen = next((p for p in periods if p["period"] == period), None) if period else _default_period(periods)
    today = (to_display(utcnow()) or "")[:10]
    facilities = FacilityRepository(db).list()
    fac = {f["id"]: f for f in facilities}
    by_fac: dict[str, list[dict[str, Any]]] = {}
    for s in SubmissionRepository(db).list():
        by_fac.setdefault(s["facilityId"], []).append(s)
    due_of = {p["period"]: p for p in periods}

    alerts: list[dict[str, Any]] = _inspection_alerts(db, [f for f in facilities if f.get("active", True) is not False], today, config.inspection_interval_days)

    # --- action items for the data owner, any unlocked period
    for fid, subs in by_fac.items():
        f = fac.get(fid)
        if f is None:
            continue
        for sub in subs:
            if sub["month"] not in unlocked:
                continue
            note = (sub.get("reviewerComments") or "").strip()
            overdue = today > due_of[sub["month"]]["submissionDue"]
            if sub["status"] == "Rejected":
                alerts.append({
                    "id": f"ALR-REJ-{sub['id']}", "kind": "rejected", "submissionId": sub["id"],
                    "severity": "High" if overdue else "Medium",
                    "title": f"Resubmission required — {f['name']} · {sub['month']}",
                    "detail": f"{sub['id']} was rejected by {sub.get('reviewer') or 'the reviewer'}{': ' + note if note else '.'}",
                    "action": "Correct the data in Activity Data and submit again",
                })
            elif sub["status"] == "Under Review" and sub.get("reviewAction") == "Clarification Required":
                alerts.append({
                    "id": f"ALR-RWK-{sub['id']}", "kind": "rework", "submissionId": sub["id"], "severity": "Medium",
                    "title": f"Rework requested — {f['name']} · {sub['month']}",
                    "detail": f"{sub['id']}: {sub.get('reviewer') or 'the reviewer'} asked for clarification{': ' + note if note else '.'}",
                    "action": "Correct the data in Activity Data and submit again",
                })

    # --- period-specific checks
    if chosen is not None and chosen.get("status") != "Locked":
        for f in facilities:
            if f.get("active", True) is False:
                continue  # a deactivated facility is no longer expected to report
            subs = by_fac.get(f["id"], [])
            sub = next((x for x in subs if x["month"] == chosen["period"]), None)
            tag = f"{f['name']} · {chosen['period']}"
            if sub is None or sub["status"] == "Draft":
                if today > chosen["submissionDue"]:
                    alerts.append({
                        "id": f"ALR-DUE-{f['code']}-{chosen['period']}", "kind": "due",
                        "severity": "High" if sub is None else "Medium", "title": f"Submission overdue — {tag}",
                        "detail": f"{chosen['period']} activity data was due {chosen['submissionDue']} and is "
                                  f"{'not started' if sub is None else 'still a draft'}.",
                        "action": "Open Activity Data and submit for review",
                    })
                continue
            if sub["status"] not in ("Submitted", "Under Review"):
                continue  # approved = nothing left to do; rejected is listed above
            for fd in validation.check_activity(sub["data"], validation.history_before(subs, sub["month"]), config):
                alerts.append({
                    "id": f"ALR-{sub['id']}-{fd.field}-{fd.code}", "kind": "anomaly", "submissionId": sub["id"],
                    "severity": fd.severity, "title": f"{fd.label} anomaly — {tag}", "detail": fd.message,
                    "action": f"Review submission {sub['id']}",
                })
            if today > chosen["approvalDue"]:
                alerts.append({
                    "id": f"ALR-APR-{sub['id']}", "kind": "approval", "submissionId": sub["id"], "severity": "Medium",
                    "title": f"Approval overdue — {tag}",
                    "detail": f"{sub['id']} awaited approval past the {chosen['approvalDue']} deadline.",
                    "action": f"Review submission {sub['id']}",
                })
    return sorted(alerts, key=lambda a: (_SEV_ORDER.get(a["severity"], 9), a["id"]))
