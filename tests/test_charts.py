"""Every chart paints its first state, morphs to a second one with animations on, and settles there."""
import numpy as np
import pytest

pytest.importorskip("pytestqt")

from navigator.engine.mcda import criteria as C
from navigator.engine.mcda import ranking as RK
from navigator.ui import anim
from navigator.ui.charts import BarChart, CashFlowChart, HBarChart, Morph, StackedBarChart, Switchable, nice_range
from navigator.ui.donut import Donut3D
from navigator.ui.fan import FanChart
from navigator.ui.maps import PriorityMap, RankBubbles
from navigator.ui.radar import ProfileRadar, WeightRadar
from navigator.ui.surface3d import Surface3D

RNG = np.random.default_rng(5)
YEARS = list(range(2027, 2047))


def test_morph_and_axis_helpers():
    m = Morph()
    m.set([1.0, 2.0], 1.0)
    assert m.at(0.0) == pytest.approx([0, 0]) and m.at(1.0) == pytest.approx([1, 2])
    m.set([3.0, 4.0], 0.5)               # from what is shown halfway
    assert m.at(0.0) == pytest.approx([0.5, 1]) and m.at(1.0) == pytest.approx([3, 4])
    lo, hi, ticks = nice_range(-1.3e6, 2.2e6)
    assert lo <= -1.3e6 and hi >= 2.2e6 and 0.0 in ticks


def weights():
    return C.global_weights({f: 0.2 for f in C.FAMILIES}, {})


def scores(x):
    def at(a, b):
        return C.split_weights(weights(), "money", "climate", a, b)
    return RK.affine_scores(x, C.MAXIMISE, at), RK.winner_regions(x, C.MAXIMISE, at)


def feed(kind, w, k):
    """Data set k (0 or 1) for chart kind."""
    if kind == "stacked":
        w.set_data(YEARS, [("a", list(RNG.uniform(0, 1e6, 20)), "#2F6FA8"), ("b", list(RNG.uniform(0, 1e6, 20)), "#2A9D8F")],
                   ("t", list(RNG.uniform(0, 2e6, 20)), "#A36A00"))
    elif kind == "bar":
        w.set_data(YEARS, list(RNG.uniform(0, 1e6, 20)), "#2F6FA8")
    elif kind == "cash":
        w.set_data(YEARS, list(RNG.normal(0, 1e5, 20)), ("flow", "total"))
    elif kind == "hbar":
        w.set_data([f"c{i}" for i in range(9)], [("", list(RNG.dirichlet(np.ones(9))), "#0F6E78")])
    elif kind == "donut":
        w.set_data([(n, RNG.uniform(1, 5), c, "") for n, c in (("a", "#D23B2E"), ("b", "#4C8DB8"), ("c", "#9AA5AE"))])
    elif kind == "fan":
        w.set_data(YEARS, np.cumsum(RNG.normal(0, 1e5, (60, 20)), axis=1), RNG.normal(0, 1e6, 500),
                   {"gain": "g", "loss": "l", "median": "m {v}", "today": "t", "best": "b", "worst": "w"})
    elif kind == "bubbles":
        m = RNG.dirichlet(np.ones(4), 4)
        w.set_data(list("abcd"), m, m @ np.arange(1, 5), 0, 3, ("{r}", "E", "rec", "ref"))
    elif kind == "profiles":
        w.set_data(list("abcdefghi"), list("abcdefghi"), ["#888888"] * 9,
                   [(n, RNG.random(9), "#D23B2E", n == "a", None) for n in "abc"])
    elif kind == "radar":
        cloud = RNG.dirichlet(np.ones(9) * 20, 120)
        w.set_data(list("abcdefghi"), ["money"] * 9, ["#888888"] * 9, weights(), cloud, RNG.random(120) > 0.3,
                   ("you", "holds", "flips"))
    elif kind in ("map", "surface"):
        x = RNG.random((4, len(C.KEYS)))
        (s0, sa, sb), regions = scores(x)
        names, colors = list("abcd"), ["#D23B2E", "#4C8DB8", "#4FA88A", "#9AA5AE"]
        if kind == "map":
            w.set_data(regions, names, colors, (0.4, 0.3), RNG.random((50, 2)) * 0.5, ("x", "y"), "you")
        else:
            w.set_data(s0, sa, sb, 0, colors, names, regions, (0.4, 0.3), ("x", "y"), ("you", "above", "below"))


KINDS = {"stacked": lambda: StackedBarChart("money"), "bar": BarChart, "cash": CashFlowChart, "hbar": HBarChart,
         "donut": Donut3D, "fan": FanChart, "bubbles": RankBubbles, "profiles": ProfileRadar,
         "radar": WeightRadar, "map": PriorityMap, "surface": Surface3D}


@pytest.mark.parametrize("kind", list(KINDS))
def test_chart_morphs_and_settles(qtbot, kind):
    anim.set_enabled(True)
    try:
        w = KINDS[kind]()
        qtbot.addWidget(w)
        w.resize(900, 460)
        w.show()
        feed(kind, w, 0)
        qtbot.wait(60)
        w.grab()                         # a frame in the middle of the first transition
        feed(kind, w, 1)
        qtbot.wait(60)
        w.grab()
        qtbot.waitUntil(lambda: w._t >= 1.0, timeout=3000)
        assert not w.grab().isNull()
    finally:
        anim.set_enabled(False)


def test_switchable_keeps_chips_in_a_gutter(qtbot):
    a, b = HBarChart(), Donut3D()
    sw = Switchable([("1", "first", a), ("2", "second", b)])
    qtbot.addWidget(sw)
    sw.resize(600, 300)
    sw.show()
    sw.buttons[1].click()
    assert sw.index() == 1 and sw.buttons[1].isChecked() and not sw.buttons[0].isChecked()
    assert all(btn.x() >= sw.stack.geometry().right() for btn in sw.buttons)
