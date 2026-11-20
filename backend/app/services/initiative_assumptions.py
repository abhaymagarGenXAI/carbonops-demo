"""Editable economic assumptions for initiatives (single document in the reference store)."""
from __future__ import annotations

from typing import Any, Mapping

from pymongo.database import Database

from app.repositories.reference import ReferenceRepository
from app.services.common import audit
from app.services.initiatives_engine import DEFAULTS

KEY = "initiativeAssumptions"


def load(db: Database) -> dict[str, Any]:
    items = ReferenceRepository(db).get_items(KEY) or []
    doc = items[0] if items else {}
    return {k: type(v)(doc.get(k, v)) for k, v in DEFAULTS.items()}


def save(db: Database, user: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: type(v)(values[k]) for k, v in DEFAULTS.items()}
    ReferenceRepository(db).set_items(KEY, [{"id": "default", **out}])
    audit(db, user, "Saved", "initiative-assumptions",
          f"Carbon value ₹{out['carbonValuePerTonne']:,.0f}/tCO₂e, discount rate {out['discountRatePct']:g}%, lifetime {out['lifetimeYears']} years.")
    return out
