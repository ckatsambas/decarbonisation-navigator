"""FuelEU Maritime: GHG-intensity compliance balance and penalty per year.

    energy in scope   = Σ_scope coverage × fuel(scope) × MJ/t      (100% EU, 50% to/from EU)
    target(year)      = 91.16 × (1 − reduction(year))
    balance [gCO2e]   = (target − intensity) × energy in scope
    penalty [€]       = |balance| ÷ (intensity × 41,000) × 2,400 × (1 + (n − 1)·0.1)   if balance < 0

n counts consecutive deficit years. Banking, borrowing and pooling are fleet-level tools and come
in a later phase; here each year stands alone (a conservative view for a single ship).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path

from .. import fuels as F
from .. import params as _params
from ..models import AnnualEmissions, Ship, ShipCategory


@dataclass(frozen=True)
class FuelEuRules:
    reference: float
    reductions: dict[int, float]
    first_year: int
    penalty: float
    vlsfo_mj_per_t: float
    increment: float
    rfnbo_factor: float
    rfnbo_until: int
    coverage: dict[str, float]
    gwp: dict[str, float]
    min_gt: float
    categories_from: dict[ShipCategory, int]
    derogations_until: int

    @classmethod
    def load(cls, override_dir: Path | None = None) -> FuelEuRules:
        ps = _params.load("fueleu", override_dir=override_dir)
        rw = ps["rfnbo_reward"]
        return cls(reference=float(ps["reference"]), reductions={int(y): float(v) for y, v in ps["reductions"].items()},
                   first_year=int(ps["first_year"]), penalty=float(ps["penalty_eur_per_t_vlsfo"]),
                   vlsfo_mj_per_t=float(ps["vlsfo_mj_per_t"]), increment=float(ps["consecutive_increment"]),
                   rfnbo_factor=float(rw["factor"]), rfnbo_until=int(rw["until"]),
                   coverage={k: float(v) for k, v in ps["coverage"].items()}, gwp=dict(ps["gwp100"]),
                   min_gt=float(ps["min_gross_tonnage"]),
                   categories_from={ShipCategory(c): int(y) for c, y in ps["categories_from"].items()},
                   derogations_until=int(ps["derogations_until"]))

    def target(self, year: int) -> float:
        steps = [y for y in self.reductions if y <= year]
        red = self.reductions[max(steps)] if steps else 0.0
        return self.reference * (1 - red)

    def in_scope(self, ship: Ship, year: int) -> bool:
        if year < self.first_year:
            return False
        if ship.ets_scope_override is not None:          # reported data: ≥5000 GT commercial ship
            return ship.ets_scope_override and ship.category in self.categories_from
        start = self.categories_from.get(ship.category)
        return start is not None and year >= start and ship.gross_tonnage >= self.min_gt

    def rfnbo(self, year: int) -> float:
        return self.rfnbo_factor if year <= self.rfnbo_until else 1.0


@dataclass(frozen=True)
class FuelEuYear:
    year: int
    in_scope: bool
    energy_mj: float          # energy in scope
    intensity: float          # gCO2e/MJ (with RFNBO reward)
    target: float
    balance_t: float          # t CO2e; negative = deficit
    consecutive: int          # n-th consecutive deficit year
    penalty: float            # €


def scoped_fuel_t(em: AnnualEmissions, mix: F.FuelMix, fuels: dict[str, F.Fuel], coverage: dict[str, float]) -> float:
    co2 = sum(coverage.get(f.name, 0.0) * getattr(em.co2, f.name) for f in fields(em.co2))
    return F.fuel_tonnes(co2, mix, fuels)


def fueleu_path(ship: Ship, emissions: Callable[[int], AnnualEmissions], mix: Callable[[int], F.FuelMix],
                years: range, rules: FuelEuRules | None = None, fuels: dict[str, F.Fuel] | None = None) -> list[FuelEuYear]:
    rules = rules or FuelEuRules.load()
    fuels = fuels or F.load()
    out, n = [], 0
    for y in years:
        if not rules.in_scope(ship, y):
            out.append(FuelEuYear(y, False, 0.0, 0.0, rules.target(y), 0.0, 0, 0.0))
            n = 0
            continue
        m = mix(y)
        ratio = 1.0
        if ship.ets_coverage_ratio is not None and y <= rules.derogations_until:
            ratio = min(max(ship.ets_coverage_ratio, 0.0), 1.0)
        energy = scoped_fuel_t(emissions(y), m, fuels, rules.coverage) * F.energy_per_t(m, fuels) * ratio
        ghg = F.intensity(m, fuels, rules.gwp, rules.rfnbo(y))
        tgt = rules.target(y)
        balance = (tgt - ghg) * energy / 1e6
        penalty = 0.0
        if balance < 0 and energy > 0:
            n += 1
            penalty = (-balance * 1e6) / (ghg * rules.vlsfo_mj_per_t) * rules.penalty * (1 + (n - 1) * rules.increment)
        else:
            n = 0
        out.append(FuelEuYear(y, True, energy, ghg, tgt, balance, n, penalty))
    return out
