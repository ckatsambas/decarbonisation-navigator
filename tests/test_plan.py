"""Timed plans: exact appraisal and the MILP planner."""
import pytest

from navigator.engine import economics as EC
from navigator.engine import library as L
from navigator.engine import measures as M
from navigator.engine import plan as P
from navigator.engine import reference as R
from navigator.engine.compliance import Rules, Scenario
from navigator.engine.models import YearSeries

RULES = Rules.load()


@pytest.fixture(scope="module")
def ship():
    lib = M.load()
    model = M.model_for(L.profile(R.by_key("bulk:60000-99999"), "deep_sea"))
    sc = Scenario(eua=YearSeries(RULES.markets.eua_paths["central"]), view="ww")
    return lib, model, sc


def test_plan_installed_together_equals_appraise(ship):
    lib, model, sc = ship
    keys = ["hull_coating", "rotor_sails", "propulsion_devices"]
    a = EC.appraise(model, [lib[k] for k in keys], sc, 2027, 0.5, "central", 0.08, rules=RULES)
    b = P.appraise_plan(model, {k: lib[k] for k in lib_keys(lib)}, P.Plan.of({k: 2027 for k in keys}), sc, 0.5,
                        "central", 0.08, rules=RULES)
    assert b.npv == pytest.approx(a.npv, rel=1e-9, abs=1.0)
    assert b.co2e_avoided == pytest.approx(a.co2e_avoided, rel=1e-9)
    assert [f.net for f in b.flows] == pytest.approx([f.net for f in a.flows], rel=1e-9, abs=1e-6)


def test_staggered_plan_switches_in_its_year(ship):
    lib, model, sc = ship
    libd = {k: lib[k] for k in lib_keys(lib)}
    plan = P.Plan.of({"hull_coating": 2027, "rotor_sails": 2030})
    a = P.appraise_plan(model, libd, plan, sc, rules=RULES)
    flows = {f.year: f for f in a.flows}
    assert flows[2030].capex < flows[2029].capex <= 0           # rotor sails paid in 2030
    assert flows[2030].fuel > flows[2029].fuel                  # and saving from then on
    assert plan.active(2029) == frozenset({"hull_coating"})
    # a later start is worth less than installing the same measure earlier when it pays back
    early = P.appraise_plan(model, libd, P.Plan.of({"hull_coating": 2027}), sc, rules=RULES, first_year=2027)
    late = P.appraise_plan(model, libd, P.Plan.of({"hull_coating": 2031}), sc, rules=RULES, first_year=2027)
    assert (early.npv > late.npv) == (early.npv > 0)


def lib_keys(lib):
    return [m.key for m in lib]


KEYS = ["hull_coating", "propulsion_devices", "rotor_sails", "biofuel_blend", "biofuel_b100", "slow_steaming",
        "carbon_capture", "weather_routing"]


@pytest.fixture(scope="module")
def front(ship):
    from navigator.engine import optimise as O
    lib, model, sc = ship
    libd = {k: lib[k] for k in lib_keys(lib)}
    return O.pareto(model, libd, KEYS, sc, O.Settings(start=2027, window=6), RULES, points=6), libd


def test_pareto_front_is_exact_and_non_dominated(ship, front):
    from navigator.engine import optimise as O
    lib, model, sc = ship
    fr, libd = front
    assert len(fr.plans) >= 2
    npv = [r.npv for r in fr.plans]
    cut = [r.avoided for r in fr.plans]
    assert cut == sorted(cut) and npv == sorted(npv, reverse=True)       # more cut costs NPV
    for r in fr.plans:
        again = P.appraise_plan(model, libd, r.plan, sc, 0.5, "central", 0.08, rules=RULES, first_year=2027)
        assert again.npv == pytest.approx(r.npv, rel=1e-9)
        fast = fr.coefficients.plan_value(r.plan)
        assert fast[0] == pytest.approx(r.npv, rel=0.02, abs=2e4)        # per-set values agree with the engine
        assert fast[1] == pytest.approx(r.avoided, rel=1e-6)
        ks = r.plan.keys
        assert not ("biofuel_blend" in ks and "biofuel_b100" in ks)       # variants exclude each other
        assert all(2027 <= y <= 2032 for _, y in r.plan.installs)
    # the search's pair model is exact for single measures and for pairs
    c = fr.coefficients
    m = O.Model(c, min_pair=0.0)
    for pl in (P.Plan.of({"hull_coating": 2028}), P.Plan.of({"hull_coating": 2027, "rotor_sails": 2029})):
        assert m.estimate(pl)[0] == pytest.approx(c.plan_value(pl)[0], rel=1e-6, abs=1.0)


def test_budget_limits_each_year(ship):
    from navigator.engine import optimise as O
    lib, model, sc = ship
    libd = {k: lib[k] for k in lib_keys(lib)}
    budget = 1.5e6
    fr = O.pareto(model, libd, KEYS, sc, O.Settings(start=2027, window=6, budget_eur=budget), RULES, points=4)
    for r in fr.plans:
        per = {}
        for k, y in r.plan.installs:
            per[y] = per.get(y, 0) + libd[k].capex_usd(model.power, model.cls, 0.5) * RULES.nzf.eur_per_usd
        assert max(per.values()) <= budget * 1.0001


def test_adaptive_plan_shares_the_first_stage(ship):
    from navigator.engine import optimise as O
    lib, model, sc = ship
    libd = {k: lib[k] for k in lib_keys(lib)}
    ad = O.adaptive(model, libd, KEYS[:6], sc, O.Settings(start=2027, window=6), RULES, decide_after=2028)
    assert len(ad.branches) == 9 and sum(b.prob for b in ad.branches) == pytest.approx(1)
    for b in ad.branches:
        assert Plan_now(b.plan, 2028) == ad.now.installs
    assert ad.value_of_flexibility >= -1e-6 * max(abs(ad.expected_rigid), 1)


def Plan_now(plan, year):
    return tuple((k, y) for k, y in plan.installs if y <= year)


def test_smaa_prices_a_timed_plan_like_the_scalar_engine(ship):
    import numpy as np

    from navigator.engine.mcda import criteria as C
    from navigator.engine.mcda import smaa as S
    lib, model, sc = ship
    libd = {k: lib[k] for k in lib_keys(lib)}
    plan = P.Plan.of({"hull_coating": 2027, "rotor_sails": 2029, "biofuel_blend": 2031})
    st = C.Settings(2027, 20, "central", 0.08)
    sim = S.Simulator(model, {"plan": tuple(libd[k] for k in plan.keys)}, sc, st, RULES, install={"plan": plan.years})
    d = S.Draws.likely(["plan"], 2, model, sc, RULES, EC.default_prices(), st)
    out = sim.npv("plan", d)
    a = P.appraise_plan(model, libd, plan, sc, 0.5, "central", 0.08, end=st.end, rules=RULES, first_year=2027)
    assert out["npv"] == pytest.approx(np.full(2, a.npv), rel=1e-6, abs=5.0)
    assert out["avoided"] == pytest.approx(np.full(2, a.co2e_avoided), rel=1e-6)
    alt = C.plan_alternative(model, libd, plan, sc, st, RULES, "plan")
    assert alt.values["npv"] == pytest.approx(a.npv) and 0 < alt.values["cut"] < 1
    assert out["cut"] == pytest.approx(np.full(2, alt.values["cut"]), rel=1e-6)
