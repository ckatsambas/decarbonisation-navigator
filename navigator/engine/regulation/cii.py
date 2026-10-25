"""IMO Carbon Intensity Indicator (CII): attained AER/cgDIST, required value and A–E rating.

    attained = CO2 [g] ÷ (capacity × distance [n mi])
    required = a · capacity^(−c) · (1 − Z(year))
    rating   = A … E by attained/required against exp(d1..d4) for the ship type

With worldwide estimates, CO2 and distance are scaled by the same EU share, so the attained value
from EU data equals the worldwide estimate: CII does not depend on the EU/WW choice.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import params as _params

RATINGS = ("A", "B", "C", "D", "E")

MRV_TO_CII = {
    "Bulk carrier": "bulk", "Oil tanker": "tanker", "Chemical tanker": "tanker", "Container ship": "container",
    "Gas carrier": "gas", "LNG carrier": "lng", "General cargo ship": "general_cargo",
    "Refrigerated cargo carrier": "reefer", "Combination carrier": "combination", "Vehicle carrier": "vehicle",
    "Ro-ro ship": "roro", "Container/ro-ro cargo ship": "roro", "Ro-pax ship": "ropax",
    "Passenger ship (Cruise Passenger ship)": "cruise", "Passenger ship": "cruise",
}


def cii_type_for(mrv_ship_type: str | None) -> str | None:
    return MRV_TO_CII.get(mrv_ship_type or "")


@dataclass(frozen=True)
class CiiRules:
    lines: dict
    boundaries: dict[str, list[float]]
    reduction: dict[int, float]
    step_after_2030: float

    @classmethod
    def load(cls, override_dir: Path | None = None) -> CiiRules:
        ps = _params.load("cii", override_dir=override_dir)
        return cls(lines=ps["reference_lines"], boundaries=ps["boundaries"],
                   reduction={int(y): float(v) for y, v in ps["reduction"].items()},
                   step_after_2030=float(ps["reduction_after_2030"]))

    def capacity_unit(self, cii_type: str) -> str:
        return self.lines[cii_type]["capacity"]

    def reference(self, cii_type: str, capacity: float) -> float:
        spec = self.lines[cii_type]
        cap = capacity
        if "cap_max" in spec:
            cap = min(cap, spec["cap_max"])
        if "cap_min" in spec:
            cap = max(cap, spec["cap_min"])
        a, c = next((a, c) for start, a, c in reversed(spec["lines"]) if capacity >= start)
        return a * cap ** (-c)

    def z(self, year: int) -> float:
        """Reduction factor vs the 2019 line; before the first year the 2019 line itself applies."""
        first, last = min(self.reduction), max(self.reduction)
        if year < first:
            return 0.0
        if year > last:
            return min(self.reduction[last] + self.step_after_2030 * (year - last), 1.0)
        return self.reduction[year]

    def required(self, cii_type: str, capacity: float, year: int) -> float:
        return self.reference(cii_type, capacity) * (1 - self.z(year))

    def boundary_key(self, cii_type: str, capacity: float) -> str:
        if cii_type == "gas" and capacity >= 65000:
            return "gas_large"
        if cii_type == "lng" and capacity >= 100000:
            return "lng_large"
        return cii_type

    def rating(self, cii_type: str, capacity: float, attained: float, required: float) -> str:
        ratio = attained / required
        d = self.boundaries[self.boundary_key(cii_type, capacity)]
        return next((r for r, lim in zip(RATINGS, d, strict=False) if ratio <= lim), "E")


def attained(co2_t: float, capacity: float, distance_nm: float) -> float:
    return co2_t * 1e6 / (capacity * distance_nm) if capacity > 0 and distance_nm > 0 else float("nan")


@dataclass(frozen=True)
class CiiYear:
    year: int
    attained: float
    required: float
    ratio: float
    rating: str


def cii_path(cii_type: str, capacity: float, co2_t: float | Callable[[int], float], distance_nm: float, years: range,
             rules: CiiRules | None = None) -> list[CiiYear]:
    """Rating each year; `co2_t` is the reported year's CO2 (kept every year) or a function of the year."""
    rules = rules or CiiRules.load()
    out = []
    for y in years:
        att = attained(co2_t(y) if callable(co2_t) else co2_t, capacity, distance_nm)
        req = rules.required(cii_type, capacity, y)
        out.append(CiiYear(y, att, req, att / req, rules.rating(cii_type, capacity, att, req)))
    return out
