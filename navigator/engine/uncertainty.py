"""Uncertain quantities: minimum / most likely / maximum, sampled with a PERT distribution.

Every estimated input in the application (ship size, EU share of activity, technology costs in
Phase 3, ...) is an `Estimate`. The deterministic screens use its most likely value; the SMAA in
Phase 4 samples it. See docs/decisions/0007 (decision 3).

PERT (modified beta, λ = 4):
    α = 1 + λ (m − a)/(b − a),   β = 1 + λ (b − m)/(b − a),   X = a + (b − a)·Beta(α, β)
    mean = (a + λ m + b)/(λ + 2)

`Sampler` provides *common random numbers*: every named quantity gets its own stream of uniform
numbers, so that all alternatives evaluated in the same SMAA run see the same draw of, say, the
ship's EU share. Differences between alternatives then reflect the alternatives, not noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.stats import beta as _beta

LAMBDA = 4.0


@dataclass(frozen=True)
class Estimate:
    low: float
    likely: float
    high: float
    method: str = ""              # how it was obtained (shown in "Read more")
    source: str = ""              # source id or short citation
    details: dict = field(default_factory=dict, compare=False)

    def __post_init__(self):
        if not (self.low <= self.likely <= self.high):
            raise ValueError(f"Estimate needs low ≤ likely ≤ high, got {self.low}, {self.likely}, {self.high}")

    @classmethod
    def exact(cls, value: float, method: str = "reported", source: str = "") -> Estimate:
        return cls(value, value, value, method, source)

    @property
    def is_exact(self) -> bool:
        return self.low == self.high

    @property
    def mean(self) -> float:
        return (self.low + LAMBDA * self.likely + self.high) / (LAMBDA + 2)

    def _ab(self) -> tuple[float, float]:
        span = self.high - self.low
        return 1 + LAMBDA * (self.likely - self.low) / span, 1 + LAMBDA * (self.high - self.likely) / span

    def from_uniform(self, u: np.ndarray | float) -> np.ndarray | float:
        """Inverse-CDF transform: the same uniform draw always maps to the same quantile."""
        if self.is_exact:
            return np.full_like(np.asarray(u, dtype=float), self.likely) if np.ndim(u) else self.likely
        a, b = self._ab()
        return self.low + (self.high - self.low) * _beta.ppf(u, a, b)

    def quantile(self, q: float) -> float:
        return float(self.from_uniform(q))

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        return np.asarray(self.from_uniform(rng.random(n)))

    def scaled(self, factor: float) -> Estimate:
        lo, mid, hi = sorted((self.low * factor, self.likely * factor, self.high * factor))
        return Estimate(lo, mid, hi, self.method, self.source, self.details)

    def clipped(self, lo: float, hi: float) -> Estimate:
        c = lambda x: min(max(x, lo), hi)  # noqa: E731
        return Estimate(c(self.low), c(self.likely), c(self.high), self.method, self.source, self.details)


class Sampler:
    """Seeded uniform streams per named quantity (common random numbers across alternatives)."""

    def __init__(self, n: int, seed: int = 20261204):
        self.n = n
        self.seed = seed
        self._streams: dict[str, np.ndarray] = {}

    def uniform(self, name: str) -> np.ndarray:
        if name not in self._streams:
            # independent, reproducible stream per name
            key = np.frombuffer(name.encode("utf-8"), dtype=np.uint8).astype(np.uint64).sum()
            rng = np.random.default_rng([self.seed, int(key), len(name)])
            self._streams[name] = rng.random(self.n)
        return self._streams[name]

    def draw(self, name: str, est: Estimate) -> np.ndarray:
        return np.asarray(est.from_uniform(self.uniform(name)), dtype=float)
