"""Persistence for the editable validation configuration (single document in the reference store)."""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.reference import ReferenceRepository
from app.services.common import audit
from app.services.validation import DEFAULT_CONFIG, Limit, ValidationConfig

KEY = "validationRules"


def to_dict(c: ValidationConfig) -> dict[str, Any]:
    return {
        "spikeEnabled": c.spike_enabled, "spikePct": c.spike_pct, "highPct": c.high_pct,
        "historyMonths": c.history_months, "spikeBlockHigh": c.spike_block_high,
        "zeroEnabled": c.zero_enabled, "zeroBlock": c.zero_block,
        "limits": [{"field": l.field, "max": l.max, "enabled": l.enabled, "block": l.block} for l in c.limits],
        "inspectionIntervalDays": c.inspection_interval_days, "energyVariancePct": c.energy_variance_pct,
    }


def from_dict(d: Mapping[str, Any]) -> ValidationConfig:
    base = DEFAULT_CONFIG
    return ValidationConfig(
        spike_enabled=d.get("spikeEnabled", base.spike_enabled), spike_pct=float(d.get("spikePct", base.spike_pct)),
        high_pct=float(d.get("highPct", base.high_pct)), history_months=int(d.get("historyMonths", base.history_months)),
        spike_block_high=d.get("spikeBlockHigh", base.spike_block_high),
        zero_enabled=d.get("zeroEnabled", base.zero_enabled), zero_block=d.get("zeroBlock", base.zero_block),
        limits=tuple(Limit(l["field"], float(l["max"]), l.get("enabled", True), l.get("block", False)) for l in d["limits"])
        if "limits" in d else base.limits,
        inspection_interval_days=int(d.get("inspectionIntervalDays", base.inspection_interval_days)),
        energy_variance_pct=float(d.get("energyVariancePct", base.energy_variance_pct)),
    )


def load(db: Database) -> ValidationConfig:
    items = ReferenceRepository(db).get_items(KEY) or []
    return from_dict(items[0]) if items else DEFAULT_CONFIG


def save(db: Database, user: Mapping[str, Any], config: ValidationConfig) -> dict[str, Any]:
    doc = {"id": "default", **to_dict(config)}
    ReferenceRepository(db).set_items(KEY, [doc])
    audit(db, user, "Saved", "validation-rules",
          f"Validation rules updated: spike ≥{config.spike_pct:g}% (high ≥{config.high_pct:g}%), "
          f"{len([l for l in config.limits if l.enabled])} control limit(s), inspection interval {config.inspection_interval_days} days, energy anomaly band ±{config.energy_variance_pct:g}%.")
    return to_dict(config)
