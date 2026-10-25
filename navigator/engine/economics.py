"""Investment value of measures (decision 0009-6): NPV with a discount-rate range.

For a ship and a set of measures installed in year `start`:

    cash flow (y) = Δ fuel cost + Δ shore electricity + Δ carbon cost (EU ETS + FuelEU + IMO NZF)
                    − OPEX − CAPEX (at installation and at each renewal) − days off-hire × daily earnings
                    − extra days at sea × daily earnings × time-cost share (slower sailing)
    NPV = Σ cash flow (y) / (1 + r)^(y − base year),  y = start … end of the ship's life (≤ 2050)

A measure whose life runs past the horizon keeps a straight-line residual value. Outputs: NPV,
payback year, and cost per tonne CO2e avoided (− NPV ÷ tonnes avoided well-to-wake, the
"MAC with NPV" of the Fourth IMO GHG Study, Annex Q.5). Prices come in three paths per fuel
(low / central / high, decision 0009-5); carbon prices from the regulation scenario.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import fuels as F
from . import params as _params
from . import power as PW
from .compliance import Rules, Scenario, YearResult, evaluate
from .measures import Measure, ShipModel, ship_path
from .models import YearSeries

PRICE_PATHS = ("low", "central", "high")


@dataclass(frozen=True)
class Prices:
    fuel: dict[str, dict[str, YearSeries]]     # fuel id → path → USD per tonne by year
    electricity_eur_kwh: dict[str, float]      # path → € per kWh at berth
    earnings_usd_day: dict[str, dict[str, float]]   # IMO type → low/likely/high daily earnings (TCE)
    discount: dict[str, float]                 # low / likely / high
    ship_life: int
    time_cost_share: dict[str, float]          # share of extra sea time that costs earnings

    @classmethod
    def load(cls, override_dir: Path | None = None) -> Prices:
        ps = _params.load("prices", base_dir=_params.CONFIG_DIR / "market", override_dir=override_dir)
        fuel = {k: {p: YearSeries({int(y): float(v[p]) for y, v in years.items()}) for p in PRICE_PATHS}
                for k, years in ps["fuel_usd_t"].items()}
        return cls(fuel, dict(ps["electricity_eur_kwh"]), dict(ps["earnings_usd_day"]), dict(ps["discount_rate"]),
                   int(ps["ship_life_years"]), dict(ps["time_cost_share"]))

    def fuel_usd_t(self, fuel: str, year: int, path: str = "central") -> float:
        series = self.fuel.get(fuel)
        if series is None:
            raise KeyError(f"No price path for fuel {fuel!r}")
        return series[path].at(year)

    def earnings(self, imo_type: str, q: str = "likely") -> float:
        row = self.earnings_usd_day.get(imo_type) or self.earnings_usd_day["default"]
        return float(row[q])


@lru_cache(maxsize=2)
def default_prices() -> Prices:
    return Prices.load()


@dataclass(frozen=True)
class YearFlow:
    year: int
    fuel: float          # € saved on fuel (+) or spent (−)
    electricity: float   # € spent on shore power (−)
    carbon: float        # € saved on ETS + FuelEU + NZF
    opex: float          # € (−)
    capex: float         # € (−), installation and renewals; residual value (+) in the last year
    offhire: float       # € (−)
    time: float          # € (−) earnings lost to slower sailing
    co2e_avoided: float  # t CO2e well-to-wake

    @property
    def net(self) -> float:
        return self.fuel + self.electricity + self.carbon + self.opex + self.capex + self.offhire + self.time


@dataclass(frozen=True)
class Appraisal:
    flows: list[YearFlow]
    npv: float
    discount_rate: float
    payback_year: int | None
    co2e_avoided: float
    cost_per_t: float | None       # € per t CO2e avoided (None if nothing avoided)
    capex_eur: float
    with_measures: list[YearResult]
    baseline: list[YearResult]

    @property
    def carbon_saved(self) -> float:
        return sum(f.carbon for f in self.flows)


def _wtw_t(fuel_t: dict[str, float], fuels: dict[str, F.Fuel], gwp: dict[str, float]) -> float:
    return sum(t * fuels[k].lcv * 1e6 * fuels[k].wtw(gwp) / 1e6 for k, t in fuel_t.items())


def appraise(model: ShipModel, measures: Iterable[Measure], scenario: Scenario, start: int = 2026,
             q: float = 0.5, price_path: str = "central", discount: float | None = None,
             end: int | None = None, rules: Rules | None = None, prices: Prices | None = None,
             build_year: int | None = None, base_year: int = 2026) -> Appraisal:
    """NPV of installing `measures` on the ship in `start`, against doing nothing (scenario's baseline)."""
    rules = rules or Rules.load()
    prices = prices or default_prices()
    fuels = rules.fuels
    ms = list(measures)
    r = prices.discount["likely"] if discount is None else discount
    usd = rules.nzf.eur_per_usd
    if end is None:                                   # end of the ship's life (25 years), at most 2050
        built = build_year or model.profile.ship.build_year
        end = built + prices.ship_life if built else start + 19
    end = min(max(end, start), 2050)
    years = range(min(2024, start), 2051)

    # regimes with and without the measures (same scenario, same baseline rule)
    path = ship_path(model, ms, start, q, fuels)
    base = evaluate(model.profile, scenario, years, rules)
    after = evaluate(model.profile, scenario, years, rules, path)
    by_year = {b.year: (b, a) for b, a in zip(base, after, strict=True)}

    # physical change from the power model (EU-recorded year; worldwide view scales it up)
    eff = PW.Effects.combine(*(m.effects(model.power, model.cls, q) for m in ms))
    res = PW.run(model.power, eff, fuels=fuels)
    scale = 1.0
    if scenario.view == "ww" and model.profile.eu_share is not None:
        scale = 1 / max(model.profile.eu_share.share, 0.01)
    d_hours = (res.hours_sea - model.base.hours_sea) * scale
    avoided = (_wtw_t(model.base.fuel_t, fuels, rules.fueleu.gwp) - _wtw_t(res.fuel_t, fuels, rules.fueleu.gwp)
               + res.co2_captured_t) * scale

    imo_type = model.cls.type
    daily = prices.earnings(imo_type) * usd
    time_share = prices.time_cost_share["likely"]
    capex0 = sum(m.capex_usd(model.power, model.cls, 1 - q) for m in ms) * usd
    opex = sum(m.opex_usd(model.power, model.cls, 1 - q) for m in ms) * usd
    offhire = sum(m.offhire_days.quantile(1 - q) for m in ms) * daily

    flows: list[YearFlow] = []
    for y in range(start, end + 1):
        f_old = sum(t * prices.fuel_usd_t(k, y, price_path) for k, t in model.base.fuel_t.items()) * usd * scale
        f_new = sum(t * prices.fuel_usd_t(k, y, price_path) for k, t in res.fuel_t.items()) * usd * scale
        elec = -res.grid_kwh * prices.electricity_eur_kwh[price_path] * scale
        b, a = by_year[y]
        carbon = b.total_eur - a.total_eur
        cap = 0.0
        for m in ms:
            life = max(int(round(m.lifetime.quantile(q))), 1)
            if (y - start) % life == 0:
                cap -= m.capex_usd(model.power, model.cls, 1 - q) * usd
        if y == end:                                  # residual value of the last installation
            for m in ms:
                life = max(int(round(m.lifetime.quantile(q))), 1)
                used = (end - start) % life + 1
                if used < life:
                    cap += m.capex_usd(model.power, model.cls, 1 - q) * usd * (life - used) / life
        flows.append(YearFlow(y, f_old - f_new, elec, carbon, -opex, cap,
                              -offhire if y == start else 0.0,
                              -max(d_hours, 0.0) / 24 * daily * time_share, avoided))
    npv = sum(f.net / (1 + r) ** (f.year - base_year) for f in flows)
    cum, payback = 0.0, None
    for f in flows:
        cum += f.net
        if cum >= 0 and payback is None:
            payback = f.year
    total_avoided = sum(f.co2e_avoided for f in flows)
    return Appraisal(flows, npv, r, payback, total_avoided,
                     (-npv / total_avoided) if total_avoided > 0 else None, capex0, after, base)
