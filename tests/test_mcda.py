"""Weighting and ranking methods against textbook properties, and SMAA against the scalar engine."""
import numpy as np
import pytest

from navigator.engine import economics as EC
from navigator.engine import library as L
from navigator.engine import measures as M
from navigator.engine import reference as R
from navigator.engine.compliance import Rules, Scenario
from navigator.engine.mcda import criteria as C
from navigator.engine.mcda import ranking as RK
from navigator.engine.mcda import smaa as S
from navigator.engine.mcda import weights as W
from navigator.engine.models import YearSeries

RULES = Rules.load()


def test_ahp_saaty_example():
    r = W.ahp([[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]])
    assert r.weights == pytest.approx([0.637, 0.258, 0.105], abs=0.002)
    assert r.consistency == pytest.approx(0.033, abs=0.003) and r.acceptable
    m = W.ahp_matrix(3, {(0, 1): 3, (0, 2): 5, (1, 2): 3})
    assert m[2, 0] == pytest.approx(0.2)


def test_bwm_recovers_consistent_weights():
    w = np.array([0.5, 0.25, 0.15, 0.10])
    a_b = list(w[0] / w)
    a_w = list(w / w[3])
    r = W.bwm(0, 3, a_b, a_w)
    assert r.weights == pytest.approx(w, abs=1e-6) and r.xi == pytest.approx(0, abs=1e-9)
    assert r.consistency == pytest.approx(0, abs=1e-9) and r.acceptable
    # inconsistent judgements: ξ > 0 and the input-based CR flags them
    bad = W.bwm(0, 3, [1, 9, 9, 9], [9, 9, 1, 1])     # criterion 1 both far below best and far above worst
    assert bad.xi > 0 and not bad.acceptable
    assert W.bwm_threshold(9, 5) == pytest.approx(0.2960) and W.bwm_threshold(4, 7) == pytest.approx(0.2457)


def test_data_weights():
    x = np.array([[1.0, 5, 3], [2.0, 5, 1], [3.0, 5, 2]])
    e = W.entropy(x, np.array([True, True, True]))
    assert e.weights.sum() == pytest.approx(1) and e.weights[1] == pytest.approx(0, abs=1e-6)
    c = W.critic(x, np.array([True, True, False]))
    assert c.weights.sum() == pytest.approx(1) and c.weights[1] == pytest.approx(0, abs=1e-9)


def test_rankings_respect_dominance():
    # alt 0 dominates, alt 2 is dominated; criteria: max, min, max
    x = np.array([[10, 1, 5], [8, 2, 4], [6, 3, 3]], float)
    w = np.array([0.5, 0.3, 0.2])
    mx = np.array([True, False, True])
    for r in RK.rank_all(x, w, mx).values():
        assert list(r.rank) == [1, 2, 3], r.method
    p = RK.promethee(x, w, mx)
    assert p.score.sum() == pytest.approx(0, abs=1e-12)
    v = RK.vikor(x, w, mx)
    assert v.details["Q"][0] == pytest.approx(0) and v.details["advantage"] and v.details["stability"]
    t = RK.topsis(np.array([[1, 0], [0, 1]], float), np.array([0.5, 0.5]), np.array([True, True]))
    assert t.score == pytest.approx([0.5, 0.5])
    mean, cons, corr = RK.consensus(RK.rank_all(x, w, mx))
    assert list(cons) == [1, 2, 3] and corr == pytest.approx(np.ones((4, 4)))


def test_criteria_tree_weights():
    fam = {"money": 0.4, "climate": 0.3, "technology": 0.1, "operations": 0.1, "regulation": 0.1}
    w = C.global_weights(fam, {"money": {"npv": 0.75, "capex": 0.25}})
    k = list(C.KEYS)
    assert w.sum() == pytest.approx(1)
    assert w[k.index("npv")] == pytest.approx(0.3) and w[k.index("cut")] == pytest.approx(0.3)
    assert w[k.index("safety")] == pytest.approx(0.025)


@pytest.fixture(scope="module")
def sim():
    lib = M.load()
    model = M.model_for(L.profile(R.by_key("bulk:60000-99999"), "deep_sea"))
    keys = ["hull_coating", "rotor_sails", "biofuel_b100", "slow_steaming", "carbon_capture"]
    sc = Scenario(eua=YearSeries(RULES.markets.eua_paths["central"]), view="ww")
    st = C.Settings(2027, 20, "central", 0.08)
    return S.Simulator(model, {k: (lib[k],) for k in keys}, sc, st, RULES), lib, model, sc, st


def test_vectorised_npv_equals_scalar_engine(sim):
    s, lib, model, sc, st = sim
    d = S.Draws.likely(list(s.alts), 3, model, sc, RULES, EC.default_prices(), st)
    for k in s.alts:
        scalar = EC.appraise(model, [lib[k]], sc, st.start, 0.5, "central", 0.08, end=st.end, rules=RULES).npv
        assert s.npv(k, d)["npv"] == pytest.approx(np.full(3, scalar), rel=1e-9, abs=1.0), k


def test_smaa_outputs_are_probabilities(sim):
    s, *_ = sim
    w = C.global_weights({f: 0.2 for f in C.FAMILIES}, {})
    r = S.run(s, True, w, n=2000)
    assert r.acceptability.shape == (6, 6)
    assert r.acceptability.sum(axis=0) == pytest.approx(np.ones(6))
    assert r.acceptability.sum(axis=1) == pytest.approx(np.ones(6))
    assert ((r.confidence >= 0) & (r.confidence <= 1)).all()
    # common random numbers: the same seed gives the same result
    assert S.run(s, True, w, n=2000).acceptability == pytest.approx(r.acceptability)
    # inputs vary across draws, but not when uncertainty is switched off
    assert r.values["npv"][:, 0].std() > 0
    fixed = S.run(s, True, w, n=500, uncertain_inputs=False)
    assert fixed.values["npv"][:, 0].std() == pytest.approx(0, abs=1e-6)
