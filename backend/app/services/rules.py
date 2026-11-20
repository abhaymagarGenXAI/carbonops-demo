"""Business rules that used to live inside React components / the in-memory store.
Pure functions: no I/O, no framework imports."""
from __future__ import annotations

import math
from typing import Any, Mapping

NUMERIC_FIELDS = (
    "productionVolume",
    "electricity",
    "diesel",
    "naturalGas",
    "steam",
    "water",
    "flareGas",
    "methaneLeak",
    "renewable",
    "operatingHours",
)
from app.services.validation import DEFAULT_CONFIG, ValidationConfig, check_activity  # noqa: E402


def js_round(x: float) -> int:
    """JavaScript Math.round / toFixed(0) semantics (half rounds up), unlike Python's banker's rounding."""
    return int(math.floor(x + 0.5))


def completeness(data: Mapping[str, Any]) -> int:
    filled = sum(1 for f in NUMERIC_FIELDS if float(data.get(f, 0) or 0) > 0)
    return js_round(filled / len(NUMERIC_FIELDS) * 100)


def validate_activity(
    status: str, data: Mapping[str, Any], history=(), config: ValidationConfig = DEFAULT_CONFIG
) -> tuple[str, list[str]]:
    """Returns (validation, anomalies). Drafts are not validated. `history` = earlier months' data, newest first.

    Blocking findings never reach this result: `save_submission` refuses to submit them (see `blocking_findings`).
    """
    if status == "Draft":
        return "Not Run", []
    findings = check_activity(data, history, config)
    return ("Warnings" if findings else "Passed"), [f.message for f in findings]


def blocking_findings(data: Mapping[str, Any], history=(), config: ValidationConfig = DEFAULT_CONFIG) -> list[str]:
    return [f.message for f in check_activity(data, history, config) if f.blocking]


def submission_id(facility_code: str, month: str) -> str:
    return f"SUB-{facility_code}-{month.replace('-', '')}"


def advance_initiative(
    *, expected_reduction: float, completion: float, timeline: str, step: int = 10
) -> dict[str, Any]:
    nxt = min(100, completion + step)
    done = nxt >= 100
    return {
        "completion": nxt,
        "status": "Completed" if done else "In Progress",
        "timeline": "Complete" if done else timeline,
        # actualReduction is deliberately NOT estimated here: it is a measured / M&V-verified figure entered by the owner.
    }


def default_milestones(start_date: str, end_date: str) -> list[dict[str, Any]]:
    return [
        {"name": "Concept approval", "date": start_date, "done": False},
        {"name": "Detailed engineering", "date": start_date, "done": False},
        {"name": "Commissioning", "date": end_date, "done": False},
    ]
