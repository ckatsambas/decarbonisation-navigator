"""Worldwide activity from EU-only data (see docs/decisions/0005).

EU MRV records only voyages that touch the EU. The IMO Net-Zero Framework applies to all of a
ship's international voyages, so its worldwide emissions are needed. Three sources, in order:

  (a) user:      the company enters the EU share of its activity (or its worldwide fuel).
  (b) estimated: EU share = MRV time at sea ÷ typical days at sea for the ship type.
  (c) reference: ship-type averages from the IMO GHG studies, as a plausibility check.

Ships whose estimated EU share is at or above a threshold are treated as trading mainly in
the EU (ferries, short-sea): their recorded data are taken as complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import params as _params
from .models import AnnualEmissions, ScopeSplit


@dataclass(frozen=True)
class ActivityRules:
    sea_days: dict[str, float]
    uncertainty: float
    eu_dominant_threshold: float

    @classmethod
    def load(cls, override_dir: Path | None = None) -> ActivityRules:
        ps = _params.load("activity", override_dir=override_dir)
        return cls(sea_days={k: float(v) for k, v in ps["sea_days"].items()},
                   uncertainty=float(ps["uncertainty"]), eu_dominant_threshold=float(ps["eu_dominant_threshold"]))


@dataclass(frozen=True)
class EuShare:
    share: float                 # EU share of annual activity, 0–1
    method: str                  # "estimated" | "user" | "eu_dominant" | "unknown"
    low: float                   # range from the uncertainty of typical days at sea
    high: float
    sea_days: float | None = None
    mrv_hours: float | None = None

    @property
    def eu_dominant(self) -> bool:
        return self.method == "eu_dominant"


def estimate_share(ship_type: str | None, mrv_time_at_sea_h: float | None,
                   rules: ActivityRules | None = None) -> EuShare:
    rules = rules or ActivityRules.load()
    days = rules.sea_days.get(ship_type or "", rules.sea_days["default"])
    if not mrv_time_at_sea_h or mrv_time_at_sea_h <= 0:
        return EuShare(1.0, "unknown", 1.0, 1.0, days, mrv_time_at_sea_h)
    hours = days * 24

    def share(d):
        return min(mrv_time_at_sea_h / d, 1.0)

    s = share(hours)
    lo, hi = share(hours * (1 + rules.uncertainty)), share(hours * (1 - rules.uncertainty))
    method = "eu_dominant" if s >= rules.eu_dominant_threshold else "estimated"
    if method == "eu_dominant":
        s = lo = hi = 1.0
    return EuShare(s, method, lo, hi, days, mrv_time_at_sea_h)


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
