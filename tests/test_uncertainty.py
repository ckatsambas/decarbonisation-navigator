import numpy as np
import pytest

from navigator.engine.uncertainty import Estimate, Sampler


def test_pert_moments_and_bounds():
    e = Estimate(10, 20, 60)
    assert e.mean == pytest.approx((10 + 4 * 20 + 60) / 6)
    x = e.sample(np.random.default_rng(1), 200_000)
    assert x.min() >= 10 and x.max() <= 60
    assert x.mean() == pytest.approx(e.mean, rel=0.01)
    assert e.quantile(0.0) == pytest.approx(10) and e.quantile(1.0) == pytest.approx(60)


def test_exact_and_invalid():
    e = Estimate.exact(5.0)
    assert e.is_exact and e.mean == 5 and e.quantile(0.3) == 5
    with pytest.raises(ValueError):
        Estimate(3, 1, 4)


def test_common_random_numbers():
    s = Sampler(1000, seed=7)
    a = s.draw("eu_share", Estimate(0.2, 0.4, 0.7))
    b = s.draw("eu_share", Estimate(0.2, 0.4, 0.7))
    c = s.draw("eua_2030", Estimate(0.2, 0.4, 0.7))
    assert np.array_equal(a, b)                         # same quantity → same draws for every alternative
    assert not np.array_equal(a, c)                     # different quantities → independent streams
    assert np.array_equal(Sampler(1000, seed=7).uniform("x"), Sampler(1000, seed=7).uniform("x"))


def test_scaled_and_clipped():
    e = Estimate(1, 2, 3).scaled(-1)
    assert (e.low, e.likely, e.high) == (-3, -2, -1)
    assert Estimate(0.5, 0.9, 1.4).clipped(0, 1).high == 1
