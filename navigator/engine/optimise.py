"""Investment plans by mixed-integer programming (decision 0014).

Which measures to install, and in which year, to get the highest NPV for every level of emissions cut
(ε-constraint Pareto front)?

Formulation (one scenario):
    x[i, s] ∈ {0, 1}  measure i installed in year s (s in the installation window); Σ_s x[i, s] ≤ 1
    a[i, t] = Σ_{s ≤ t} x[i, s]          measure i is working in year t
    b[ij, t] = a[i, t] · a[j, t]         exact for binaries with the three McCormick inequalities
    NPV  ≈ Σ_t δ_t (Σ_i u[i, t] a[i, t] + Σ_ij p[ij, t] b[ij, t]) − Σ_{i,s} K[i, s] x[i, s]
    cut  ≈ Σ_t   (Σ_i e[i, t] a[i, t] + Σ_ij f[ij, t] b[ij, t])
    measures that exclude each other: Σ_s x[i, s] + Σ_s x[j, s] ≤ 1;  optional budget per year.

u and e are the yearly operating value (fuel, electricity, carbon under every regime, time cost) and
the tonnes avoided of each measure alone; p and f are the exact corrections for each pair, both from
the full engine (power model + regimes). K holds capex at installation and renewals, residual value,
off-hire and opex, discounted. Interactions of three or more measures are left out of the search, so
every plan the search returns is re-appraised exactly with `plan.appraise_plan`; the front shows the
exact values and the gap to the search's estimate is reported.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from .compliance import Rules, Scenario, evaluate
from .economics import Appraisal, Prices, _wtw_t, default_prices
from .measures import Measure, ShipModel
from .plan import Plan, SetPhysics, appraise_plan, horizon


@dataclass(frozen=True)
class Settings:
    start: int = 2027                 # first year of installations and of the cash-flow window
    window: int = 9                   # installation years: start … start + window − 1
    price_path: str = "central"
    discount: float = 0.08
    q: float = 0.5
    budget_eur: float | None = None   # capex limit for new installations in any one year
    end: int | None = None


@dataclass
class Coefficients:
    keys: list[str]
    years: list[int]                  # cash-flow years
    install_years: list[int]
    disc: np.ndarray                  # (T,) discount factors
    u: np.ndarray                     # (n, T) € per year when working (undiscounted)
    e: np.ndarray                     # (n, T) t CO2e avoided per year
    pairs: list[tuple[int, int]]
    p: np.ndarray                     # (P, T)
    f: np.ndarray                     # (P, T)
    K: np.ndarray                     # (n, S) discounted fixed cost of installing i in year s
    capex: np.ndarray                 # (n,) € per installation
    clashes: list[tuple[int, int]]
    value: Callable[[frozenset[str]], tuple[np.ndarray, np.ndarray]] | None = field(default=None, repr=False)

    def plan_value(self, plan: Plan) -> tuple[float, float]:
        """NPV and t CO2e of a timed plan from the per-set yearly values: exact for the physics and the
        regimes year by year (only the FuelEU repeat-penalty count is taken per set)."""
        yrs = plan.years
        npv = 0.0
        cut = 0.0
        for t, y in enumerate(self.years):
            v, e = self.value(plan.active(y))
            npv += self.disc[t] * v[t]
            cut += e[t]
        for k, y in yrs.items():
            npv -= self.K[self.keys.index(k), self.install_years.index(y)]
        return npv, cut


@dataclass
class PlanResult:
    plan: Plan
    estimate_npv: float
    estimate_cut: float
    appraisal: Appraisal
    label: str = ""

    @property
    def npv(self) -> float:
        return self.appraisal.npv

    @property
    def avoided(self) -> float:
        return self.appraisal.co2e_avoided


@dataclass
class Front:
    plans: list[PlanResult]
    coefficients: Coefficients
    notes: dict = field(default_factory=dict)


def coefficients(model: ShipModel, lib: Mapping[str, Measure], keys: Sequence[str], scenario: Scenario,
                 st: Settings, rules: Rules | None = None, prices: Prices | None = None,
                 clashes: Sequence[tuple[str, str]] = (), progress: Callable[[float], None] | None = None,
                 physics: SetPhysics | None = None) -> Coefficients:
    rules = rules or Rules.load()
    prices = prices or default_prices()
    fuels = rules.fuels
    phys = physics or SetPhysics(model, lib, st.q, rules)
    usd = rules.nzf.eur_per_usd
    end = horizon(model, st.start, prices, st.end)
    years = list(range(st.start, end + 1))
    install = [y for y in range(st.start, st.start + st.window) if y <= end]
    T, n = len(years), len(keys)
    disc = np.array([(1 + st.discount) ** -(y - 2026) for y in years])
    scale = 1.0
    if scenario.view == "ww" and model.profile.eu_share is not None:
        scale = 1 / max(model.profile.eu_share.share, 0.01)
    daily = prices.earnings(model.cls.type) * usd
    time_share = prices.time_cost_share["likely"]
    base_wtw = _wtw_t(model.base.fuel_t, fuels, rules.fueleu.gwp)
    yrange = range(min(2024, st.start), 2051)
    base_cost = {r.year: r.total_eur for r in evaluate(model.profile, scenario, yrange, rules)}
    f_price = {y: {k: prices.fuel_usd_t(k, y, st.price_path) for k in fuels} for y in years}

    memo: dict[frozenset, tuple[np.ndarray, np.ndarray]] = {}

    def value(keyset: frozenset[str]) -> tuple[np.ndarray, np.ndarray]:
        """Operating € per year and t CO2e avoided per year with `keyset` working all the time."""
        if keyset in memo:
            return memo[keyset]
        if not keyset:
            memo[keyset] = (np.zeros(T), np.zeros(T))
            return memo[keyset]
        res = phys.run(keyset)
        state = phys.state(keyset)
        cost = {r.year: r.total_eur for r in evaluate(model.profile, scenario, yrange, rules, lambda _y: state)}
        d_hours = (res.hours_sea - model.base.hours_sea) * scale
        time = -max(d_hours, 0.0) / 24 * daily * time_share
        elec = -res.grid_kwh * prices.electricity_eur_kwh[st.price_path] * scale
        avoided = (base_wtw - _wtw_t(res.fuel_t, fuels, rules.fueleu.gwp) + res.co2_captured_t) * scale
        v = np.empty(T)
        for j, y in enumerate(years):
            fuel = (sum(t * f_price[y][k] for k, t in model.base.fuel_t.items())
                    - sum(t * f_price[y][k] for k, t in res.fuel_t.items())) * usd * scale
            v[j] = fuel + elec + (base_cost[y] - cost[y]) + time
        memo[keyset] = (v, np.full(T, avoided))
        return memo[keyset]

    clash_idx = {(keys.index(a), keys.index(b)) for a, b in clashes if a in keys and b in keys}
    clash_idx |= {(j, i) for i, j in clash_idx}
    singles = []
    total = n + n * (n - 1) // 2
    done = 0
    for k in keys:
        singles.append(value(frozenset([k])))
        done += 1
        if progress:
            progress(done / total)
    u = np.array([s[0] for s in singles]).reshape(n, T)
    e = np.array([s[1] for s in singles]).reshape(n, T)
    pairs, p, f = [], [], []
    scale_v = max(float(np.abs(u).max(initial=0)), 1.0)
    scale_e = max(float(np.abs(e).max(initial=0)), 1e-9)
    for i in range(n):
        for j in range(i + 1, n):
            done += 1
            if (i, j) in clash_idx:
                continue
            v2, e2 = value(frozenset([keys[i], keys[j]]))
            dp, df = v2 - u[i] - u[j], e2 - e[i] - e[j]
            if np.abs(dp).max() > 1e-4 * scale_v or np.abs(df).max() > 1e-4 * scale_e:
                pairs.append((i, j))
                p.append(dp)
                f.append(df)
            if progress:
                progress(done / total)
    # fixed costs of installing i in year s: capex events, residual value, off-hire, opex while working
    K = np.zeros((n, len(install)))
    capex = np.zeros(n)
    for i, k in enumerate(keys):
        m = lib[k]
        c = m.capex_usd(model.power, model.cls, 1 - st.q) * usd
        o = m.opex_usd(model.power, model.cls, 1 - st.q) * usd
        life = max(int(round(m.lifetime.quantile(st.q))), 1)
        off = m.offhire_days.quantile(1 - st.q) * daily
        capex[i] = c
        for si, s in enumerate(install):
            total_cost = 0.0
            for j, y in enumerate(years):
                if y < s:
                    continue
                cash = o
                if (y - s) % life == 0:
                    cash += c
                if y == end:
                    used = (end - s) % life + 1
                    if used < life:
                        cash -= c * (life - used) / life
                if y == s:
                    cash += off
                total_cost += cash * disc[j]
            K[i, si] = total_cost
    return Coefficients(list(keys), years, install, disc, u, e, pairs,
                        np.array(p).reshape(len(pairs), T), np.array(f).reshape(len(pairs), T), K, capex,
                        sorted((i, j) for i, j in clash_idx if i < j), value)


class Model:
    """The MILP of one scenario, built once and solved for several objectives / ε levels.

    Size control: after the last installation year every measure's state is fixed, so the pair terms of
    all later years collapse into one 'tail' period; McCormick inequalities are added only on the side
    the coefficients' signs need; pairs whose interaction is immaterial (< `min_pair` of the largest
    single-measure value) are left to the exact re-appraisal."""

    def __init__(self, c: Coefficients, budget: float | None = None, min_pair: float = 0.01):
        self.c = c
        n, S = len(c.keys), len(c.install_years)
        last = c.install_years[-1]
        # periods: each installation year before the last, then one tail period (all later years)
        self.periods = [[t] for t, y in enumerate(c.years) if y < last] + [[t for t, y in enumerate(c.years) if y >= last]]
        K = len(self.periods)
        self.works = np.array([[1.0 if c.install_years[s] <= c.years[per[0]] else 0.0 for per in self.periods]
                               for s in range(S)])                                   # (S, K)
        big_v = max(float(np.abs((c.u * c.disc).sum(axis=1)).max(initial=0)), 1.0)
        big_e = max(float(np.abs(c.e.sum(axis=1)).max(initial=0)), 1e-9)
        pv = np.array([[float((c.disc[per] * c.p[q, per]).sum()) for per in self.periods] for q in range(len(c.pairs))])
        pf = np.array([[float(c.f[q, per].sum()) for per in self.periods] for q in range(len(c.pairs))])
        keep = [q for q in range(len(c.pairs)) if np.abs(pv[q]).sum() > min_pair * big_v
                or np.abs(pf[q]).sum() > min_pair * big_e]
        self.pairs = [c.pairs[q] for q in keep]
        self.pv, self.pf = pv[keep].reshape(len(keep), K), pf[keep].reshape(len(keep), K)
        P = len(self.pairs)
        self.n, self.S, self.K, self.P = n, S, K, P
        self.nx = n * S
        self.nv = self.nx + P * K
        A = lil_matrix((n + len(c.clashes) + 3 * P * K + (S if budget else 0), self.nv))
        lo, hi = [], []
        r = 0
        for i in range(n):                                     # at most one installation
            for s in range(S):
                A[r, self.xi(i, s)] = 1
            lo.append(0)
            hi.append(1)
            r += 1
        for i, j in c.clashes:                                 # measures that exclude each other
            for s in range(S):
                A[r, self.xi(i, s)] = 1
                A[r, self.xi(j, s)] = 1
            lo.append(0)
            hi.append(1)
            r += 1
        for q, (i, j) in enumerate(self.pairs):                # b = a_i · a_j (McCormick, sign-aware)
            for k in range(K):
                b = self.bi(q, k)
                coeffs = (self.pv[q, k], self.pf[q, k])
                need_upper = any(v > 0 for v in coeffs)        # objective or ε row would push b up
                need_lower = any(v < 0 for v in coeffs)
                if need_upper:
                    for m in (i, j):                           # b − a_m ≤ 0
                        A[r, b] = 1
                        for s in range(S):
                            if self.works[s, k]:
                                A[r, self.xi(m, s)] = -1
                        lo.append(-np.inf)
                        hi.append(0)
                        r += 1
                if need_lower:                                 # b − a_i − a_j ≥ −1
                    A[r, b] = 1
                    for m in (i, j):
                        for s in range(S):
                            if self.works[s, k]:
                                A[r, self.xi(m, s)] = -1
                    lo.append(-1)
                    hi.append(np.inf)
                    r += 1
        if budget:
            for s in range(S):
                for i in range(n):
                    A[r, self.xi(i, s)] = c.capex[i]
                lo.append(0)
                hi.append(budget)
                r += 1
        self.base = LinearConstraint(A.tocsr()[:r], lo, hi)
        self.integrality = np.r_[np.ones(self.nx), np.zeros(self.nv - self.nx)]
        self.bounds = Bounds(np.zeros(self.nv), np.ones(self.nv))
        self.npv_row = np.zeros(self.nv)
        self.cut_row = np.zeros(self.nv)
        works_t = np.array([[1.0 if c.install_years[s] <= y else 0.0 for y in c.years] for s in range(S)])
        for i in range(n):
            for s in range(S):
                w = works_t[s]
                self.npv_row[self.xi(i, s)] = float((c.disc * c.u[i] * w).sum()) - c.K[i, s]
                self.cut_row[self.xi(i, s)] = float((c.e[i] * w).sum())
        for q in range(P):
            for k in range(K):
                self.npv_row[self.bi(q, k)] = self.pv[q, k]
                self.cut_row[self.bi(q, k)] = self.pf[q, k]

    def xi(self, i: int, s: int) -> int:
        return i * self.S + s

    def bi(self, q: int, k: int) -> int:
        return self.nx + q * self.K + k

    def solve(self, objective: str = "npv", min_cut: float | None = None, time_limit: float = 6.0) -> Plan | None:
        cons = [self.base]
        if min_cut is not None:
            cons.append(LinearConstraint(self.cut_row[None, :], [min_cut], [np.inf]))
        row = self.npv_row if objective == "npv" else self.cut_row / max(np.abs(self.cut_row).max(), 1e-9) \
            + 1e-6 * self.npv_row / max(np.abs(self.npv_row).max(), 1e-9)
        res = milp(-row, constraints=cons, integrality=self.integrality, bounds=self.bounds,
                   options={"time_limit": time_limit, "mip_rel_gap": 1e-3})
        if res.x is None:
            return None
        x = np.round(res.x[: self.nx]).reshape(self.n, self.S)
        return Plan.of((self.c.keys[i], self.c.install_years[s]) for i, s in zip(*np.nonzero(x), strict=True))

    def estimate(self, plan: Plan) -> tuple[float, float]:
        """The search's own estimate of a plan (NPV, t CO2e)."""
        v = np.zeros(self.nv)
        yrs = plan.years
        for i, k in enumerate(self.c.keys):
            if k in yrs:
                v[self.xi(i, self.c.install_years.index(yrs[k]))] = 1
        a = v[: self.nx].reshape(self.n, self.S) @ self.works        # (n, K)
        for q, (i, j) in enumerate(self.pairs):
            v[self.nx + q * self.K: self.nx + (q + 1) * self.K] = a[i] * a[j]
        return float(self.npv_row @ v), float(self.cut_row @ v)


def refine(plan: Plan, exact: Callable[[Plan], tuple[float, float]], keys: Sequence[str], install: Sequence[int],
           clashes: set[frozenset], capex: Mapping[str, float], min_cut: float = -np.inf,
           budget: float | None = None, max_evals: int = 160) -> tuple[Plan, float, float]:
    """Exact local search around a plan: add, drop or move one measure while NPV rises and the plan
    still avoids at least `min_cut` tonnes (first improvement; stops after `max_evals` appraisals)."""
    cur = plan
    npv, cut = exact(cur)
    evals = 1

    def ok(p: Plan) -> bool:
        ks = p.keys
        if any(frozenset((a, b)) in clashes for i, a in enumerate(ks) for b in ks[i + 1:]):
            return False
        if budget:
            per: dict[int, float] = {}
            for k, y in p.installs:
                per[y] = per.get(y, 0.0) + capex[k]
            if any(v > budget for v in per.values()):
                return False
        return True

    improved = True
    while improved and evals < max_evals:
        improved = False
        yrs = cur.years
        moves: list[dict[str, int]] = []
        for k in yrs:                                          # drop, or move to a neighbouring year
            moves.append({x: y for x, y in yrs.items() if x != k})
            for dy in (-1, 1, -3, 3):
                y = yrs[k] + dy
                if install[0] <= y <= install[-1]:
                    moves.append({**yrs, k: y})
        for k in keys:                                         # add a measure in the first year
            if k not in yrs:
                moves.append({**yrs, k: install[0]})
        for mv in moves:
            cand = Plan.of(mv)
            if not ok(cand):
                continue
            n2, c2 = exact(cand)
            evals += 1
            if c2 >= min_cut and n2 > npv + 1.0:
                cur, npv, cut, improved = cand, n2, c2, True
                break
            if evals >= max_evals:
                break
    return cur, npv, cut


def pareto(model: ShipModel, lib: Mapping[str, Measure], keys: Sequence[str], scenario: Scenario,
           st: Settings | None = None, rules: Rules | None = None, prices: Prices | None = None,
           points: int = 8, progress: Callable[[float], None] | None = None) -> Front:
    """Highest-NPV plans from 'best NPV' to 'deepest cut', each re-appraised exactly."""
    st = st or Settings()
    rules = rules or Rules.load()
    prices = prices or default_prices()
    phys = SetPhysics(model, lib, st.q, rules)
    clashes = [(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]
               if b in lib[a].excludes or a in lib[b].excludes]

    def coeff_progress(x: float) -> None:
        if progress:
            progress(0.7 * x)

    c = coefficients(model, lib, keys, scenario, st, rules, prices, clashes, coeff_progress, phys)
    m = Model(c, st.budget_eur)
    cache: dict[tuple, Appraisal] = {}

    def appraisal(pl: Plan) -> Appraisal:
        if pl.installs not in cache:
            cache[pl.installs] = appraise_plan(model, lib, pl, scenario, st.q, st.price_path, st.discount, st.end,
                                               rules, prices, first_year=st.start, physics=phys)
        return cache[pl.installs]

    def exact(pl: Plan) -> tuple[float, float]:
        return c.plan_value(pl)

    clash_set = {frozenset(x) for x in clashes}
    capex = dict(zip(c.keys, c.capex, strict=True))
    best = m.solve("npv")
    deep = m.solve("cut")
    found: list[tuple[Plan, float]] = []                      # (plan, ε it must meet exactly)
    if best is not None:
        found.append((best, -np.inf))
    if best is not None and deep is not None:
        lo_e, hi_e = exact(best)[1], exact(deep)[1]
        est_lo, est_hi = m.estimate(best)[1], m.estimate(deep)[1]
        for k in range(1, points - 1):
            share = k / (points - 1)
            pl = m.solve("npv", min_cut=est_lo + (est_hi - est_lo) * share)
            if pl is not None:
                found.append((pl, lo_e + (hi_e - lo_e) * share))
            if progress:
                progress(0.7 + 0.2 * k / points)
    if deep is not None:
        found.append((deep, exact(deep)[1]))
    out: list[PlanResult] = []
    seen = set()
    for pl, eps in found:
        if not pl:
            continue
        fine, _n, _c = refine(pl, exact, c.keys, c.install_years, clash_set, capex, eps, st.budget_eur)
        if fine.installs in seen:
            continue
        seen.add(fine.installs)
        est = m.estimate(pl)
        out.append(PlanResult(fine, est[0], est[1], appraisal(fine)))
    # keep the exact non-dominated plans, ordered by emissions cut
    keep = [r for r in out if not any((o.npv >= r.npv and o.avoided > r.avoided) or
                                      (o.npv > r.npv and o.avoided >= r.avoided) for o in out)]
    keep.sort(key=lambda r: r.avoided)
    span = max((abs(r.npv) for r in keep), default=1.0) or 1.0
    gaps = [abs(r.npv - r.estimate_npv) / span for r in keep]
    if progress:
        progress(1.0)
    return Front(keep, c, {"max_gap": max(gaps, default=0.0), "pairs": len(m.pairs), "appraisals": len(cache)})
