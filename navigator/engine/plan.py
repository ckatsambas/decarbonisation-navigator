"""Timed investment plans (decision 0014): each measure has its own installation year.

A plan is a set of (measure, year). In every year the ship runs with the measures installed by then,
so the physics (power model), the carbon bill (all regimes) and the cash flow follow the plan year by
year. With every measure installed in the same year this is exactly `economics.appraise`.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from . import power as PW
from .compliance import Rules, Scenario, evaluate
from .economics import Appraisal, Prices, YearFlow, _wtw_t, default_prices
from .measures import Measure, ShipModel, _ets_rules, year_state


@dataclass(frozen=True)
class Plan:
    """Measures with their installation years, sorted by year then key."""

    installs: tuple[tuple[str, int], ...]

    @classmethod
    def of(cls, items: Mapping[str, int] | Iterable[tuple[str, int]]) -> Plan:
        pairs = items.items() if isinstance(items, Mapping) else items
        return cls(tuple(sorted(((k, int(y)) for k, y in pairs), key=lambda p: (p[1], p[0]))))

    @property
    def keys(self) -> list[str]:
        return [k for k, _ in self.installs]

    @property
    def years(self) -> dict[str, int]:
        return dict(self.installs)

    def active(self, year: int) -> frozenset[str]:
        return frozenset(k for k, y in self.installs if y <= year)

    def __bool__(self) -> bool:
        return bool(self.installs)


class SetPhysics:
    """Power-model result and regime state for each distinct set of measures (cached)."""

    def __init__(self, model: ShipModel, lib: Mapping[str, Measure], q: float, rules: Rules):
        self.model, self.lib, self.q, self.rules = model, lib, q, rules
        self.zero, self.credit = _ets_rules()
        self._run: dict[frozenset, PW.PowerResult] = {}
        self._state: dict[frozenset, object] = {}
        self.base_results: dict[tuple, list] = {}       # doing-nothing regimes per scenario and years

    def run(self, keys: frozenset[str]) -> PW.PowerResult:
        if keys not in self._run:
            if not keys:
                self._run[keys] = self.model.base
            else:
                eff = PW.Effects.combine(*(self.lib[k].effects(self.model.power, self.model.cls, self.q)
                                           for k in sorted(keys)))
                self._run[keys] = PW.run(self.model.power, eff, fuels=self.rules.fuels)
        return self._run[keys]

    def state(self, keys: frozenset[str]):
        if keys not in self._state:
            self._state[keys] = year_state(self.model, self.run(keys), self.rules.fuels, self.zero, self.credit)
        return self._state[keys]


def horizon(model: ShipModel, start: int, prices: Prices, end: int | None = None,
            build_year: int | None = None) -> int:
    """Last year of the appraisal: the ship's 25th year at most 2050 (as in `appraise`)."""
    if end is None:
        built = build_year or model.profile.ship.build_year
        end = built + prices.ship_life if built else start + 19
    return min(max(end, start), 2050)


def appraise_plan(model: ShipModel, lib: Mapping[str, Measure], plan: Plan, scenario: Scenario,
                  q: float = 0.5, price_path: str = "central", discount: float | None = None,
                  end: int | None = None, rules: Rules | None = None, prices: Prices | None = None,
                  build_year: int | None = None, base_year: int = 2026, first_year: int | None = None,
                  physics: SetPhysics | None = None) -> Appraisal:
    """NPV of a timed plan against doing nothing. `first_year` fixes the start of the cash-flow window
    (default: the first installation), so plans with different first years compare on one window."""
    rules = rules or Rules.load()
    prices = prices or default_prices()
    fuels = rules.fuels
    phys = physics or SetPhysics(model, lib, q, rules)
    r = prices.discount["likely"] if discount is None else discount
    usd = rules.nzf.eur_per_usd
    start = first_year if first_year is not None else (min(y for _, y in plan.installs) if plan else 2026)
    end = horizon(model, start, prices, end, build_year)
    years = range(min(2024, start), 2051)
    before = phys.state(frozenset())
    bkey = (id(scenario), years.start, id(rules))
    if bkey not in phys.base_results:
        phys.base_results[bkey] = (scenario, evaluate(model.profile, scenario, years, rules))
    base = phys.base_results[bkey][1]
    after = evaluate(model.profile, scenario, years, rules, lambda y: phys.state(plan.active(y)) if plan else before)
    by_year = {b.year: (b, a) for b, a in zip(base, after, strict=True)}
    scale = 1.0
    if scenario.view == "ww" and model.profile.eu_share is not None:
        scale = 1 / max(model.profile.eu_share.share, 0.01)
    daily = prices.earnings(model.cls.type) * usd
    time_share = prices.time_cost_share["likely"]
    base_wtw = _wtw_t(model.base.fuel_t, fuels, rules.fueleu.gwp)
    ms = {k: lib[k] for k in plan.keys}
    capex = {k: m.capex_usd(model.power, model.cls, 1 - q) * usd for k, m in ms.items()}
    opex = {k: m.opex_usd(model.power, model.cls, 1 - q) * usd for k, m in ms.items()}
    life = {k: max(int(round(m.lifetime.quantile(q))), 1) for k, m in ms.items()}
    off = {k: m.offhire_days.quantile(1 - q) * daily for k, m in ms.items()}
    yr = plan.years
    flows: list[YearFlow] = []
    for y in range(start, end + 1):
        act = plan.active(y)
        res = phys.run(act)
        f_old = sum(t * prices.fuel_usd_t(k, y, price_path) for k, t in model.base.fuel_t.items()) * usd * scale
        f_new = sum(t * prices.fuel_usd_t(k, y, price_path) for k, t in res.fuel_t.items()) * usd * scale
        elec = -res.grid_kwh * prices.electricity_eur_kwh[price_path] * scale
        b, a = by_year[y]
        d_hours = (res.hours_sea - model.base.hours_sea) * scale
        avoided = (base_wtw - _wtw_t(res.fuel_t, fuels, rules.fueleu.gwp) + res.co2_captured_t) * scale
        cap = 0.0
        for k in act:
            if (y - yr[k]) % life[k] == 0:
                cap -= capex[k]
            if y == end:
                used = (end - yr[k]) % life[k] + 1
                if used < life[k]:
                    cap += capex[k] * (life[k] - used) / life[k]
        flows.append(YearFlow(y, f_old - f_new, elec, b.total_eur - a.total_eur, -sum(opex[k] for k in act), cap,
                              -sum(off[k] for k in act if yr[k] == y),
                              -max(d_hours, 0.0) / 24 * daily * time_share, avoided))
    npv = sum(f.net / (1 + r) ** (f.year - base_year) for f in flows)
    cum, payback = 0.0, None
    for f in flows:
        cum += f.net
        if cum >= 0 and payback is None:
            payback = f.year
    total = sum(f.co2e_avoided for f in flows)
    return Appraisal(flows, npv, r, payback, total, (-npv / total) if total > 0 else None,
                     sum(capex.values()), after, base)
