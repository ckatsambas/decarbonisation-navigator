"""SMAA-2 on inputs and weights, with a vectorised appraisal (decision 0010-4).

Two layers keep this fast and exact:

1. *Physics on a grid.* What a measure does to the ship (fuel by type, ETS allowances, FuelEU energy,
   intensity and balance, IMO NZF energy and intensity, hours at sea, shore electricity) depends only on
   that measure's own uncertain effect. It is computed with the scalar engine at a grid of effect
   quantiles and interpolated for each draw.
2. *Money vectorised.* Everything that depends on prices or scenarios is computed with NumPy for all
   draws at once: EUA, fuel and electricity prices, the FuelEU least-cost route with consecutive
   penalties, the NZF tiers under the drawn outcome, earnings lost to off-hire and slower sailing,
   discounting and renewals.

A draw at the most likely values reproduces `economics.appraise` (tested).

SMAA-2 (Lahdelma & Salminen 2001) then ranks the alternatives in every draw by an additive utility
and reports the rank acceptability indices b_i^r, the central weight vectors w_i^c and the confidence
factors p_i^c.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from .. import economics as EC
from .. import fuels as F
from .. import power as PW
from ..compliance import Rules, Scenario
from ..measures import Measure, ShipModel, ship_path
from ..models import YearSeries
from ..regulation.eu_ets import cost_path
from ..regulation.fueleu import fueleu_path
from ..regulation.imo_nzf import SCENARIOS
from ..uncertainty import Estimate, Sampler
from . import criteria as C

GRID = np.linspace(0.0, 1.0, 11)
FOSSIL = {"hfo", "lfo", "mgo", "lng_otto_ms", "lng_otto_ss", "lng_diesel_ss", "lng_lbsi", "methanol"}
PERT01 = Estimate(0.0, 0.5, 1.0)
FIRST_YEAR = 2025                      # FuelEU starts; the consecutive-penalty counter runs from here


# ------------------------------------------------------------------ physics on the grid
@dataclass
class Physics:
    """Per grid point g and year y (years = FIRST_YEAR … 2050)."""
    allowances: np.ndarray        # (G, Y) EUAs per year (= cost at 1 €/EUA)
    fe_in: np.ndarray             # (Y,) bool
    fe_energy: np.ndarray         # (G, Y) MJ in FuelEU scope
    fe_int: np.ndarray            # (G, Y) gCO2e/MJ
    fe_target: np.ndarray         # (Y,)
    nzf_energy: np.ndarray        # (G, Y) MJ, EU-recorded activity
    nzf_gfi: np.ndarray           # (G, Y)
    fuel_t: dict[str, np.ndarray]  # fuel → (G,) tonnes a year (EU-recorded)
    grid_kwh: np.ndarray          # (G,)
    hours: np.ndarray             # (G,)
    wtw: np.ndarray               # (G,) t CO2e well-to-wake a year, after capture

    def at(self, q: np.ndarray) -> dict:
        """Linear interpolation on the grid for draws q (K,)."""
        g = len(self.grid_kwh)
        if g == 1:                                   # a single point (the ship without measures)
            q = np.zeros_like(q)
            i0 = np.zeros(len(q), int)
            t = np.zeros((len(q), 1))

            def lerp2(a):
                return np.repeat(a[:1], len(q), axis=0)

            def lerp1(a):
                return np.repeat(a[:1], len(q))

            return {"allowances": lerp2(self.allowances), "fe_energy": lerp2(self.fe_energy), "fe_int": lerp2(self.fe_int),
                    "nzf_energy": lerp2(self.nzf_energy), "nzf_gfi": lerp2(self.nzf_gfi),
                    "fuel_t": {k: lerp1(v) for k, v in self.fuel_t.items()}, "grid_kwh": lerp1(self.grid_kwh),
                    "hours": lerp1(self.hours), "wtw": lerp1(self.wtw)}
        pos = np.clip(q, 0, 1) * (g - 1)
        i0 = np.minimum(pos.astype(int), g - 2)
        t = (pos - i0)[:, None]

        def lerp2(a):
            return a[i0] * (1 - t) + a[i0 + 1] * t

        def lerp1(a):
            return a[i0] * (1 - t[:, 0]) + a[i0 + 1] * t[:, 0]

        return {"allowances": lerp2(self.allowances), "fe_energy": lerp2(self.fe_energy), "fe_int": lerp2(self.fe_int),
                "nzf_energy": lerp2(self.nzf_energy), "nzf_gfi": lerp2(self.nzf_gfi),
                "fuel_t": {k: lerp1(v) for k, v in self.fuel_t.items()}, "grid_kwh": lerp1(self.grid_kwh),
                "hours": lerp1(self.hours), "wtw": lerp1(self.wtw)}


def _physics(model: ShipModel, ms: tuple[Measure, ...], rules: Rules, start: int, grid=GRID) -> Physics:
    prof, fuels = model.profile, rules.fuels
    years = range(FIRST_YEAR, 2051)
    G, Y = len(grid), len(years)
    out = {k: np.zeros((G, Y)) for k in ("allowances", "fe_energy", "fe_int", "nzf_energy", "nzf_gfi")}
    fuel_t: dict[str, np.ndarray] = {}
    grid_kwh, hours, wtw = np.zeros(G), np.zeros(G), np.zeros(G)
    fe_in, fe_target = np.zeros(Y, bool), np.zeros(Y)
    for gi, q in enumerate(grid):
        path = ship_path(model, ms, start, float(q), fuels)
        ets = cost_path(prof.ship, lambda y, p=path: p(y).ets_emissions, 1.0, years, rules.ets)
        fe = fueleu_path(prof.ship, lambda y, p=path: p(y).emissions, lambda y, p=path: p(y).mix, years,
                         rules.fueleu, fuels)
        for yi, y in enumerate(years):
            st = path(y)
            out["allowances"][gi, yi] = ets[yi].allowances
            out["fe_energy"][gi, yi] = fe[yi].energy_mj
            out["fe_int"][gi, yi] = fe[yi].intensity
            fe_in[yi] = fe[yi].in_scope
            fe_target[yi] = fe[yi].target
            m = st.mix
            out["nzf_energy"][gi, yi] = F.fuel_tonnes(st.emissions.co2.total, m, fuels) * F.energy_per_t(m, fuels)
            out["nzf_gfi"][gi, yi] = F.intensity(m, fuels, rules.nzf.gwp)
        eff = PW.Effects.combine(*(m.effects(model.power, model.cls, float(q)) for m in ms))
        res = PW.run(model.power, eff, fuels=fuels)
        for k, t in res.fuel_t.items():
            fuel_t.setdefault(k, np.zeros(G))[gi] = t
        grid_kwh[gi], hours[gi] = res.grid_kwh, res.hours_sea
        wtw[gi] = EC._wtw_t(res.fuel_t, fuels, rules.fueleu.gwp) - res.co2_captured_t
    for k in model.base.fuel_t:
        fuel_t.setdefault(k, np.zeros(G))
    return Physics(fe_in=fe_in, fe_target=fe_target, fuel_t=fuel_t, grid_kwh=grid_kwh, hours=hours, wtw=wtw, **out)


# ------------------------------------------------------------------ draws
@dataclass
class Draws:
    """Values for K draws. Arrays of shape (K,); `effect`, `cost` and `offhire` hold one array per
    alternative key (independent per measure); everything else is common to all alternatives."""
    k: int
    effect: dict[str, np.ndarray]
    cost: dict[str, np.ndarray]
    offhire: dict[str, np.ndarray]
    fossil: np.ndarray            # price level 0 = low path, 0.5 = central, 1 = high
    alt: np.ndarray
    elec: np.ndarray
    eua: np.ndarray
    pool: np.ndarray              # € per t CO2e
    premium: np.ndarray           # $ per t biofuel
    scenario: np.ndarray          # index into SCENARIOS
    share: np.ndarray             # EU share (worldwide view)
    earnings: np.ndarray          # $ per day
    time_share: np.ndarray
    rate: np.ndarray

    @classmethod
    def likely(cls, keys: list[str], k: int, model: ShipModel, scenario: Scenario, rules: Rules,
               prices: EC.Prices, st: C.Settings) -> Draws:
        """K identical draws at the most likely values (used to check against the scalar engine)."""
        one = np.ones(k)
        lvl = {"low": 0.0, "central": 0.5, "high": 1.0}[st.prices]
        mk = rules.markets
        share = model.profile.eu_share.share if model.profile.eu_share else 1.0
        return cls(k, {a: one * 0.5 for a in keys}, {a: one * 0.5 for a in keys}, {a: one * 0.5 for a in keys},
                   one * lvl, one * lvl, one * lvl, one * 0.5,
                   one * (scenario.pool_price if scenario.pool_price is not None else mk.pool_price.likely),
                   one * (scenario.bio_premium_usd if scenario.bio_premium_usd is not None else mk.bio_premium.likely),
                   (one * SCENARIOS.index(scenario.nzf)).astype(int), one * share,
                   one * prices.earnings(model.cls.type), one * prices.time_cost_share["likely"], one * st.rate)

    @classmethod
    def sample(cls, keys: list[str], n: int, model: ShipModel, rules: Rules, prices: EC.Prices,
               nzf_prob: dict[str, float] | None = None, seed: int = 20261204, uncertain_inputs: bool = True) -> Draws:
        s = Sampler(n, seed)
        mk = rules.markets
        prob = nzf_prob or mk.nzf_probability
        p = np.array([prob.get(x, 0.0) for x in SCENARIOS], float)
        p = p / p.sum()
        if not uncertain_inputs:
            return cls.likely(keys, n, model, Scenario(), rules, prices, C.Settings())
        sc = np.searchsorted(np.cumsum(p), s.uniform("nzf_outcome"), side="right").clip(0, len(SCENARIOS) - 1)
        share_est = model.profile.eu_share.estimate if model.profile.eu_share else None
        share = s.draw("eu_share", share_est) if share_est is not None and not share_est.is_exact else \
            np.full(n, model.profile.eu_share.share if model.profile.eu_share else 1.0)
        earn = prices.earnings_usd_day.get(model.cls.type) or prices.earnings_usd_day["default"]
        ts, dr = prices.time_cost_share, prices.discount
        return cls(n, {a: s.uniform(f"effect:{a}") for a in keys}, {a: s.uniform(f"cost:{a}") for a in keys},
                   {a: s.uniform(f"offhire:{a}") for a in keys},
                   s.draw("price_fossil", PERT01), s.draw("price_alt", PERT01), s.draw("price_elec", PERT01),
                   s.draw("price_eua", PERT01), s.draw("pool_price", mk.pool_price), s.draw("bio_premium", mk.bio_premium),
                   sc, np.clip(share, 0.01, 1.0),
                   s.draw("earnings", Estimate(earn["low"], earn["likely"], earn["high"])),
                   s.draw("time_share", Estimate(ts["low"], ts["likely"], ts["high"])),
                   s.draw("discount", Estimate(dr["low"], dr["likely"], dr["high"])))


def _level(lo: np.ndarray | float, c: np.ndarray | float, hi: np.ndarray | float, u: np.ndarray) -> np.ndarray:
    """0 → low, 0.5 → central, 1 → high (piecewise linear)."""
    return np.where(u <= 0.5, lo + (c - lo) * 2 * u, c + (hi - c) * (2 * u - 1))


def _tier(gfi, energy, base, direct, nz) -> np.ndarray:
    """Vectorised imo_nzf.tier_cost (USD); base/direct NaN = NZF not applying."""
    t2 = np.where(gfi > base, (gfi - base) * energy / 1e6, 0.0)
    t1 = np.where(gfi > base, (base - direct) * energy / 1e6,
                  np.where(gfi > direct, (gfi - direct) * energy / 1e6, 0.0))
    sur = np.where(gfi <= direct, (direct - gfi) * energy / 1e6, 0.0)
    usd = t1 * nz.tier1_usd + t2 * nz.tier2_usd - sur * nz.surplus_usd
    return np.where(np.isnan(base), 0.0, usd)


# ------------------------------------------------------------------ vectorised regimes
class Simulator:
    """Prepared once per ship and shortlist; `npv()` evaluates any set of draws."""

    def __init__(self, model: ShipModel, alternatives: dict[str, tuple[Measure, ...]], scenario: Scenario,
                 st: C.Settings, rules: Rules | None = None, prices: EC.Prices | None = None):
        self.model, self.scenario, self.st = model, scenario, st
        self.rules = rules or Rules.load()
        self.prices = prices or EC.default_prices()
        self.alts = {k: ms for k, ms in alternatives.items() if ms}
        self.base = _physics(model, (), self.rules, st.start, np.array([0.5]))
        self.phys = {k: _physics(model, ms, self.rules, st.start) for k, ms in self.alts.items()}
        self.years = np.arange(FIRST_YEAR, 2051)
        nz = self.rules.nzf
        tgt = np.full((len(SCENARIOS), len(self.years), 2), np.nan)
        applies = nz.in_scope(model.profile.ship) and not model.profile.domestic_only
        for si, s in enumerate(SCENARIOS):
            for yi, y in enumerate(self.years):
                t = nz.targets(int(y), s)
                if t is not None and applies:
                    tgt[si, yi] = t
        self.targets = tgt
        mk = self.rules.markets
        self.eua = {k: YearSeries(v) for k, v in mk.eua_paths.items()}
        self.base_wtw = float(self.base.wtw[0])
        sp, cls = model.power, model.cls
        # capital and running cost of each measure on the effect grid (cost quantile → USD)
        self._costs = {(k, m.key): (np.array([m.capex_usd(sp, cls, float(q)) for q in GRID]),
                                    np.array([m.opex_usd(sp, cls, float(q)) for q in GRID]))
                       for k, ms in self.alts.items() for m in ms}

    # --------------------------------------------------------------
    def _carbon(self, ph: dict, d: Draws, ww_scale: np.ndarray) -> np.ndarray:
        """€ per draw and year: EU ETS + FuelEU route + IMO NZF (K, Y)."""
        rules, fr, nz = self.rules, self.rules.fueleu, self.rules.nzf
        K, Y = d.k, len(self.years)
        eua = np.stack([_level(self.eua["low"].at(int(y)), self.eua["central"].at(int(y)), self.eua["high"].at(int(y)),
                               d.eua) for y in self.years], axis=1)
        ets = ph["allowances"] * eua
        base = self.targets[d.scenario, :, 0]                 # (K, Y)
        direct = self.targets[d.scenario, :, 1]
        z_energy = ph["nzf_energy"] * ww_scale[:, None]
        z_usd = _tier(ph["nzf_gfi"], z_energy, base, direct, nz)
        z_eur = z_usd * nz.eur_per_usd
        if self.scenario.baseline == "pay":
            out = np.zeros((K, Y))
            n = np.zeros(K)
            for yi in range(Y):
                e, inten = ph["fe_energy"][:, yi], ph["fe_int"][:, yi]
                bal = (self.base_target(yi) - inten) * e / 1e6
                deficit = self.base_in(yi) & (bal < 0) & (e > 0)
                n = np.where(deficit, n + 1, 0)
                pen = np.where(deficit, -bal * 1e6 / np.where(inten > 0, inten, 1) / fr.vlsfo_mj_per_t * fr.penalty
                               * (1 + (n - 1) * fr.increment), 0.0)
                out[:, yi] = ets[:, yi] + pen + z_eur[:, yi]
            return out
        bio = rules.fuels[rules.markets.bio_fuel]
        i_bio_fe, i_bio_nzf = bio.wtw(fr.gwp), bio.wtw(nz.gwp)
        premium_eur = d.premium * nz.eur_per_usd
        out = np.zeros((K, Y))
        n = np.zeros(K)
        for yi in range(Y):
            e, inten = ph["fe_energy"][:, yi], ph["fe_int"][:, yi]
            tgt = self.base_target(yi)
            bal = (tgt - inten) * e / 1e6
            active = self.base_in(yi) & (bal < 0) & (e > 0)
            deficit = -bal
            pen = deficit * 1e6 / np.where(inten > 0, inten, 1) / fr.vlsfo_mj_per_t * fr.penalty * (1 + n * fr.increment)
            pay = ets[:, yi] + pen + z_eur[:, yi]
            pool = ets[:, yi] + deficit * d.pool + z_eur[:, yi]
            share = np.where(inten > i_bio_fe, (inten - tgt) / np.where(inten > i_bio_fe, inten - i_bio_fe, 1), 1.0)
            share = np.clip(share, 0, 1)
            bio_t = share * e / (bio.lcv * 1e6)
            ze = z_energy[:, yi]
            s_all = np.where(ze > 0, np.minimum(share * e / np.where(ze > 0, ze, 1), 1.0), 0.0)
            gfi_b = (1 - s_all) * ph["nzf_gfi"][:, yi] + s_all * i_bio_nzf
            z_bio = _tier(gfi_b, ze, base[:, yi], direct[:, yi], nz) * nz.eur_per_usd
            z_bio = np.where(ze > 0, z_bio, z_eur[:, yi])
            biop = ets[:, yi] * (1 - share) + bio_t * premium_eur + z_bio
            choice = np.argmin(np.stack([pay, pool, biop]), axis=0)
            best = np.choose(choice, [pay, pool, biop])
            out[:, yi] = np.where(active, best, ets[:, yi] + z_eur[:, yi])
            n = np.where(active & (choice == 0), n + 1, 0)
        return out

    def base_target(self, yi: int) -> float:
        return float(self.base.fe_target[yi])

    def base_in(self, yi: int) -> bool:
        return bool(self.base.fe_in[yi])

    # --------------------------------------------------------------
    def _fuel_cost(self, fuel_t: dict[str, np.ndarray], d: Draws, years: np.ndarray) -> np.ndarray:
        pr, usd = self.prices, self.rules.nzf.eur_per_usd
        out = np.zeros((d.k, len(years)))
        for f, t in fuel_t.items():
            series = pr.fuel[f]
            u = d.fossil if f in FOSSIL else d.alt
            p = np.stack([_level(series["low"].at(int(y)), series["central"].at(int(y)), series["high"].at(int(y)), u)
                          for y in years], axis=1)
            out += t[:, None] * p
        return out * usd

    def npv(self, key: str, d: Draws, scenario_index: np.ndarray | None = None) -> dict[str, np.ndarray]:
        """NPV and companions for alternative `key` over the draws."""
        if scenario_index is not None:
            d = replace(d, scenario=scenario_index)
        ms, ph_grid = self.alts[key], self.phys[key]
        st, pr, usd = self.st, self.prices, self.rules.nzf.eur_per_usd
        ww = self.scenario.view == "ww" and self.model.profile.eu_share is not None
        scale = 1 / np.clip(d.share, 0.01, 1) if ww else np.ones(d.k)
        q = d.effect[key]
        ph = ph_grid.at(q)
        bph = self.base.at(np.zeros(d.k))
        c_after = self._carbon(ph, d, scale)
        c_base = self._base_carbon(d, scale)
        years = np.arange(st.start, st.end + 1)
        idx = years - FIRST_YEAR
        carbon = (c_base - c_after)[:, idx]
        fuel = (self._fuel_cost(bph["fuel_t"], d, years) - self._fuel_cost(ph["fuel_t"], d, years)) * scale[:, None]
        elec_p = _level(pr.electricity_eur_kwh["low"], pr.electricity_eur_kwh["central"],
                        pr.electricity_eur_kwh["high"], d.elec)
        elec = -(ph["grid_kwh"] * elec_p * scale)[:, None] * np.ones(len(years))
        daily = d.earnings * usd
        d_hours = (ph["hours"] - bph["hours"]) * scale
        time = (-np.maximum(d_hours, 0) / 24 * daily * d.time_share)[:, None] * np.ones(len(years))
        qc = d.cost[key]
        capex_now = np.zeros(d.k)
        opex = np.zeros(d.k)
        cap = np.zeros((d.k, len(years)))
        off = np.zeros(d.k)
        for m in ms:
            c_m = np.interp(qc, GRID, self._costs[(key, m.key)][0]) * usd
            o_m = np.interp(qc, GRID, self._costs[(key, m.key)][1]) * usd
            capex_now += c_m
            opex += o_m
            life = max(int(round(m.lifetime.quantile(0.5))), 1)
            for j, y in enumerate(years):
                if (y - st.start) % life == 0:
                    cap[:, j] -= c_m
            used = (st.end - st.start) % life + 1
            if used < life:
                cap[:, -1] += c_m * (life - used) / life
            off += np.asarray(m.offhire_days.from_uniform(d.offhire[key]), float)
        offhire = np.zeros((d.k, len(years)))
        offhire[:, 0] = -off * daily
        flows = fuel + elec + carbon - opex[:, None] + cap + offhire + time
        disc = (1 + d.rate[:, None]) ** (years[None, :] - 2026)
        npv = (flows / disc).sum(axis=1)
        avoided_year = (self.base_wtw - ph["wtw"]) * scale
        return {"npv": npv, "capex": capex_now, "offhire": off, "cut": 1 - ph["wtw"] / self.base_wtw,
                "avoided": avoided_year * len(years), "flows": flows}

    def _base_carbon(self, d: Draws, scale: np.ndarray) -> np.ndarray:
        return self._carbon(self.base.at(np.zeros(d.k)), d, scale)


# ------------------------------------------------------------------ SMAA-2
@dataclass
class SmaaResult:
    keys: list[str]
    acceptability: np.ndarray       # (A, A): share of draws with alternative i at rank r+1
    central_weights: np.ndarray     # (A, C)
    confidence: np.ndarray          # (A,)
    values: dict[str, np.ndarray]   # criterion → (K, A) sampled values
    weights: np.ndarray             # (K, C)
    n: int
    details: dict = field(default_factory=dict)

    @property
    def first_rank(self) -> np.ndarray:
        return self.acceptability[:, 0]

    def expected_rank(self) -> np.ndarray:
        r = np.arange(1, len(self.keys) + 1)
        return self.acceptability @ r


def sample_weights(center: np.ndarray | None, n: int, kappa: float, seed: int) -> np.ndarray:
    """Dirichlet around the company weights (concentration κ), or uniform on the simplex if none."""
    rng = np.random.default_rng(seed + 7)
    c = len(C.CRITERIA)
    if center is None:
        return rng.dirichlet(np.ones(c), n)
    alpha = np.maximum(np.asarray(center, float) * kappa, 1e-3)
    return rng.dirichlet(alpha, n)


def run(sim: Simulator, include_do_nothing: bool = True, center_weights: np.ndarray | None = None,
        n: int = 10000, kappa: float = 100.0, seed: int = 20261204, nzf_prob: dict | None = None,
        uncertain_inputs: bool = True) -> SmaaResult:
    keys = list(sim.alts)
    d = Draws.sample(keys, n, sim.model, sim.rules, sim.prices, nzf_prob, seed, uncertain_inputs)
    A = len(keys) + (1 if include_do_nothing else 0)
    vals = {k: np.zeros((n, A)) for k in C.KEYS}
    lib = {a: sim.alts[a] for a in keys}
    as_drafted = np.full(n, SCENARIOS.index("as_drafted"))
    not_adopted = np.full(n, SCENARIOS.index("not_adopted"))
    for j, a in enumerate(keys):
        r = sim.npv(a, d)
        ms = lib[a]
        vals["npv"][:, j] = r["npv"]
        vals["capex"][:, j] = r["capex"]
        vals["cut"][:, j] = r["cut"]
        vals["offhire"][:, j] = r["offhire"]
        vals["nzf_exposure"][:, j] = np.abs(sim.npv(a, d, as_drafted)["npv"] - sim.npv(a, d, not_adopted)["npv"])
        vals["trl"][:, j] = min(m.attributes.get("trl", 9) for m in ms)
        vals["cargo"][:, j] = sum(m.attributes.get("cargo_loss", 0.0) for m in ms)
        vals["availability"][:, j] = min(m.attributes.get("availability", 5) for m in ms)
        vals["safety"][:, j] = min(m.attributes.get("safety", 5) for m in ms)
    if include_do_nothing:
        dn = C.do_nothing().values
        for k in C.KEYS:
            vals[k][:, -1] = dn[k]
        keys = [*keys, C.DO_NOTHING]
    x = np.stack([vals[k] for k in C.KEYS], axis=2)          # (K, A, C)
    lo = x.min(axis=(0, 1))
    hi = x.max(axis=(0, 1))
    span = np.where(hi > lo, hi - lo, 1.0)
    z = (x - lo) / span
    z = np.where(C.MAXIMISE, z, 1 - z)
    z = np.where(hi > lo, z, 0.5)
    w = sample_weights(center_weights, n, kappa, seed)
    u = np.einsum("kac,kc->ka", z, w)
    order = np.argsort(-u, axis=1, kind="stable")
    ranks = np.empty_like(order)
    rows = np.arange(n)[:, None]
    ranks[rows, order] = np.arange(A)[None, :]
    acc = np.stack([(ranks == r).mean(axis=0) for r in range(A)], axis=1)       # (A, R)
    first = ranks == 0
    central = np.array([w[first[:, i]].mean(axis=0) if first[:, i].any() else np.full(w.shape[1], np.nan)
                        for i in range(A)])
    conf = np.zeros(A)
    for i in range(A):
        if np.isnan(central[i]).any():
            continue
        ui = np.einsum("kac,c->ka", z, central[i])
        conf[i] = (ui.argmax(axis=1) == i).mean()
    return SmaaResult(keys, acc, central, conf, vals, w, n, {"bounds": (lo, hi)})
