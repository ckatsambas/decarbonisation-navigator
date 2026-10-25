"""Worldwide activity from EU-only data. Decisions 0005, 0007-2; method in note 0008.

EU MRV records only voyages that touch the EU. The IMO Net-Zero Framework applies to all of a
ship's international voyages, so its worldwide emissions are needed. Sources, in order:

  (a) user:      the company enters the EU share of its activity.
  (b) estimated: EU share = MRV hours at sea ÷ (days at sea × 24), where the days at sea of the
                 ship's type and size class come from the Fourth IMO GHG Study (2018 value most
                 likely; the 2012–2018 range widened by the individual spread sets min and max).
                 The share is an Estimate (PERT) and is sampled by SMAA in Phase 4.
  (c) reference: the implied worldwide fuel is compared with the study's average annual fuel for
                 the same class, as a plausibility check shown to the user.

The share can never exceed 1 (worldwide activity is at least the EU-recorded activity). Ships whose
most likely share is at or above a threshold are treated as trading mainly in the EU.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import params as _params
from . import reference as R
from .models import AnnualEmissions, ScopeSplit
from .uncertainty import Estimate


@dataclass(frozen=True)
class ActivityRules:
    individual_spread: float
    max_days: float
    eu_dominant_threshold: float

    @classmethod
    def load(cls, override_dir: Path | None = None) -> ActivityRules:
        ps = _params.load("activity", override_dir=override_dir)
        return cls(individual_spread=float(ps["individual_spread"]), max_days=float(ps["max_days"]),
                   eu_dominant_threshold=float(ps["eu_dominant_threshold"]))


@dataclass(frozen=True)
class EuShare:
    share: float                 # most likely EU share of annual activity, 0–1
    method: str                  # "estimated" | "user" | "eu_dominant" | "unknown"
    low: float
    high: float
    sea_days: float | None = None          # most likely days at sea used
    mrv_hours: float | None = None
    size_class: str | None = None          # IMO class key, e.g. "bulk:60000-99999"
    days: Estimate | None = None
    fuel_ratio: float | None = None        # (c) implied worldwide fuel ÷ IMO class average fuel

    @property
    def eu_dominant(self) -> bool:
        return self.method == "eu_dominant"

    @property
    def estimate(self) -> Estimate:
        return Estimate(min(self.low, self.share), self.share, max(self.high, self.share), self.method)


def days_at_sea(size_class: R.SizeClass, rules: ActivityRules) -> Estimate:
    series = size_class.series("days_at_sea")
    likely = size_class.value("days_at_sea")
    low = min(series) * (1 - rules.individual_spread)
    high = min(max(series) * (1 + rules.individual_spread), rules.max_days)
    return Estimate(min(low, likely), likely, max(high, likely), "imo4", "imo4")


def estimate_share(ship_type: str | None, mrv_time_at_sea_h: float | None, capacity: float | None = None,
                   capacity_unit: str = "dwt", mrv_fuel_t: float | None = None,
                   rules: ActivityRules | None = None) -> EuShare:
    rules = rules or ActivityRules.load()
    imo_type = R.MRV_TO_IMO.get(ship_type or "")
    cls = None
    if imo_type:
        cls = R.class_for(imo_type, dwt=capacity if capacity_unit == "dwt" else None,
                          gt=capacity if capacity_unit == "gt" else None)
        if cls is None:                       # no size known: the class holding the type's median ship
            cs = R.of_type(imo_type)
            cls = cs[len(cs) // 2] if cs else None
    if cls is None or not mrv_time_at_sea_h or mrv_time_at_sea_h <= 0:
        return EuShare(1.0, "unknown", 1.0, 1.0, None, mrv_time_at_sea_h)
    d = days_at_sea(cls, rules)

    def share(days: float) -> float:
        return min(mrv_time_at_sea_h / (days * 24), 1.0)

    s, lo, hi = share(d.likely), share(d.high), share(d.low)
    ratio = None
    if mrv_fuel_t and s > 0:
        ratio = (mrv_fuel_t / s) / cls.fuel_t() if cls.fuel_t() else None
    method = "eu_dominant" if s >= rules.eu_dominant_threshold else "estimated"
    if method == "eu_dominant":
        s = lo = hi = 1.0
    return EuShare(s, method, lo, hi, d.likely, mrv_time_at_sea_h, cls.key, d, ratio)


def user_share(value: float) -> EuShare:
    v = min(max(value, 0.01), 1.0)
    return EuShare(v, "user", v, v)


def to_worldwide(em: AnnualEmissions, eu_share: float) -> AnnualEmissions:
    """Add the estimated non-EU emissions as `outside` (EU categories unchanged)."""
    if eu_share >= 1.0:
        return em
    factor = 1 / max(eu_share, 0.01) - 1

    def grow(s: ScopeSplit) -> ScopeSplit:
        eu = s.total - s.outside
        return ScopeSplit(s.intra_eu, s.in_port, s.from_eu, s.to_eu, s.outside + eu * factor)

    return AnnualEmissions(grow(em.co2), grow(em.ch4), grow(em.n2o))
