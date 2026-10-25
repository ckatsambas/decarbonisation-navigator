"""Ranking methods (decision 0010-3): SAW, TOPSIS, PROMETHEE II, VIKOR and a consensus view.

All take a decision matrix x (alternatives × criteria), weights w (sum 1) and a boolean vector telling
which criteria are maximised. Each returns a score (higher = better, except VIKOR's Q where lower is
better) and the rank (1 = best).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import rankdata, spearmanr

METHODS = ("saw", "topsis", "promethee", "vikor")


@dataclass(frozen=True)
class Ranking:
    method: str
    score: np.ndarray
    rank: np.ndarray            # 1 = best
    details: dict


def _ranks(score: np.ndarray, higher_is_better: bool = True) -> np.ndarray:
    return rankdata(-score if higher_is_better else score, method="min").astype(int)


def minmax(x: np.ndarray, maximise: np.ndarray) -> np.ndarray:
    lo, hi = x.min(axis=0), x.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)
    z = (x - lo) / span
    z = np.where(hi > lo, z, 1.0)          # a criterion on which all are equal does not discriminate
    return np.where(maximise, z, 1 - z)


def saw(x, w, maximise) -> Ranking:
    x, w, mx = np.asarray(x, float), np.asarray(w, float), np.asarray(maximise, bool)
    s = minmax(x, mx) @ w
    return Ranking("saw", s, _ranks(s), {})


def topsis(x, w, maximise) -> Ranking:
    """Hwang & Yoon (1981): vector normalisation, distance to ideal and anti-ideal solutions."""
    x, w, mx = np.asarray(x, float), np.asarray(w, float), np.asarray(maximise, bool)
    norm = np.sqrt((x ** 2).sum(axis=0))
    v = x / np.where(norm > 0, norm, 1.0) * w
    ideal = np.where(mx, v.max(axis=0), v.min(axis=0))
    anti = np.where(mx, v.min(axis=0), v.max(axis=0))
    dp = np.sqrt(((v - ideal) ** 2).sum(axis=1))
    dm = np.sqrt(((v - anti) ** 2).sum(axis=1))
    c = np.where(dp + dm > 0, dm / (dp + dm), 0.0)
    return Ranking("topsis", c, _ranks(c), {"d_plus": dp, "d_minus": dm})


def promethee(x, w, maximise) -> Ranking:
    """PROMETHEE II (Brans & Vincke 1985) with the linear (V-shape) preference function, p = the
    criterion's range across the alternatives (no indifference threshold)."""
    x, w, mx = np.asarray(x, float), np.asarray(w, float), np.asarray(maximise, bool)
    m = x.shape[0]
    d = x[:, None, :] - x[None, :, :]                     # a − b per criterion
    d = np.where(mx, d, -d)
    p = x.max(axis=0) - x.min(axis=0)
    pref = np.clip(d / np.where(p > 0, p, 1.0), 0, 1)
    pi = (pref * w).sum(axis=2)                           # π(a, b)
    plus = pi.sum(axis=1) / (m - 1) if m > 1 else np.zeros(m)
    minus = pi.sum(axis=0) / (m - 1) if m > 1 else np.zeros(m)
    net = plus - minus
    return Ranking("promethee", net, _ranks(net), {"phi_plus": plus, "phi_minus": minus})


def vikor(x, w, maximise, v: float = 0.5) -> Ranking:
    """VIKOR (Opricovic & Tzeng 2004): group utility S, individual regret R, compromise index Q."""
    x, w, mx = np.asarray(x, float), np.asarray(w, float), np.asarray(maximise, bool)
    best = np.where(mx, x.max(axis=0), x.min(axis=0))
    worst = np.where(mx, x.min(axis=0), x.max(axis=0))
    span = np.where(best != worst, best - worst, 1.0)
    g = w * (best - x) / span
    g = np.where(best != worst, g, 0.0)
    s, r = g.sum(axis=1), g.max(axis=1)

    def scale(a):
        return (a - a.min()) / (a.max() - a.min()) if a.max() > a.min() else np.zeros_like(a)

    q = v * scale(s) + (1 - v) * scale(r)
    rank = _ranks(q, higher_is_better=False)
    # compromise conditions: acceptable advantage and acceptable stability
    order = np.argsort(q, kind="stable")
    m = len(q)
    dq = 1 / (m - 1) if m > 1 else 0
    c1 = m > 1 and q[order[1]] - q[order[0]] >= dq
    c2 = m > 0 and (np.argmin(s) == order[0] or np.argmin(r) == order[0])
    return Ranking("vikor", -q, rank, {"S": s, "R": r, "Q": q, "advantage": bool(c1), "stability": bool(c2)})


def rank_all(x, w, maximise) -> dict[str, Ranking]:
    return {"saw": saw(x, w, maximise), "topsis": topsis(x, w, maximise),
            "promethee": promethee(x, w, maximise), "vikor": vikor(x, w, maximise)}


def consensus(rankings: dict[str, Ranking]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(mean rank, consensus rank, Spearman correlation matrix between the methods)."""
    rs = np.array([r.rank for r in rankings.values()], dtype=float)
    mean = rs.mean(axis=0)
    k = len(rs)
    corr = np.ones((k, k))
    for i in range(k):
        for j in range(i + 1, k):
            c = spearmanr(rs[i], rs[j]).statistic if rs.shape[1] > 2 else 1.0
            corr[i, j] = corr[j, i] = 1.0 if np.isnan(c) else c
    return mean, rankdata(mean, method="min").astype(int), corr
