"""All carbon regimes for one ship, year by year: EU ETS, FuelEU Maritime, IMO NZF and CII.

`Profile` describes the ship as reported (EU-recorded emissions, fuel mix, size, distance).
`Scenario` holds the assumptions about the future (EUA prices, NZF outcome, EU or worldwide view,
"doing nothing" baseline and market prices).
In the EU view the IMO measures are computed on EU-recorded activity only (a lower bound); in the
worldwide view the non-EU activity is estimated (see engine.estimate).

Baselines (decision 0007-5):
- "pay":        the ship keeps its fuel and pays every FuelEU penalty (10% more each consecutive year).
- "least_cost": each year with a FuelEU deficit the ship takes the cheapest route for the whole
                year's carbon bill: pay the penalty, buy surplus from a pool, or blend just enough
                biofuel into the fuel used in FuelEU scope to meet the target. Blending also lowers
                the EU ETS cost (sustainable biofuel is zero-rated) and the IMO NZF intensity.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import fuels as F
from . import params as _params
from .estimate import ActivityRules, EuShare, to_worldwide
from .models import AnnualEmissions, Ship, YearSeries
from .regulation.cii import CiiRules, CiiYear, cii_path
from .regulation.eu_ets import EtsRules, EtsYear, cost_path
from .regulation.fueleu import FuelEuRules, FuelEuYear, fueleu_path
from .regulation.imo_nzf import NzfRules, NzfYear, nzf_path, tier_cost
from .uncertainty import Estimate

BASELINES = ("least_cost", "pay")


@dataclass(frozen=True)
class Markets:
    pool_price: Estimate          # € per t CO2e
    bio_premium: Estimate         # $ per t biofuel above fossil
    bio_fuel: str

    @classmethod
    def load(cls, override_dir: Path | None = None) -> Markets:
        ps = _params.load("markets", override_dir=override_dir)
        pp, bp = ps["pool_price_eur"], ps["bio_premium_usd"]
        return cls(Estimate(pp["low"], pp["likely"], pp["high"], "market", "markets"),
                   Estimate(bp["low"], bp["likely"], bp["high"], "market", "markets"), ps["bio_fuel"])

YEARS = range(2024, 2051)


@dataclass(frozen=True)
class Rules:
    ets: EtsRules
    fueleu: FuelEuRules
    nzf: NzfRules
    cii: CiiRules
    activity: ActivityRules
    fuels: dict[str, F.Fuel]
    markets: Markets

    @classmethod
    def load(cls, override_dir: Path | None = None) -> Rules:
        return cls(EtsRules.load(override_dir), FuelEuRules.load(override_dir), NzfRules.load(override_dir),
                   CiiRules.load(override_dir), ActivityRules.load(override_dir), F.load(override_dir),
                   Markets.load(override_dir))


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
    size: Estimate | None = None             # estimated capacity when not reported (decision 0007-1)


@dataclass(frozen=True)
class Scenario:
    eua: YearSeries = field(default_factory=lambda: YearSeries({2025: 75, 2030: 110, 2050: 150}))
    nzf: str = "as_drafted"
    view: str = "eu"                         # "eu" | "ww"
    baseline: str = "least_cost"             # "least_cost" | "pay"
    pool_price: float | None = None          # € / t CO2e; None = most likely market value
    bio_premium_usd: float | None = None     # $ / t biofuel above fossil; None = most likely


@dataclass(frozen=True)
class YearState:
    """The ship in one year after measures (decision 0009): what each regime sees.

    `emissions` are physical tank-to-wake emissions in EU scope (FuelEU, IMO, CII read the fuel and
    energy from them); `ets_emissions` are what is surrendered under the EU ETS (sustainable biofuel
    and RFNBO zero-rated, credited capture removed); `mix` is the mass mix of fuels burnt.
    """
    emissions: AnnualEmissions
    ets_emissions: AnnualEmissions
    mix: F.FuelMix


ShipPath = Callable[[int], YearState]


@dataclass(frozen=True)
class YearResult:
    year: int
    ets: EtsYear
    fueleu: FuelEuYear
    nzf: NzfYear
    cii: CiiYear | None
    route: str = "none"                      # FuelEU route: none | pay | pool | bio
    fueleu_cost: float = 0.0                 # € spent on FuelEU compliance by that route
    bio_share: float = 0.0                   # energy share of biofuel blended in FuelEU scope

    @property
    def total_eur(self) -> float:
        return self.ets.cost + self.fueleu_cost + self.nzf.cost_eur


def worldwide_factor(profile: Profile, scenario: Scenario) -> float:
    """Multiplier from EU-recorded to the activity used for IMO measures."""
    if scenario.view != "ww" or profile.eu_share is None:
        return 1.0
    return 1 / max(profile.eu_share.share, 0.01)


def evaluate(profile: Profile, scenario: Scenario, years: range = YEARS, rules: Rules | None = None,
             path: ShipPath | None = None) -> list[YearResult]:
    """All regimes year by year; `path` gives the ship after measures (None = as reported every year)."""
    rules = rules or Rules.load()
    base = YearState(profile.emissions, profile.emissions, profile.fuel_mix)
    state = path or (lambda _y: base)
    ww = scenario.view == "ww" and profile.eu_share is not None

    def imo(y: int) -> AnnualEmissions:
        em = state(y).emissions
        return to_worldwide(em, profile.eu_share.share) if ww else em

    def mix(y: int) -> F.FuelMix:
        return state(y).mix

    ets = cost_path(profile.ship, lambda y: state(y).ets_emissions, scenario.eua, years, rules.ets)
    fe = fueleu_path(profile.ship, lambda y: state(y).emissions, mix, years, rules.fueleu, rules.fuels)
    nz = nzf_path(profile.ship, imo, mix, years, scenario.nzf, rules.nzf, rules.fuels, profile.domestic_only)
    cii: list[CiiYear | None] = [None] * len(years)
    if profile.cii_type and profile.capacity > 0 and profile.distance_nm > 0:
        f = worldwide_factor(profile, scenario)
        cii = cii_path(profile.cii_type, profile.capacity, lambda y: imo(y).co2.total, profile.distance_nm * f,
                       years, rules.cii)
    if scenario.baseline == "pay":
        return [YearResult(y, a, b, c, d, "pay" if b.penalty > 0 else "none", b.penalty)
                for y, a, b, c, d in zip(years, ets, fe, nz, cii, strict=True)]
    return _least_cost(years, ets, fe, nz, cii, scenario, rules)


def _least_cost(years, ets, fe, nz, cii, scenario: Scenario, rules: Rules) -> list[YearResult]:
    fr, mk = rules.fueleu, rules.markets
    pool_price = scenario.pool_price if scenario.pool_price is not None else mk.pool_price.likely
    premium_eur = (scenario.bio_premium_usd if scenario.bio_premium_usd is not None
                   else mk.bio_premium.likely) * rules.nzf.eur_per_usd
    bio = rules.fuels[mk.bio_fuel]
    i_bio_fe, i_bio_nzf = bio.wtw(fr.gwp), bio.wtw(rules.nzf.gwp)
    out, n = [], 0
    for y, e, f, z, c in zip(years, ets, fe, nz, cii, strict=True):
        if not f.in_scope or f.balance_t >= 0 or f.energy_mj <= 0:
            out.append(YearResult(y, e, f, z, c))
            n = 0
            continue
        deficit = -f.balance_t
        penalty = deficit * 1e6 / (f.intensity * fr.vlsfo_mj_per_t) * fr.penalty * (1 + n * fr.increment)
        options = {"pay": (e.cost + penalty + z.cost_eur, penalty, e, z, 0.0),
                   "pool": (e.cost + deficit * pool_price + z.cost_eur, deficit * pool_price, e, z, 0.0)}
        share = (f.intensity - f.target) / (f.intensity - i_bio_fe) if f.intensity > i_bio_fe else 1.0
        share = min(max(share, 0.0), 1.0)
        bio_t = share * f.energy_mj / (bio.lcv * 1e6)
        e_bio = replace(e, allowances=e.allowances * (1 - share), cost=e.cost * (1 - share),
                        covered=e.covered * (1 - share))
        z_bio = z
        if z.applies and z.energy_mj > 0:
            s_all = min(share * f.energy_mj / z.energy_mj, 1.0)
            gfi = (1 - s_all) * z.gfi + s_all * i_bio_nzf
            t1, t2, sur, usd = tier_cost(gfi, z.energy_mj, z.base, z.direct, rules.nzf)
            z_bio = replace(z, gfi=gfi, tier1_t=t1, tier2_t=t2, surplus_t=sur, cost_usd=usd,
                            cost_eur=usd * rules.nzf.eur_per_usd)
        options["bio"] = (e_bio.cost + bio_t * premium_eur + z_bio.cost_eur, bio_t * premium_eur, e_bio, z_bio, share)
        route = min(options, key=lambda k: options[k][0])
        _, cost, e2, z2, s2 = options[route]
        n = n + 1 if route == "pay" else 0
        out.append(YearResult(y, e2, f, z2, c, route, cost, s2))
    return out


def with_view(scenario: Scenario, view: str) -> Scenario:
    return replace(scenario, view=view)
