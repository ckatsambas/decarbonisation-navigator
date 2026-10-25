"""Criteria tree and decision matrix (decision 0010-1).

Five families, nine criteria. Each alternative is a shortlisted measure (or "do nothing"), and its
values come from the Phase 3 engine at the most likely inputs. SMAA (mcda.smaa) samples the same
quantities over their ranges.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

import numpy as np

from .. import economics as EC
from .. import power as PW
from ..compliance import Rules, Scenario
from ..measures import Measure, ShipModel

FAMILIES = ("money", "climate", "technology", "operations", "regulation")


@dataclass(frozen=True)
class Criterion:
    key: str
    family: str
    maximise: bool
    unit: str                # eur | share | trl | days | score


CRITERIA = (
    Criterion("npv", "money", True, "eur"),
    Criterion("capex", "money", False, "eur"),
    Criterion("cut", "climate", True, "share"),
    Criterion("trl", "technology", True, "trl"),
    Criterion("offhire", "operations", False, "days"),
    Criterion("cargo", "operations", False, "share"),
    Criterion("availability", "operations", True, "score"),
    Criterion("safety", "operations", True, "score"),
    Criterion("nzf_exposure", "regulation", False, "eur"),
)
KEYS = tuple(c.key for c in CRITERIA)
MAXIMISE = np.array([c.maximise for c in CRITERIA])
DO_NOTHING = "do_nothing"


def members(family: str) -> list[Criterion]:
    return [c for c in CRITERIA if c.family == family]


def global_weights(family_w: dict[str, float], local_w: dict[str, dict[str, float]]) -> np.ndarray:
    """Family weight × weight within the family (a single-criterion family gets 1)."""
    out = []
    for c in CRITERIA:
        fam = members(c.family)
        lw = 1.0 if len(fam) == 1 else local_w.get(c.family, {}).get(c.key, 1 / len(fam))
        out.append(family_w.get(c.family, 1 / len(FAMILIES)) * lw)
    w = np.array(out)
    return w / w.sum()


@dataclass(frozen=True)
class Alternative:
    key: str
    measures: tuple[Measure, ...]
    values: dict[str, float]
    appraisal: EC.Appraisal | None = None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Settings:
    start: int = 2027
    life: int = 20
    prices: str = "central"
    rate: float = 0.08

    @property
    def end(self) -> int:
        return min(self.start + self.life - 1, 2050)


def wtw_cut(model: ShipModel, measures: Iterable[Measure], rules: Rules, q: float = 0.5) -> float:
    ms = list(measures)
    eff = PW.Effects.combine(*(m.effects(model.power, model.cls, q) for m in ms))
    res = PW.run(model.power, eff, fuels=rules.fuels)
    base = EC._wtw_t(model.base.fuel_t, rules.fuels, rules.fueleu.gwp)
    new = EC._wtw_t(res.fuel_t, rules.fuels, rules.fueleu.gwp) - res.co2_captured_t
    return 1 - new / base if base > 0 else 0.0


def do_nothing() -> Alternative:
    return Alternative(DO_NOTHING, (), {"npv": 0.0, "capex": 0.0, "cut": 0.0, "trl": 9, "offhire": 0.0, "cargo": 0.0,
                                        "availability": 5, "safety": 5, "nzf_exposure": 0.0})


def alternative(model: ShipModel, measures: Iterable[Measure], scenario: Scenario, st: Settings,
                rules: Rules, key: str | None = None) -> Alternative:
    ms = tuple(measures)
    kw = dict(start=st.start, q=0.5, price_path=st.prices, discount=st.rate, end=st.end, rules=rules)
    a = EC.appraise(model, ms, scenario, **kw)
    as_drafted = EC.appraise(model, ms, replace(scenario, nzf="as_drafted"), **kw).npv
    not_adopted = EC.appraise(model, ms, replace(scenario, nzf="not_adopted"), **kw).npv
    vals = {
        "npv": a.npv, "capex": a.capex_eur, "cut": wtw_cut(model, ms, rules),
        "trl": min(m.attributes.get("trl", 9) for m in ms),
        "offhire": sum(m.offhire_days.quantile(0.5) for m in ms),
        "cargo": sum(m.attributes.get("cargo_loss", 0.0) for m in ms),
        "availability": min(m.attributes.get("availability", 5) for m in ms), "safety": min(m.attributes.get("safety", 5) for m in ms),
        "nzf_exposure": abs(as_drafted - not_adopted),
    }
    return Alternative(key or "+".join(m.key for m in ms), ms, vals, a)


def matrix(alts: list[Alternative]) -> np.ndarray:
    return np.array([[a.values[k] for k in KEYS] for a in alts], dtype=float)
