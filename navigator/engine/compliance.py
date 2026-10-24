"""All carbon regimes for one ship, year by year: EU ETS, FuelEU Maritime, IMO NZF and CII.

`Profile` describes the ship as reported (EU-recorded emissions, fuel mix, size, distance).
`Scenario` holds the assumptions about the future (EUA prices, NZF outcome, EU or worldwide view).
In the EU view the IMO measures are computed on EU-recorded activity only (a lower bound); in the
worldwide view the non-EU activity is estimated (see engine.estimate).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from . import fuels as F
from .estimate import ActivityRules, EuShare, to_worldwide
from .models import AnnualEmissions, Ship, YearSeries
from .regulation.cii import CiiRules, CiiYear, cii_path
from .regulation.eu_ets import EtsRules, EtsYear, cost_path
from .regulation.fueleu import FuelEuRules, FuelEuYear, fueleu_path
from .regulation.imo_nzf import NzfRules, NzfYear, nzf_path

YEARS = range(2024, 2051)


@dataclass(frozen=True)
class Rules:
    ets: EtsRules
    fueleu: FuelEuRules
    nzf: NzfRules
    cii: CiiRules
    activity: ActivityRules
    fuels: dict[str, F.Fuel]

    @classmethod
    def load(cls, override_dir: Path | None = None) -> Rules:
        return cls(EtsRules.load(override_dir), FuelEuRules.load(override_dir), NzfRules.load(override_dir),
                   CiiRules.load(override_dir), ActivityRules.load(override_dir), F.load(override_dir))


@dataclass(frozen=True)
class Profile:
    ship: Ship
    emissions: AnnualEmissions               # EU-recorded (outside = 0 for MRV ships)
    fuel_mix: F.FuelMix
    cii_type: str | None = None
    capacity: float = 0.0                    # DWT or GT, depending on the CII ship type
    distance_nm: float = 0.0                 # distance matching `emissions`
    domestic_only: bool = False
    eu_share: EuShare | None = None          # for the worldwide view


@dataclass(frozen=True)
class Scenario:
    eua: YearSeries = field(default_factory=lambda: YearSeries({2025: 75, 2030: 110, 2050: 150}))
    nzf: str = "as_drafted"
    view: str = "eu"                         # "eu" | "ww"


@dataclass(frozen=True)
class YearResult:
    year: int
    ets: EtsYear
    fueleu: FuelEuYear
    nzf: NzfYear
    cii: CiiYear | None

    @property
    def total_eur(self) -> float:
        return self.ets.cost + self.fueleu.penalty + self.nzf.cost_eur


def worldwide_factor(profile: Profile, scenario: Scenario) -> float:
    """Multiplier from EU-recorded to the activity used for IMO measures."""
    if scenario.view != "ww" or profile.eu_share is None:
        return 1.0
    return 1 / max(profile.eu_share.share, 0.01)


def evaluate(profile: Profile, scenario: Scenario, years: range = YEARS, rules: Rules | None = None) -> list[YearResult]:
    rules = rules or Rules.load()
    em_eu = profile.emissions
    em_imo = em_eu
    if scenario.view == "ww" and profile.eu_share is not None:
        em_imo = to_worldwide(em_eu, profile.eu_share.share)

    def mix(_y):
        return profile.fuel_mix

    ets = cost_path(profile.ship, em_eu, scenario.eua, years, rules.ets)
    fe = fueleu_path(profile.ship, lambda _y: em_eu, mix, years, rules.fueleu, rules.fuels)
    nz = nzf_path(profile.ship, lambda _y: em_imo, mix, years, scenario.nzf, rules.nzf, rules.fuels,
                  profile.domestic_only)
    cii: list[CiiYear | None] = [None] * len(years)
    if profile.cii_type and profile.capacity > 0 and profile.distance_nm > 0:
        f = worldwide_factor(profile, scenario)
        cii = cii_path(profile.cii_type, profile.capacity, em_imo.co2.total, profile.distance_nm * f,
                       years, rules.cii)
    return [YearResult(y, a, b, c, d) for y, a, b, c, d in zip(years, ets, fe, nz, cii, strict=True)]


def with_view(scenario: Scenario, view: str) -> Scenario:
    return replace(scenario, view=view)
