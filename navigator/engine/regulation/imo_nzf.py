"""IMO Net-Zero Framework (MEPC 83 draft): GHG fuel intensity (GFI) and remedial units.

    base, direct (year) = 93.3 × (1 − reduction)               gCO2e/MJ
    GFI > base          → Tier 2 deficit (GFI − base)·E  at $380 + Tier 1 deficit (base − direct)·E at $100
    direct < GFI ≤ base → Tier 1 deficit (GFI − direct)·E at $100
    GFI ≤ direct        → surplus units (direct − GFI)·E, valued at an assumed price (0 by default)

E is the energy used on international voyages in the year (MJ); deficits are in t CO2e.
Scenarios (adopted as drafted, delayed one year, not adopted) are defined in the parameter file.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import fuels as F
from .. import params as _params
from ..models import AnnualEmissions, Ship, YearSeries

SCENARIOS = ("as_drafted", "delayed", "not_adopted")


@dataclass(frozen=True)
class NzfRules:
    reference: float
    base: YearSeries
    direct: YearSeries
    tier1_usd: float
    tier2_usd: float
    surplus_usd: float
    gwp: dict[str, float]
    min_gt: float
    eur_per_usd: float
    first_year: dict[str, int | None]

    @classmethod
    def load(cls, override_dir: Path | None = None) -> NzfRules:
        ps = _params.load("imo_nzf", override_dir=override_dir)
        base = {int(y): float(v) for y, v in ps["base_target"].items()}
        base.update({int(y): float(v) for y, v in ps["base_target_after_2040"].items()})
        direct = {int(y): float(v) for y, v in ps["direct_target"].items()}
        direct.update({int(y): float(v) for y, v in ps["direct_target_after_2035"].items()})
        ru = ps["ru_price_usd"]
        return cls(reference=float(ps["reference"]), base=YearSeries(base), direct=YearSeries(direct),
                   tier1_usd=float(ru["tier1"]), tier2_usd=float(ru["tier2"]),
                   surplus_usd=float(ps["surplus_unit_value_usd"]), gwp=dict(ps["gwp100"]),
                   min_gt=float(ps["min_gross_tonnage"]), eur_per_usd=float(ps["eur_per_usd"]),
                   first_year={k: v["first_year"] for k, v in ps["scenarios"].items()})

    def targets(self, year: int, scenario: str) -> tuple[float, float] | None:
        start = self.first_year.get(scenario)
        if start is None or year < start:
            return None
        return (self.reference * (1 - self.base.at(year)), self.reference * (1 - self.direct.at(year)))

    def in_scope(self, ship: Ship) -> bool:
        if ship.ets_scope_override is not None:
            return ship.ets_scope_override
        return ship.gross_tonnage >= self.min_gt


@dataclass(frozen=True)
class NzfYear:
    year: int
    applies: bool
    energy_mj: float
    gfi: float
    base: float
    direct: float
    tier1_t: float
    tier2_t: float
    surplus_t: float
    cost_usd: float          # positive = cost, negative = income from surplus units
    cost_eur: float


def tier_cost(gfi: float, energy_mj: float, base: float, direct: float, rules: NzfRules) -> tuple[float, float, float, float]:
    """(tier 1 t, tier 2 t, surplus t, cost USD) for one year."""
    tier1 = tier2 = surplus = 0.0
    if gfi > base:
        tier2 = (gfi - base) * energy_mj / 1e6
        tier1 = (base - direct) * energy_mj / 1e6
    elif gfi > direct:
        tier1 = (gfi - direct) * energy_mj / 1e6
    else:
        surplus = (direct - gfi) * energy_mj / 1e6
    return tier1, tier2, surplus, tier1 * rules.tier1_usd + tier2 * rules.tier2_usd - surplus * rules.surplus_usd


def nzf_path(ship: Ship, emissions: Callable[[int], AnnualEmissions], mix: Callable[[int], F.FuelMix],
             years: range, scenario: str = "as_drafted", rules: NzfRules | None = None,
             fuels: dict[str, F.Fuel] | None = None, domestic_only: bool = False) -> list[NzfYear]:
    rules = rules or NzfRules.load()
    fuels = fuels or F.load()
    out = []
    for y in years:
        t = rules.targets(y, scenario)
        if t is None or domestic_only or not rules.in_scope(ship):
            out.append(NzfYear(y, False, 0, 0, t[0] if t else 0, t[1] if t else 0, 0, 0, 0, 0, 0))
            continue
        base, direct = t
        m = mix(y)
        energy = F.fuel_tonnes(emissions(y).co2.total, m, fuels) * F.energy_per_t(m, fuels)
        gfi = F.intensity(m, fuels, rules.gwp)
        tier1, tier2, surplus, usd = tier_cost(gfi, energy, base, direct, rules)
        out.append(NzfYear(y, True, energy, gfi, base, direct, tier1, tier2, surplus, usd, usd * rules.eur_per_usd))
    return out
