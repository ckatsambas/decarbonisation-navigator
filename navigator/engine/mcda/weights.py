"""Criteria weights (decision 0010-2).

- Best-Worst Method, linear model (Rezaei 2015, 2016): the decision maker names the most and the least
  important criterion and compares the best with every other one (a_Bj, 1–9) and every other one with
  the worst (a_jW). Weights minimise ξ subject to |w_B − a_Bj w_j| ≤ ξ and |w_j − a_jW w_W| ≤ ξ.
  Consistency: ξ itself, and the input-based ratio of Liang, Brunelli & Rezaei (2020),
  CR_I = max_j |a_Bj · a_jW − a_BW| / (a_BW² − a_BW), with their acceptance thresholds.
- AHP (Saaty 1980): principal eigenvector of the pairwise matrix, CR = CI / RI.
- Entropy and CRITIC: data-driven weights from the decision matrix (for comparison only).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

# Saaty's random index by matrix size
RI = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
# Liang, Brunelli & Rezaei (2020), Omega 96, Table 3: thresholds of the input-based CR,
# rows = number of criteria n (3..9), columns = a_BW (3..9)
_BWM_THRESHOLD = {3: (0.1667, 0.1667, 0.1667, 0.1667, 0.1667, 0.1667, 0.1667),
                  4: (0.1121, 0.1529, 0.1898, 0.2206, 0.2527, 0.2577, 0.2683),
                  5: (0.1354, 0.1994, 0.2306, 0.2546, 0.2716, 0.2844, 0.2960),
                  6: (0.1330, 0.1990, 0.2643, 0.3044, 0.3144, 0.3221, 0.3262),
                  7: (0.1294, 0.2457, 0.2819, 0.3029, 0.3144, 0.3251, 0.3403),
                  8: (0.1309, 0.2521, 0.2958, 0.3154, 0.3408, 0.3620, 0.3657),
                  9: (0.1359, 0.2681, 0.3062, 0.3337, 0.3517, 0.3620, 0.3662)}


@dataclass(frozen=True)
class WeightResult:
    weights: np.ndarray
    method: str
    consistency: float          # BWM: input-based CR; AHP: CR; data methods: 0
    threshold: float            # acceptable if consistency ≤ threshold
    xi: float = 0.0             # BWM: optimal ξ

    @property
    def acceptable(self) -> bool:
        return self.consistency <= self.threshold + 1e-12


def bwm_threshold(a_bw: float, n: int) -> float:
    """Acceptance threshold for the input-based CR (scales below 3 and n < 3 are always acceptable)."""
    if a_bw < 3 or n < 3:
        return 1.0
    return _BWM_THRESHOLD[min(n, 9)][min(int(round(a_bw)), 9) - 3]


def bwm(best: int, worst: int, best_to_others: list[float], others_to_worst: list[float]) -> WeightResult:
    """Linear BWM. `best_to_others[j]` = a_Bj, `others_to_worst[j]` = a_jW (a_BB = a_WW = 1)."""
    a_b = np.asarray(best_to_others, dtype=float)
    a_w = np.asarray(others_to_worst, dtype=float)
    n = len(a_b)
    if n == 1:
        return WeightResult(np.array([1.0]), "bwm", 0.0, 1.0)
    if n == 2:
        a = a_b[worst] if best != worst else 1.0
        w = np.array([0.0, 0.0])
        w[best], w[worst] = a / (1 + a), 1 / (1 + a)
        return WeightResult(w, "bwm", 0.0, 1.0)
    # variables: w_0..w_{n-1}, xi ; minimise xi
    c = np.zeros(n + 1)
    c[-1] = 1.0
    rows, rhs = [], []
    for j in range(n):
        for sign in (1, -1):
            r = np.zeros(n + 1)
            r[best] += sign
            r[j] -= sign * a_b[j]
            r[-1] = -1
            rows.append(r)
            rhs.append(0.0)
            r = np.zeros(n + 1)
            r[j] += sign
            r[worst] -= sign * a_w[j]
            r[-1] = -1
            rows.append(r)
            rhs.append(0.0)
    eq = np.zeros((1, n + 1))
    eq[0, :n] = 1
    res = linprog(c, A_ub=np.array(rows), b_ub=np.array(rhs), A_eq=eq, b_eq=[1.0],
                  bounds=[(0, None)] * (n + 1), method="highs")
    w = res.x[:n]
    a_bw = a_b[worst]
    cr = 0.0
    if a_bw > 1:
        cr = float(max(abs(a_b[j] * a_w[j] - a_bw) for j in range(n)) / (a_bw * a_bw - a_bw))
    return WeightResult(w / w.sum(), "bwm", cr, bwm_threshold(a_bw, n), float(res.x[-1]))


def ahp(matrix: np.ndarray | list[list[float]]) -> WeightResult:
    """Principal-eigenvector weights and Saaty's consistency ratio (acceptable ≤ 0.10)."""
    a = np.asarray(matrix, dtype=float)
    n = a.shape[0]
    vals, vecs = np.linalg.eig(a)
    k = int(np.argmax(vals.real))
    w = np.abs(vecs[:, k].real)
    w = w / w.sum()
    lam = float(vals[k].real)
    ci = (lam - n) / (n - 1) if n > 2 else 0.0
    cr = ci / RI[n] if RI.get(n) else 0.0
    return WeightResult(w, "ahp", max(cr, 0.0), 0.10)


def ahp_matrix(n: int, judgements: dict[tuple[int, int], float]) -> np.ndarray:
    """Reciprocal matrix from upper-triangle judgements {(i, j): a_ij}."""
    a = np.ones((n, n))
    for (i, j), v in judgements.items():
        a[i, j], a[j, i] = v, 1.0 / v
    return a


def _benefit_normalised(x: np.ndarray, maximise: np.ndarray) -> np.ndarray:
    lo, hi = x.min(axis=0), x.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)
    z = (x - lo) / span
    return np.where(maximise, z, 1 - z)


def entropy(x: np.ndarray, maximise: np.ndarray) -> WeightResult:
    """Shannon entropy weights: criteria whose values differ more across alternatives weigh more."""
    z = _benefit_normalised(np.asarray(x, float), np.asarray(maximise, bool)) + 1e-9
    p = z / z.sum(axis=0)
    m = x.shape[0]
    e = -(p * np.log(p)).sum(axis=0) / np.log(m) if m > 1 else np.ones(x.shape[1])
    d = 1 - e
    w = d / d.sum() if d.sum() > 0 else np.full(x.shape[1], 1 / x.shape[1])
    return WeightResult(w, "entropy", 0.0, 1.0)


def critic(x: np.ndarray, maximise: np.ndarray) -> WeightResult:
    """CRITIC (Diakoulaki et al. 1995): contrast (standard deviation) × conflict (1 − correlation)."""
    z = _benefit_normalised(np.asarray(x, float), np.asarray(maximise, bool))
    sd = z.std(axis=0, ddof=1) if z.shape[0] > 1 else np.zeros(z.shape[1])
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.corrcoef(z, rowvar=False)
    r = np.nan_to_num(np.atleast_2d(r), nan=0.0)
    c = sd * (1 - r).sum(axis=0)
    w = c / c.sum() if c.sum() > 0 else np.full(x.shape[1], 1 / x.shape[1])
    return WeightResult(w, "critic", 0.0, 1.0)
