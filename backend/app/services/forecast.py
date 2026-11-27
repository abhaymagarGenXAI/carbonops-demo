"""Forecast of approved emissions per scope, plus an outlook against the configured targets."""
from __future__ import annotations

from typing import Any

from pymongo.database import Database

from app.repositories.emission import EmissionRecordRepository
from app.services import forecast_engine as fe
from app.services import targets as targets_svc
from app.services import targets_engine as te
from app.services.common import unprocessable


def build(db: Database, horizon: int = 12) -> dict[str, Any]:
    if not 1 <= horizon <= 24:
        raise unprocessable("horizon must be between 1 and 24 months")
    view = targets_svc.get_targets(db)
    agg = te.aggregate(EmissionRecordRepository(db).list())
    fac = targets_svc._facility_ids(db)
    complete = te.complete_months(agg, fac)
    months = fe.consecutive_tail(complete)
    out: dict[str, Any] = {"horizon": horizon, "method": fe.METHOD, "minMonths": fe.MIN_POINTS, "completeMonths": len(complete),
                           "usedMonths": months, "scopes": {}, "outlook": [], "warnings": [], "available": False}
    if len(months) < fe.MIN_POINTS:
        out["warnings"].append(
            f"Not enough history: a forecast needs at least {fe.MIN_POINTS} consecutive complete approved months; "
            f"{len(months)} available. Approve the remaining facility submissions first.")
        return out
    out["available"] = True
    results = {}
    for scope in ("Total", "Scope 1", "Scope 2"):
        res = fe.forecast_series(months, [agg[m][scope] for m in months], horizon)
        results[scope] = res
        out["scopes"][scope] = {k: v for k, v in res.items() if not k.startswith("_")}
    if len(months) < 8:
        out["warnings"].append(f"Only {len(months)} months of history — the band is wide and the trend may be unreliable.")
    if out["scopes"]["Total"]["fit"]["r2"] < 0.3:
        out["warnings"].append("The months do not follow a clear straight-line trend (low R²); the projection is a weak guide.")
    base = view["baseline"]
    if base:
        for t in view["targets"]:
            o = fe.target_outlook(results[t["scope"]], base, t)
            out["outlook"].append(o)
    return out
