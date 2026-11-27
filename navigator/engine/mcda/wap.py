"""Weights Assessment through Prioritizations, WAP (Tsotsolas, Spyridakos, Siskos & Salmon 2019,
Operational Research 19:135–150), decision 0016.

The decision maker only (1) puts the criteria in order of importance, ties allowed, and (2) says for
every pair of consecutive classes a *range* [z_min, z_max] for "the upper class matters z times as much
as the lower one". The weights consistent with those answers form a polyhedron:

    p_i = p_k                       for i, k in the same class
    z_min,r · p_low ≤ p_up ≤ z_max,r · p_low     between class r and r + 1
    Σ p = 1,  p ≥ 0

There is nothing to contradict, so no consistency check is needed. Following Siskos & Tsotsolas (2015,
EJOR 246:543–553) the robustness of the answers is measured on the 2n solutions of "min p_i" and
"max p_i": the range μ_i = max − min of each weight and the Average Stability Index (ASI, Grigoroudis &
Siskos 2010; 1 = a single weight vector, 0 = no information). The working weights are the barycentre
of those 2n vectors. For SMAA the polyhedron itself is sampled uniformly by hit-and-run (their rule 4,
Tervonen et al. 2013), so the spread of the weights comes from the company's own answers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog

from .weights import WeightResult

# Verbal answers between two consecutive classes and the z range each one starts from (refined by the
# range slider). "same" is a tie and puts both items in one class.
LEVELS: dict[str, tuple[float, float]] = {
    "little": (1.1, 1.5),
    "clearly": (1.5, 2.0),
    "much": (2.0, 3.0),
    "very": (3.0, 5.0),
}
Z_MAX = 6.0                     # top of the range slider
ASI_GOOD, ASI_FAIR = 0.95, 0.90  # labels for the stability badge


@dataclass(frozen=True)
class WapResult(WeightResult):
    lo: np.ndarray = field(default_factory=lambda: np.zeros(0))     # min of each weight on the polyhedron
    hi: np.ndarray = field(default_factory=lambda: np.zeros(0))     # max of each weight
    asi: float = 1.0
    classes: tuple[tuple[int, ...], ...] = ()
    z: tuple[tuple[float, float], ...] = ()

    @property
    def mu(self) -> np.ndarray:
        return self.hi - self.lo

    @property
    def z_total(self) -> tuple[float, float]:
        """Most / least important class ratio, the z of the revised Simos method."""
        return float(np.prod([a for a, _ in self.z])) if self.z else 1.0, \
            float(np.prod([b for _, b in self.z])) if self.z else 1.0

    @property
    def stability(self) -> str:
        return "good" if self.asi >= ASI_GOOD else "fair" if self.asi >= ASI_FAIR else "wide"


def classes_from_order(order: list[int], gaps: list[str | None]) -> list[list[int]]:
    """Items in order of importance and the answer between each consecutive pair (None = tie)."""
    out = [[order[0]]] if order else []
    for item, g in zip(order[1:], gaps, strict=True):
        if g is None:
            out[-1].append(item)
        else:
            out.append([item])
    return out


GAP_LEVELS = tuple(LEVELS)        # empty rows between two classes → word: 0 little, 1 clearly, 2 much, 3+ very


def from_rows(rows: list[int]) -> tuple[list[list[int]], list[tuple[float, float]]]:
    """Classes and z ranges from the row of each item on the ladder (row 0 = most important).

    Items on the same row tie; the number of empty rows between two classes says how much more the
    upper class matters (Simos' white cards, read as WAP ranges).
    """
    used = sorted(set(rows))
    classes = [[i for i, r in enumerate(rows) if r == u] for u in used]
    z = [LEVELS[GAP_LEVELS[min(b - a - 1, len(GAP_LEVELS) - 1)]] for a, b in zip(used, used[1:], strict=False)]
    return classes, z


def _system(n: int, classes: list[list[int]], z: list[tuple[float, float]]):
    """A_ub p ≤ b_ub and A_eq p = b_eq over the n weights."""
    if sorted(i for c in classes for i in c) != list(range(n)):
        raise ValueError("every item must be in exactly one class")
    if len(z) != len(classes) - 1:
        raise ValueError("one z range per pair of consecutive classes")
    a_eq, b_eq, a_ub, b_ub = [np.ones(n)], [1.0], [], []
    for c in classes:
        for k in c[1:]:
            r = np.zeros(n)
            r[c[0]], r[k] = 1, -1
            a_eq.append(r)
            b_eq.append(0.0)
    for (zmin, zmax), up, low in zip(z, classes[:-1], classes[1:], strict=True):
        if not 1.0 <= zmin <= zmax:
            raise ValueError("need 1 ≤ z_min ≤ z_max")
        i, k = up[0], low[0]
        r = np.zeros(n)
        r[i], r[k] = -1, zmin              # z_min p_k − p_i ≤ 0
        a_ub.append(r)
        r = np.zeros(n)
        r[i], r[k] = 1, -zmax              # p_i − z_max p_k ≤ 0
        a_ub.append(r)
        b_ub += [0.0, 0.0]
    return (np.array(a_ub) if a_ub else None, np.array(b_ub) if b_ub else None,
            np.array(a_eq), np.array(b_eq))


def asi(vectors: np.ndarray) -> float:
    """Average Stability Index of m weight vectors (rows) over n criteria (Grigoroudis & Siskos 2010)."""
    v = np.asarray(vectors, float)
    m, n = v.shape
    if n < 2 or m < 2:
        return 1.0
    spread = np.sqrt(np.maximum(m * (v ** 2).sum(axis=0) - v.sum(axis=0) ** 2, 0.0))
    return float(1 - spread.sum() / n / (m / n * np.sqrt(n - 1)))


def wap(n: int, classes: list[list[int]], z: list[tuple[float, float]]) -> WapResult:
    """Weight ranges, barycentre and ASI from a ranking in classes (most important first)."""
    a_ub, b_ub, a_eq, b_eq = _system(n, classes, z)
    sols = []
    for i in range(n):
        for sign in (1.0, -1.0):
            c = np.zeros(n)
            c[i] = sign
            res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=[(0, None)] * n, method="highs")
            sols.append(np.clip(res.x, 0, None))
    v = np.array(sols)
    bary = v.mean(axis=0)
    bary = bary / bary.sum()
    return WapResult(bary, "wap", 0.0, 1.0, lo=v.min(axis=0), hi=v.max(axis=0), asi=asi(v),
                     classes=tuple(tuple(c) for c in classes), z=tuple((float(a), float(b)) for a, b in z))


def sample(r: WapResult, k: int, seed: int, steps: int | None = None) -> np.ndarray:
    """k weight vectors uniform on the WAP polyhedron (hit-and-run, k independent chains).

    The chains move in the space of class weights q (one per class) on Σ size·q = 1, which maps linearly
    onto the weights, so uniform there is uniform on the polyhedron. A class pair with z_min = z_max is an
    equality and is folded in before sampling.
    """
    n = len(r.weights)
    classes = [list(c) for c in r.classes]
    m = len(classes)
    if m <= 1:
        return np.tile(r.weights, (k, 1))
    rng = np.random.default_rng(seed + 11)
    size = np.array([len(c) for c in classes], float)
    eq, ub = [size], []
    eq_b = [1.0]
    for j, (zmin, zmax) in enumerate(r.z):
        if zmax - zmin < 1e-9:
            row = np.zeros(m)
            row[j], row[j + 1] = 1, -zmin
            eq.append(row)
            eq_b.append(0.0)
            continue
        row = np.zeros(m)
        row[j], row[j + 1] = -1, zmin
        ub.append(row)
        row = np.zeros(m)
        row[j], row[j + 1] = 1, -zmax
        ub.append(row)
    g = np.vstack([*ub, -np.eye(m)])                 # q ≥ 0 as well
    h = np.zeros(len(g))
    e = np.array(eq)
    # start: barycentre in class space, a strictly interior point when the ranges have width
    q0 = np.array([r.weights[c[0]] for c in classes])
    _u, s, vt = np.linalg.svd(e)
    rank = int((s > 1e-12).sum())
    basis = vt[rank:].T                              # (m, d) null space of the equalities
    d = basis.shape[1]
    if d == 0:
        q = np.tile(q0, (k, 1))
    else:
        steps = steps or 30 + 15 * d
        q = np.tile(q0, (k, 1))
        gb = g @ basis                                # (G, d)
        for _ in range(steps):
            u = rng.standard_normal((k, d))
            u /= np.linalg.norm(u, axis=1, keepdims=True)
            dirs = u @ gb.T                           # (k, G): rate of change of each constraint
            slack = h[None, :] - q @ g.T              # (k, G) ≥ 0
            with np.errstate(divide="ignore", invalid="ignore"):
                t = slack / dirs
            t_hi = np.where(dirs > 1e-12, t, np.inf).min(axis=1)
            t_lo = np.where(dirs < -1e-12, t, -np.inf).max(axis=1)
            t_hi, t_lo = np.maximum(t_hi, 0), np.minimum(t_lo, 0)
            step = t_lo + (t_hi - t_lo) * rng.random(k)
            q = q + step[:, None] * (u @ basis.T)
    q = np.clip(q, 0, None)
    w = np.zeros((k, n))
    for j, c in enumerate(classes):
        w[:, c] = q[:, [j]]
    return w / w.sum(axis=1, keepdims=True)
