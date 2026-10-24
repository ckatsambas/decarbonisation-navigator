"""Core data types shared by every part of the engine."""
from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from enum import StrEnum


class Gas(StrEnum):
    CO2 = "co2"
    CH4 = "ch4"
    N2O = "n2o"


class ShipCategory(StrEnum):
    """Grouping used to decide which regimes apply (EU ETS scope differs by category)."""
    CARGO = "cargo"
    PASSENGER = "passenger"
    OFFSHORE = "offshore"
    OTHER = "other"


@dataclass(frozen=True)
class ScopeSplit:
    """Tonnes of one gas in one year, split by the EU MRV voyage categories.

    The split follows the public EU MRV emission reports, so real ships can be loaded directly.
    `outside` holds emissions on voyages with no EU/EEA port; it is outside EU scope but counts
    for IMO measures (CII, Net-Zero Framework).
    """
    intra_eu: float = 0.0   # voyages between two EU/EEA ports of call
    in_port: float = 0.0    # within EU/EEA ports: at berth plus in-port movements
    from_eu: float = 0.0    # voyages departing an EU/EEA port to a non-EU port
    to_eu: float = 0.0      # voyages arriving at an EU/EEA port from a non-EU port
    outside: float = 0.0    # voyages with no EU/EEA port

    @property
    def total(self) -> float:
        return sum(getattr(self, f.name) for f in fields(self))

    def scaled(self, factor: float) -> ScopeSplit:
        return ScopeSplit(**{f.name: getattr(self, f.name) * factor for f in fields(self)})


@dataclass(frozen=True)
class AnnualEmissions:
    """One ship's emissions in one year, per gas (tonnes of the gas itself, not CO2e)."""
    co2: ScopeSplit
    ch4: ScopeSplit = field(default_factory=ScopeSplit)
    n2o: ScopeSplit = field(default_factory=ScopeSplit)

    def gas(self, g: Gas) -> ScopeSplit:
        return getattr(self, g.value)

    def scaled(self, factor: float) -> AnnualEmissions:
        """Uniform change, e.g. a measure that saves 8% of fuel scales every gas by 0.92."""
        return AnnualEmissions(self.co2.scaled(factor), self.ch4.scaled(factor), self.n2o.scaled(factor))


@dataclass(frozen=True)
class Ship:
    imo: str
    name: str
    ship_type: str                      # label as reported in EU MRV, e.g. "Bulk carrier"
    category: ShipCategory = ShipCategory.CARGO
    gross_tonnage: float = 0.0
    deadweight: float = 0.0
    build_year: int | None = None
    flag: str = ""
    ice_class: str | None = None        # e.g. "IA", "IA Super"
    # Known EU ETS status from reported data (EMSA publishes ETS emissions from 2024). None = use the rules.
    ets_scope_override: bool | None = None
    # EMSA-reported ETS emissions ÷ rule-based covered emissions in the latest reported year (0–1).
    # Captures route-specific derogations (islands, outermost regions); applied until they expire.
    ets_coverage_ratio: float | None = None


class YearSeries:
    """A value that changes by year (prices, targets).

    Linear interpolation between the given years and flat beyond the first and last year,
    so a path can be specified with only a few anchor points.
    """

    def __init__(self, points: Mapping[int, float]):
        if not points:
            raise ValueError("YearSeries needs at least one point")
        self._years = sorted(int(y) for y in points)
        self._vals = [float(points[y]) for y in self._years]

    @classmethod
    def constant(cls, value: float) -> YearSeries:
        return cls({2000: value})

    def at(self, year: int) -> float:
        ys, vs = self._years, self._vals
        if year <= ys[0]:
            return vs[0]
        if year >= ys[-1]:
            return vs[-1]
        i = bisect_right(ys, year)
        y0, y1, v0, v1 = ys[i - 1], ys[i], vs[i - 1], vs[i]
        return v0 + (v1 - v0) * (year - y0) / (y1 - y0)

    def __getitem__(self, year: int) -> float:
        return self.at(year)

    def points(self) -> dict[int, float]:
        return dict(zip(self._years, self._vals, strict=True))
