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
from navigator.engine.mcda import wap as WAP
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


def test_selftest_entry_point():
    from navigator.__main__ import selftest
    assert selftest() == 0


def test_priority_map_helpers():
    fam = {"money": 0.4, "climate": 0.3, "technology": 0.1, "operations": 0.1, "regulation": 0.1}
    base = C.global_weights(fam, {"money": {"npv": 0.75, "capex": 0.25}})
    w = C.split_weights(base, "money", "climate", 0.2, 0.5)
    s = C.family_sums(w)
    assert w.sum() == pytest.approx(1) and s["money"] == pytest.approx(0.2) and s["climate"] == pytest.approx(0.5)
    k = list(C.KEYS)
    assert w[k.index("npv")] / w[k.index("capex")] == pytest.approx(3)        # internal split kept
    assert s["technology"] == pytest.approx(0.1) and s["regulation"] == pytest.approx(0.1)  # 0.3 left, equal shares
    # the company's own point reproduces its weights
    assert C.split_weights(base, "money", "climate", 0.4, 0.3) == pytest.approx(base)
    # two options, each best on one criterion: the winner follows the larger weight
    x = np.array([[1.0, 0.0], [0.0, 1.0]])
    grid = RK.winner_map(x, np.array([True, True]), lambda a, b: np.array([a, b]), n=10)
    assert grid[9, 0] == 0 and grid[0, 9] == 1 and grid[9, 9] == -1


def test_winner_regions_match_the_grid():
    fam = {"money": 0.4, "climate": 0.3, "technology": 0.1, "operations": 0.1, "regulation": 0.1}
    base = C.global_weights(fam, {"money": {"npv": 0.75, "capex": 0.25}})
    rng = np.random.default_rng(3)
    x = rng.uniform(0, 1, (5, len(C.KEYS)))

    def at(a, b):
        return C.split_weights(base, "money", "climate", a, b)

    regions = RK.winner_regions(x, C.MAXIMISE, at)
    assert sum(RK.polygon_area(p) for p in regions) == pytest.approx(0.5, abs=1e-9)
    grid = RK.winner_map(x, C.MAXIMISE, at, n=40)
    shares = [(grid == i).sum() / (grid >= 0).sum() for i in range(5)]
    assert [RK.polygon_area(p) / 0.5 for p in regions] == pytest.approx(shares, abs=0.04)


def test_smaa_keeps_paths_that_end_at_the_npv(sim):
    s, *_ = sim
    r = S.run(s, True, C.global_weights({f: 0.2 for f in C.FAMILIES}, {}), n=600)
    k = r.keys[0]
    paths = r.details["paths"][k]
    assert paths.shape == (S.FAN_PATHS, len(r.details["years"]))
    assert paths[:, -1] == pytest.approx(r.values["npv"][: S.FAN_PATHS, 0], rel=1e-4, abs=50)
    assert r.details["winner"].shape == (600,)


# ------------------------------------------------------------------ WAP (decision 0016)
PAPER_CLASSES = [[0], [1, 4], [2], [3]]                 # crit1 > {crit2, crit5} > crit3 > crit4
PAPER_Z = [(1.1978, 1.4096), (1.8169, 1.9851), (2.5088, 2.7037)]


def test_wap_reproduces_the_paper_example():
    """Tsotsolas et al. (2019), Table 3: min, max, barycentre and μ of every weight."""
    r = WAP.wap(5, PAPER_CLASSES, PAPER_Z)
    assert r.lo == pytest.approx([0.3019, 0.2393, 0.1224, 0.0454, 0.2393], abs=1e-4)
    assert r.hi == pytest.approx([0.3438, 0.2572, 0.1393, 0.0553, 0.2572], abs=1e-4)
    assert r.weights == pytest.approx([0.3228, 0.2481, 0.1307, 0.0503, 0.2481], abs=1e-4)
    assert r.mu.mean() == pytest.approx(0.02086, abs=1e-4)
    assert r.z_total == pytest.approx((5.4599, 7.5655), abs=1e-3)      # the z of revised Simos
    assert r.acceptable                                                 # nothing can contradict


def test_wap_feedback_narrows_the_polyhedron():
    """Table 10: z_max,1 from 1.41 to 1.22 shrinks the ranges and raises the ASI."""
    wide = WAP.wap(5, PAPER_CLASSES, PAPER_Z)
    narrow = WAP.wap(5, PAPER_CLASSES, [(1.1978, 1.22), *PAPER_Z[1:]])
    assert narrow.lo == pytest.approx([0.3019, 0.2505, 0.1283, 0.0476, 0.2505], abs=3e-4)
    assert narrow.hi == pytest.approx([0.3124, 0.2572, 0.1393, 0.0553, 0.2572], abs=5e-4)
    assert narrow.asi > wide.asi and (narrow.mu <= wide.mu + 1e-12).all()


def test_wap_asi_bounds_and_ties():
    assert WAP.asi(np.tile([0.5, 0.3, 0.2], (6, 1))) == pytest.approx(1.0)
    assert WAP.asi(np.eye(4)) == pytest.approx(0.0)
    tie = WAP.wap(3, [[0, 1, 2]], [])
    assert tie.weights == pytest.approx([1 / 3] * 3) and tie.asi == pytest.approx(1.0)
    exact = WAP.wap(2, [[1], [0]], [(3.0, 3.0)])
    assert exact.weights == pytest.approx([0.25, 0.75])
    with pytest.raises(ValueError):
        WAP.wap(2, [[0], [1]], [(2.0, 1.5)])
    assert WAP.classes_from_order([2, 0, 1, 3], [None, "much", None]) == [[2, 0], [1, 3]]


def test_wap_sampler_stays_inside_and_covers_the_polyhedron():
    r = WAP.wap(5, PAPER_CLASSES, PAPER_Z)
    s = WAP.sample(r, 4000, seed=3)
    assert s.sum(axis=1) == pytest.approx(np.ones(len(s)))
    assert (s >= r.lo - 1e-9).all() and (s <= r.hi + 1e-9).all()
    assert s[:, 1] == pytest.approx(s[:, 4])
    ratio = s[:, 0] / s[:, 1]
    assert ratio.min() >= 1.1978 - 1e-9 and ratio.max() <= 1.4096 + 1e-9
    assert ratio.min() < 1.22 and ratio.max() > 1.38                     # reaches both ends
    assert s.mean(axis=0) == pytest.approx(r.weights, abs=3e-3)
    fixed = WAP.sample(WAP.wap(3, [[0], [1], [2]], [(2.0, 2.0), (1.5, 2.5)]), 500, seed=1)
    assert fixed[:, 0] / fixed[:, 1] == pytest.approx(np.full(500, 2.0))
