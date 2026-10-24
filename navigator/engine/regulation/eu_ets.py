"""EU ETS for maritime transport: allowances and cost per emission year.

For one ship and one emission year:

    covered CO2e = Σ_gas  GWP(gas) × Σ_scope coverage(scope) × tonnes(gas, scope)
                   (a gas counts only from the year it enters the ETS)
    allowances   = covered CO2e × phase-in(year) × (1 − ice-class reduction, if eligible)
    cost         = allowances × EUA price(year)

The cost belongs to the emission year; the cash leaves in the following year
(`surrender_year`), which matters for discounting in the investment appraisal.

Not modelled here (documented limitations): the outermost-region and small-island
exemptions, which apply to specific routes; enter those emissions as `outside` if relevant.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from pathlib import Path

from .. import params as _params
from ..models import AnnualEmissions, Gas, ScopeSplit, Ship, ShipCategory, YearSeries

PARAM_FILE = "eu_ets_maritime"


@dataclass(frozen=True)
class EtsRules:
    first_year: int
    phase_in: dict[int, float]
    coverage: dict[str, float]
    gases_from: dict[Gas, int]
    gwp: dict[Gas, float]
    min_gross_tonnage: float
    categories_from: dict[ShipCategory, int]
    ice_share: float
    ice_until: int
    ice_classes: frozenset[str]

    @classmethod
    def from_params(cls, ps: _params.ParamSet) -> EtsRules:
        ice = ps["ice_class_reduction"]
        return cls(
            first_year=int(ps["first_year"]),
            phase_in={int(y): float(v) for y, v in ps["phase_in"].items()},
            coverage={k: float(v) for k, v in ps["coverage"].items()},
            gases_from={Gas(g): int(y) for g, y in ps["gases_from"].items()},
            gwp={Gas(g): float(v) for g, v in ps["gwp100"].items()},
            min_gross_tonnage=float(ps["min_gross_tonnage"]),
            categories_from={ShipCategory(c): int(y) for c, y in ps["categories_from"].items()},
            ice_share=float(ice["share"]),
            ice_until=int(ice["until"]),
            ice_classes=frozenset(c.lower() for c in ice["classes"]),
        )

    @classmethod
    def load(cls, override_dir: Path | None = None) -> EtsRules:
        return cls.from_params(_params.load(PARAM_FILE, override_dir=override_dir))

    def phase_in_share(self, year: int) -> float:
        """Latest phase-in step at or before `year`; 0 before the system starts."""
        if year < self.first_year:
            return 0.0
        steps = [y for y in self.phase_in if y <= year]
        return self.phase_in[max(steps)] if steps else 0.0

    def ship_in_scope(self, ship: Ship, year: int) -> bool:
        start = self.categories_from.get(ship.category)
        return start is not None and year >= start and ship.gross_tonnage >= self.min_gross_tonnage

    def ice_factor(self, ship: Ship, year: int) -> float:
        if ship.ice_class and ship.ice_class.lower() in self.ice_classes and year <= self.ice_until:
            return 1.0 - self.ice_share
        return 1.0


@dataclass(frozen=True)
class EtsYear:
    year: int
    surrender_year: int
    in_scope: bool
    covered_by_gas: dict[Gas, float]   # t CO2e after voyage coverage, before phase-in
    covered: float                     # t CO2e
    phase_in: float
    ice_factor: float
    allowances: float                  # EUAs to surrender
    price: float                       # €/EUA
    cost: float                        # €


def covered_co2e(em: AnnualEmissions, year: int, rules: EtsRules) -> dict[Gas, float]:
    out: dict[Gas, float] = {}
    for g in Gas:
        if year < rules.gases_from.get(g, 10**6):
            out[g] = 0.0
            continue
        split: ScopeSplit = em.gas(g)
        tonnes = sum(rules.coverage.get(f.name, 0.0) * getattr(split, f.name) for f in fields(split))
        out[g] = tonnes * rules.gwp[g]
    return out


def ets_year(ship: Ship, em: AnnualEmissions, year: int, price: float, rules: EtsRules) -> EtsYear:
    in_scope = rules.ship_in_scope(ship, year)
    by_gas = covered_co2e(em, year, rules) if in_scope else {g: 0.0 for g in Gas}
    covered = sum(by_gas.values())
    share = rules.phase_in_share(year) if in_scope else 0.0
    ice = rules.ice_factor(ship, year) if in_scope else 1.0
    allowances = covered * share * ice
    return EtsYear(year=year, surrender_year=year + 1, in_scope=in_scope, covered_by_gas=by_gas,
                   covered=covered, phase_in=share, ice_factor=ice, allowances=allowances,
                   price=price, cost=allowances * price)


EmissionsInput = AnnualEmissions | Mapping[int, AnnualEmissions] | Callable[[int], AnnualEmissions]


def _emissions_for(src: EmissionsInput, year: int) -> AnnualEmissions:
    if isinstance(src, AnnualEmissions):
        return src
    if callable(src):
        return src(year)
    return src[year]


def cost_path(ship: Ship, emissions: EmissionsInput, prices: YearSeries | Mapping[int, float] | float,
              years: range, rules: EtsRules | None = None) -> list[EtsYear]:
    """EU ETS position year by year.

    `emissions` may be one profile used every year, a mapping year → profile, or a function of the
    year (for example a measure that only starts in 2028). `prices` may be a constant, a mapping or
    a YearSeries (interpolated).
    """
    rules = rules or EtsRules.load()
    if isinstance(prices, (int, float)):
        prices = YearSeries.constant(float(prices))
    elif not isinstance(prices, YearSeries):
        prices = YearSeries(prices)
    return [ets_year(ship, _emissions_for(emissions, y), y, prices.at(y), rules) for y in years]


def total_cost(path: list[EtsYear]) -> float:
    return sum(r.cost for r in path)
