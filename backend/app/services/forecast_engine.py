"""Emissions trend forecast — pure functions, no I/O.

Method (printed with every forecast, nothing hidden): ordinary least-squares straight line through the most recent complete,
approved months (x = month number, y = tCO2e). Projection = the line extended forward. The band is the classical ~95 % *prediction*
interval  ŷ ± t · s · sqrt(1 + 1/n + (x − x̄)² / Sxx)  with s the residual standard deviation. It is a statistical trend, not a
plan: seasonality, planned initiatives, factor changes and production changes are NOT modelled.
"""
from __future__ import annotations

from math import sqrt
from typing import Any, Mapping, Sequence

from app.services.targets_engine import allowed_monthly, month_index, month_str

MIN_POINTS = 4
MAX_POINTS = 12
# two-sided 97.5 % Student-t quantiles for df = 1..30 (df > 30 -> 1.96)
_T = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110,
      2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]

METHOD = [
    "Method: least-squares straight line through the last complete approved months (a month is complete when every facility has approved records).",
    "The band is an approximate 95 % prediction interval from the scatter of those months around the line.",
    "Not modelled: seasonality, planned initiatives, production changes, emission-factor changes. Treat it as a trend check, not a commitment.",
]


def t_value(df: int) -> float:
    return _T[df - 1] if 1 <= df <= 30 else 1.96


def fit(values: Sequence[float]) -> dict[str, float]:
    n = len(values)
    xs = list(range(n))
    xbar, ybar = sum(xs) / n, sum(values) / n
    sxx = sum((x - xbar) ** 2 for x in xs)
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, values)) / sxx
    intercept = ybar - slope * xbar
    sse = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, values))
    sst = sum((y - ybar) ** 2 for y in values)
    s = sqrt(sse / (n - 2)) if n > 2 else 0.0
    return {"n": n, "slope": slope, "intercept": intercept, "s": s, "sxx": sxx, "xbar": xbar, "r2": 1 - sse / sst if sst else 1.0}


def predict(m: Mapping[str, float], x: float) -> tuple[float, float, float]:
    y = m["intercept"] + m["slope"] * x
    half = t_value(int(m["n"]) - 2) * m["s"] * sqrt(1 + 1 / m["n"] + (x - m["xbar"]) ** 2 / m["sxx"])
    return y, y - half, y + half


def forecast_series(months: Sequence[str], values: Sequence[float], horizon: int) -> dict[str, Any]:
    """`months` must be consecutive complete months. Returns the fit, history and projected months."""
    m = fit(values)
    last = month_index(months[-1])
    rows = []
    for k in range(1, horizon + 1):
        y, lo, hi = predict(m, m["n"] - 1 + k)
        rows.append({"month": month_str(last + k), "value": round(max(y, 0.0), 2), "low": round(max(lo, 0.0), 2), "high": round(max(hi, 0.0), 2)})
    return {
        "fit": {"months": int(m["n"]), "slopePerMonth": round(m["slope"], 2), "r2": round(m["r2"], 3), "residualSd": round(m["s"], 2),
                "slopePctPerMonth": round(m["slope"] / (sum(values) / len(values)) * 100, 2) if sum(values) else 0.0},
        "history": [{"month": a, "value": round(b, 2)} for a, b in zip(months, values)],
        "projection": rows, "_model": m, "_last": last,
    }


def consecutive_tail(months: Sequence[str], limit: int = MAX_POINTS) -> list[str]:
    """Longest run of consecutive months ending at the latest month (gaps would distort a time trend), capped at `limit`."""
    run: list[str] = []
    for mo in reversed(sorted(months)):
        if run and month_index(run[-1]) - month_index(mo) != 1:
            break
        run.append(mo)
    return list(reversed(run))[-limit:]


def target_outlook(res: Mapping[str, Any], baseline: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    """Where the trend line will be in December of the target year vs the monthly level the target allows then."""
    scope, pct, year = target["scope"], float(target["reductionPct"]), int(target["targetYear"])
    m, last = res["_model"], res["_last"]
    k = month_index(f"{year}-12") - last
    allowed = allowed_monthly(baseline, scope, pct, year, f"{year}-12")
    if k < 1:
        return {"scope": scope, "targetYear": year, "reductionPct": pct, "applicable": False}
    y, lo, hi = predict(m, m["n"] - 1 + k)
    y, lo, hi = max(y, 0.0), max(lo, 0.0), max(hi, 0.0)
    verdict = "Projected to meet" if y <= allowed else "Projected to miss"
    return {
        "scope": scope, "targetYear": year, "reductionPct": pct, "applicable": True, "monthsAhead": k,
        "projectedMonthly": round(y, 2), "projectedLow": round(lo, 2), "projectedHigh": round(hi, 2), "allowedMonthly": round(allowed, 2),
        "gapMonthly": round(y - allowed, 2), "gapPct": round((y - allowed) / allowed * 100, 1) if allowed else None, "verdict": verdict,
        "certainty": ("Meets the target even at the upper bound" if hi <= allowed else
                      "Misses the target even at the lower bound" if lo > allowed else "Band straddles the target level — inconclusive"),
    }
