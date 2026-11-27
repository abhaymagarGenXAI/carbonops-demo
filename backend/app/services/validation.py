"""Activity-data validation rules — pure functions, no I/O.

Every rule is driven by a `ValidationConfig` (editable by a Sustainability Manager, stored in the database), so
thresholds are never hard-coded. Each finding is explainable: it names the field, the reported value and the
reference it was compared with. A rule can be set to *block*: a submission with a blocking finding cannot be
submitted until the data is corrected (drafts can always be saved).
"""
from __future__ import annotations

from dataclasses import replace, dataclass, field
from typing import Any, Mapping, Sequence

# activity field -> (label, unit) for the sources that drive emissions
WATCHED: dict[str, tuple[str, str]] = {
    "electricity": ("Electricity", "kWh"),
    "diesel": ("Diesel", "L"),
    "naturalGas": ("Natural gas", "SCM"),
    "steam": ("Steam", "t"),
    "flareGas": ("Flare gas", "SCM"),
    "methaneLeak": ("Methane leakage", "kg"),
}


@dataclass(frozen=True)
class Limit:
    """Absolute monthly ceiling for one activity field."""
    field: str
    max: float
    enabled: bool = True
    block: bool = False


@dataclass(frozen=True)
class ValidationConfig:
    spike_enabled: bool = True
    spike_pct: float = 30.0  # |deviation from rolling mean| at/above this raises a finding
    high_pct: float = 50.0  # at/above this the finding is High severity instead of Medium
    history_months: int = 3  # how many earlier non-draft months form the reference mean
    spike_block_high: bool = False  # block submission when a spike finding is High
    zero_enabled: bool = True
    zero_block: bool = False
    limits: tuple[Limit, ...] = (Limit("diesel", 250_000),)  # the original built-in rule
    energy_variance_pct: float = 14.0  # Energy Management: |month-on-month variance| above this marks a record as an Anomaly
    inspection_interval_days: int = 150  # asset inspection considered overdue after this many days


DEFAULT_CONFIG = ValidationConfig()


@dataclass(frozen=True)
class Finding:
    code: str  # <FIELD>_LIMIT | SPIKE | ZERO
    severity: str  # High | Medium
    field: str
    label: str
    message: str
    deviation_pct: float | None = None
    blocking: bool = False


def _num(data: Mapping[str, Any], key: str) -> float:
    return float(data.get(key, 0) or 0)


def check_activity(
    data: Mapping[str, Any], history: Sequence[Mapping[str, Any]] = (), config: ValidationConfig = DEFAULT_CONFIG
) -> list[Finding]:
    """`history` = activity data of earlier months, most recent first (only `config.history_months` are used)."""
    findings: list[Finding] = []
    for lim in config.limits:
        if lim.enabled and _num(data, lim.field) > lim.max:
            label, unit = WATCHED.get(lim.field, (lim.field, ""))
            findings.append(Finding(f"{lim.field.upper()}_LIMIT", "High", lim.field, label,
                                    f"{label} consumption above facility control limit ({lim.max:,.0f} {unit})",
                                    blocking=lim.block))
    past = list(history)[: config.history_months]
    if not past:
        return findings
    n = len(past)
    for fld, (label, unit) in WATCHED.items():
        mean = sum(_num(h, fld) for h in past) / n
        if mean <= 0:
            continue
        value = _num(data, fld)
        dev = (value - mean) / mean * 100
        ref = f"{n}-month mean {mean:,.0f} {unit}"
        if value == 0:
            if config.zero_enabled:
                findings.append(Finding("ZERO", "High", fld, label,
                                        f"{label} reported as zero but the {ref} is positive — missing data?", -100.0,
                                        blocking=config.zero_block))
        elif config.spike_enabled and abs(dev) >= config.spike_pct:
            high = abs(dev) >= config.high_pct
            direction = "above" if dev > 0 else "below"
            findings.append(Finding("SPIKE", "High" if high else "Medium", fld, label,
                                    f"{label} {value:,.0f} {unit} is {abs(dev):.0f}% {direction} the {ref}", round(dev, 1),
                                    blocking=high and config.spike_block_high))
    return findings


def unit_history(subs: Sequence[Mapping[str, Any]], month: str, unit: str) -> list[Mapping[str, Any]]:
    """One production unit's figures in earlier non-draft submissions, newest first (older single-unit records count too)."""
    out: list[Mapping[str, Any]] = []
    for s in sorted((s for s in subs if s["month"] < month and s["status"] != "Draft"), key=lambda s: s["month"], reverse=True):
        lines = s.get("unitData") or [{"unit": s.get("unit"), "data": s.get("data", {})}]
        out.extend(ln["data"] for ln in lines if ln.get("unit") == unit)
    return out


def unit_findings(
    lines: Sequence[tuple[str, Mapping[str, Any]]], subs: Sequence[Mapping[str, Any]], month: str, config: ValidationConfig
) -> list[tuple[str, Finding]]:
    """Spike / zero checks per production unit against that unit's own history, so a spike in one unit cannot hide behind a quiet
    one. Facility control limits stay facility-level. Only for multi-unit submissions."""
    if len(lines) < 2:
        return []
    cfg = replace(config, limits=())
    out: list[tuple[str, Finding]] = []
    for unit, data in lines:
        out.extend((unit, f) for f in check_activity(data, unit_history(subs, month, unit), cfg))
    return out


def history_before(subs: Sequence[Mapping[str, Any]], month: str) -> list[Mapping[str, Any]]:
    """Activity data of one facility's earlier non-draft submissions, most recent first."""
    prior = [s for s in subs if s["month"] < month and s["status"] != "Draft"]
    return [s["data"] for s in sorted(prior, key=lambda s: s["month"], reverse=True)]
