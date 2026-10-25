"""Ship size (DWT or GT) for EU MRV ships, which MRV does not publish. Decision 0007-1, note 0008.

Signals, each giving ln(capacity) with a standard deviation:

1. Efficiency index (EEDI / EEXI / EIV published by EMSA). Attained ≈ a·C^(−c)·(1 − X), so
       ln C = (ln a + ln(1 − X) − ln attained) / c,  with X uncertain (see config eedi.json).
   Used where the reference line is steep enough (c ≥ 0.30) to identify size.
2. Fuel per hour at sea (engine power grows with size): ln(F/h) = α + β·ln C, fitted per type to
   the IMO class averages (annual fuel ÷ hours at sea, both including port fuel, as in MRV), so
       ln C = (ln(F/h) − α) / β.
   Used where β ≥ 0.5 (container, gas/LNG, general cargo, ro-pax); for tankers, bulk carriers,
   cruise ships and car carriers boilers or hotel load blur the relation.
3. Size mix of the ship type in EU trade (Fourth IMO GHG Study, Table 92: EU MRV ships by type and
   size class, 2018) as a wide reference range for the type.

They are combined by inverse-variance weighting:  μ = Σ wᵢμᵢ / Σ wᵢ,  σ² = 1/Σ wᵢ,  wᵢ = 1/σᵢ².
The result is an Estimate (low, likely, high) = exp(μ − 2σ, μ, μ + 2σ), sampled as PERT by SMAA.
With only the type range available the estimate is flagged so the user confirms the actual size.

A further signal, fuel per mile inverted through a fitted admiralty relation
ln(F/d) = α + β·ln C + 2·ln v, was tested and rejected: fuel per mile changes too little with size
(β ≈ 0.2–0.4 in the IMO class data), so inversion amplifies errors and placed 35% of 2018 bulk
carriers in the largest class against 0.7% in the IMO study (docs/validation/size-estimate.md).
The code is kept (`fuel_signal`) for that comparison.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache, lru_cache

import numpy as np

from . import params as _params
from . import reference as R
from .uncertainty import Estimate

# CII ship type → capacity unit used by CII and by the estimate
CII_UNIT = {"bulk": "dwt", "gas": "dwt", "tanker": "dwt", "container": "dwt", "general_cargo": "dwt", "reefer": "dwt",
            "combination": "dwt", "lng": "dwt", "vehicle": "gt", "roro": "gt", "ropax": "gt", "cruise": "gt"}
# MRV ship type → EEDI reference line
MRV_TO_EEDI = {"Bulk carrier": "bulk", "Combination carrier": "combination", "Oil tanker": "tanker",
               "Chemical tanker": "tanker", "Container ship": "container", "Gas carrier": "gas", "LNG carrier": "lng",
               "General cargo ship": "general_cargo", "Refrigerated cargo carrier": "reefer",
               "Passenger ship (Cruise Passenger ship)": "cruise"}
SPEED_EXP = 2.0
MIN_SIGMA = 0.05
MIN_BETA = 0.25          # below this, fuel per mile barely changes with size and cannot identify it
MIN_BETA_HOUR = 0.50     # fuel per hour: only types where it identifies size (validated against IMO Table 92)
SHIP_SIGMA_HOUR = 0.30   # spread of an individual ship's fuel per hour around its class average (ln)
MAX_SIGMA = 0.60         # a signal vaguer than ±0.6 in ln (×1.8) is not used
FIT_GROUP = {"oil": ("oil", "chemical"), "chemical": ("oil", "chemical")}


@dataclass(frozen=True)
class Fit:
    imo_type: str
    unit: str          # dwt | gt
    alpha: float
    beta: float
    sigma: float       # residual standard deviation of ln(F/d) on class averages
    cap_min: float
    cap_max: float


def _capacity_of(c: R.SizeClass, unit: str) -> float:
    return c.gt_mid if unit == "gt" else c.value("dwt")


@cache
def fit(imo_type: str, unit: str) -> Fit | None:
    """Least squares on all classes and years of the type, weighted by √(number of ships)."""
    xs, ys, ws = [], [], []
    for c in [c for t in FIT_GROUP.get(imo_type, (imo_type,)) for c in R.of_type(t)]:
        if unit == "gt" and c.unit != "gt":
            continue
        for y in c.years:
            v = c.value("speed_at_sea", y)
            fpn = c.fuel_per_nm(y)
            cap = _capacity_of(c, unit)
            n = c.value("n_type12", y) + c.value("n_type3", y) + c.value("n_type4", y)
            if v > 0 and fpn > 0 and cap > 0 and n > 0:
                xs.append(math.log(cap))
                ys.append(math.log(fpn) - SPEED_EXP * math.log(v))
                ws.append(math.sqrt(n))
    if len(set(round(x, 6) for x in xs)) < 2:
        return None
    x, y, w = np.array(xs), np.array(ys), np.array(ws)
    a = np.vstack([np.ones_like(x), x]).T * w[:, None]
    (alpha, beta), *_ = np.linalg.lstsq(a, y * w, rcond=None)
    resid = y - (alpha + beta * x)
    sigma = float(np.sqrt(np.average(resid ** 2, weights=w)))
    caps = [_capacity_of(c, unit) for c in R.of_type(imo_type)]
    return Fit(imo_type, unit, float(alpha), float(beta), max(sigma, MIN_SIGMA), min(caps) * 0.5, max(caps) * 1.6)


@dataclass(frozen=True)
class Signal:
    name: str          # "fuel" | "index"
    mu: float          # ln capacity
    sigma: float


def fuel_signal(imo_type: str, unit: str, fuel_t: float, distance_nm: float, hours_at_sea: float,
                ship_sigma: float) -> Signal | None:
    f = fit(imo_type, unit)
    if f is None or f.beta < MIN_BETA or not (fuel_t and distance_nm and hours_at_sea):
        return None
    v = distance_nm / hours_at_sea
    if not 3 <= v <= 30:
        return None
    mu = (math.log(fuel_t * 1000 / distance_nm) - SPEED_EXP * math.log(v) - f.alpha) / f.beta
    sigma = math.hypot(f.sigma, ship_sigma) / f.beta
    return Signal("fuel", mu, sigma) if sigma <= MAX_SIGMA * 2 else None


@cache
def fit_hour(imo_type: str, unit: str) -> Fit | None:
    xs, ys, ws = [], [], []
    for c in R.of_type(imo_type):
        if unit == "gt" and c.unit != "gt":
            return None
        for v in c.years.values():
            kt = v["fuel_main_kt"] + v["fuel_aux_kt"] + v["fuel_boiler_kt"]
            n = v["n_type12"] + v["n_type3"] + v["n_type4"]
            if v["days_at_sea"] > 0 and kt > 0 and n > 0:
                xs.append(math.log(_capacity_of(c, unit)))
                ys.append(math.log(kt * 1000 / (v["days_at_sea"] * 24)))
                ws.append(math.sqrt(n))
    if len(set(round(x, 6) for x in xs)) < 2:
        return None
    x, y, w = np.array(xs), np.array(ys), np.array(ws)
    a = np.vstack([np.ones_like(x), x]).T * w[:, None]
    (alpha, beta), *_ = np.linalg.lstsq(a, y * w, rcond=None)
    sigma = float(np.sqrt(np.average((y - (alpha + beta * x)) ** 2, weights=w)))
    return Fit(imo_type, unit, float(alpha), float(beta), max(sigma, MIN_SIGMA), 0, 0)


def hour_signal(imo_type: str, unit: str, fuel_t: float, hours_at_sea: float) -> Signal | None:
    f = fit_hour(imo_type, unit)
    if f is None or f.beta < MIN_BETA_HOUR or not (fuel_t and hours_at_sea and hours_at_sea > 50):
        return None
    mu = (math.log(fuel_t / hours_at_sea) - f.alpha) / f.beta
    return Signal("hour", mu, math.hypot(f.sigma, SHIP_SIGMA_HOUR) / f.beta)


def index_signal(eedi_type: str | None, index_type: str | None, index_value: float | None, unit: str,
                 rules: dict | None = None) -> Signal | None:
    if not (eedi_type and index_type and index_value and index_value > 0):
        return None
    rules = rules or _eedi_rules()
    line = rules["reference_lines"].get(eedi_type)
    xs = rules["reduction_by_index"].get(index_type.upper())
    if not line or not xs or line["capacity"] != unit or line["c"] < rules["min_slope"]:
        return None
    if xs == "phase":
        xmax = rules["max_reduction"].get(eedi_type, rules["max_reduction"]["default"])
        xs = [0.0, xmax / 2, xmax]
    lo, mid, hi = (math.log(1 - x) for x in xs)
    mu = (math.log(line["a"]) + mid - math.log(index_value)) / line["c"]
    # X spread treated as a uniform-like range → σ ≈ range / √12 in ln(1 − X), scaled by 1/c
    sigma = abs(hi - lo) / math.sqrt(12) / line["c"]
    return Signal("index", mu, max(sigma, MIN_SIGMA)) if sigma <= MAX_SIGMA * 2 else None


@lru_cache(maxsize=1)
def _eedi_rules() -> dict:
    ps = _params.load("eedi")
    return {k: ps[k] for k in ("reference_lines", "reduction_by_index", "max_reduction", "min_slope")}


SHIP_SIGMA = 0.30   # individual ship vs class average in ln(F/d); used only by the rejected fuel signal


@cache
def type_range(imo_type: str, unit: str) -> Signal | None:
    """Size mix of the type among EU MRV ships (IMO Table 92) as a log-normal range."""
    counts = {r["size"]: r["vessels"] for r in R.mrv_2018() if r["type"] == imo_type}
    pts = []
    for c in R.of_type(imo_type):
        if unit == "gt" and c.unit != "gt":
            return None
        n = counts.get(c.size, 0)
        if n:
            pts.append((math.log(_capacity_of(c, unit)), n))
    if not pts:
        return None
    total = sum(n for _, n in pts)
    mu = sum(x * n for x, n in pts) / total
    var = sum(n * (x - mu) ** 2 for x, n in pts) / total
    within = 0.25 ** 2                     # spread of ships around their class average
    return Signal("type", mu, math.sqrt(var + within))


def estimate_capacity(mrv_type: str | None, cii_type: str | None, fuel_t: float | None, distance_nm: float | None,
                      hours_at_sea: float | None, index_type: str | None = None,
                      index_value: float | None = None) -> Estimate | None:
    """Capacity in the CII unit (DWT or GT) of the ship's CII type, or None when it cannot be estimated."""
    unit = CII_UNIT.get(cii_type or "")
    imo_type = R.MRV_TO_IMO.get(mrv_type or "")
    if unit is None or imo_type is None:
        return None
    if unit == "gt" and R.of_type(imo_type) and R.of_type(imo_type)[0].unit != "gt":
        return None                                  # e.g. ro-ro: IMO classes in DWT, CII needs GT
    signals = [s for s in (index_signal(MRV_TO_EEDI.get(mrv_type or ""), index_type, index_value, unit),
                           hour_signal(imo_type, unit, fuel_t or 0, hours_at_sea or 0),
                           type_range(imo_type, unit)) if s]
    if not signals:
        return None
    w = [1 / s.sigma ** 2 for s in signals]
    mu = sum(wi * s.mu for wi, s in zip(w, signals, strict=True)) / sum(w)
    sigma = math.sqrt(1 / sum(w))
    caps = [_capacity_of(c, unit) for c in R.of_type(imo_type)]
    lo_cap, hi_cap = (min(caps) * 0.5, max(caps) * 1.6) if caps else (100, 600_000)
    likely = min(max(math.exp(mu), lo_cap), hi_cap)
    low = min(max(math.exp(mu - 2 * sigma), lo_cap), likely)
    high = max(min(math.exp(mu + 2 * sigma), hi_cap), likely)
    method = "+".join(s.name for s in signals)          # e.g. "index+type", "hour+type"; "type" alone = confirm
    return Estimate(low, likely, high, method=method, source="eedi+imo4",
                    details={"unit": unit, "imo_type": imo_type, "signals": [(s.name, math.exp(s.mu), s.sigma) for s in signals]})
