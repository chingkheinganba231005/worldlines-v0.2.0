"""Statistical primitives. Pure functions, no I/O; every fit uses only data passed in.

Ported from v0.1 (unchanged semantics): probability, jsd, js_contributions,
transport, ilr, inverse_ilr, smoothed_counts, fit_ridge, shrinkage_covariance.
New in v0.2: conformal p-values, Cauchy combination, Benjamini-Hochberg,
weekday-aware design matrices, generalized impulse responses helpers.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
from scipy.linalg import helmert
from scipy.optimize import linprog
from scipy.special import softmax


# ---------------------------------------------------------------- distributions
def probability(values: Any) -> np.ndarray:
    p = np.asarray(values, dtype=float)
    if p.ndim != 1 or len(p) < 2 or not np.all(np.isfinite(p)) or np.any(p < 0) or p.sum() <= 0:
        raise ValueError("A finite, nonnegative, nonempty distribution with at least two bins is required")
    return p / p.sum()


def smoothed_counts(counts: Any, alpha: float = 0.5) -> np.ndarray:
    c = np.asarray(counts, dtype=float)
    probability(c)  # an empty window has no distribution; never impute a uniform one
    if alpha <= 0:
        raise ValueError("Positive smoothing required")
    return probability(c + alpha)


def jsd(p: Any, q: Any) -> float:
    """Jensen-Shannon divergence in nats, range [0, ln 2]."""
    p, q = probability(p), probability(q)
    if p.shape != q.shape:
        raise ValueError("Distribution dimensions differ")
    return float(max(0.0, js_contributions(p, q).sum()))


def js_contributions(p: Any, q: Any) -> np.ndarray:
    """Per-category terms that sum exactly to JSD(p, q)."""
    p, q = probability(p), probability(q)
    m = (p + q) / 2
    result = np.zeros_like(p)
    for r in (p, q):
        mask = r > 0
        result[mask] += 0.5 * r[mask] * np.log(r[mask] / m[mask])
    return result


def transport(p: Any, q: Any, cost: Any) -> float:
    """Exact optimal transport cost (earth mover's distance) by linear programming."""
    p, q, c = probability(p), probability(q), np.asarray(cost, dtype=float)
    n, m = len(p), len(q)
    if c.shape != (n, m) or not np.all(np.isfinite(c)) or np.any(c < 0):
        raise ValueError("Invalid nonnegative transport cost matrix")
    if n == m and np.array_equal(p, q) and np.all(np.diag(c) == 0):
        return 0.0
    a = np.zeros((n + m, n * m))
    for i in range(n):
        a[i, i * m:(i + 1) * m] = 1
    for j in range(m):
        a[n + j, j::m] = 1
    result = linprog(c.ravel(), A_eq=a[:-1], b_eq=np.r_[p, q][:-1], bounds=(0, None), method="highs")
    if not result.success:
        raise ArithmeticError(f"OT solver failed: {result.message}")
    return max(0.0, float(result.fun))


def ilr(p: Any) -> np.ndarray:
    p = probability(p)
    if np.any(p <= 0):
        raise ValueError("Smooth zero counts before ILR transformation")
    return helmert(len(p), full=False) @ np.log(p)


def inverse_ilr(z: Any) -> np.ndarray:
    z = np.asarray(z, dtype=float)
    return softmax(helmert(len(z) + 1, full=False).T @ z)


def ilr_matrix(shares: np.ndarray) -> np.ndarray:
    """Row-wise ILR of strictly positive compositions (T x K -> T x K-1)."""
    shares = np.asarray(shares, dtype=float)
    return np.log(shares) @ helmert(shares.shape[1], full=False).T


# ---------------------------------------------------------------- regression
def fit_ridge(x: np.ndarray, y: np.ndarray, penalty: float, unpenalized: int = 1) -> np.ndarray:
    """Ridge regression; the first `unpenalized` columns (intercept, weekday effects) are not shrunk."""
    reg = np.eye(x.shape[1]) * penalty
    reg[:unpenalized, :unpenalized] = 0
    return np.linalg.solve(x.T @ x + reg, x.T @ y)


def shrinkage_covariance(residuals: np.ndarray, floor: float, weight: float = 0.8) -> np.ndarray:
    cov = np.atleast_2d(np.cov(np.asarray(residuals), rowvar=False))
    d = cov.shape[0]
    target = np.eye(d) * max(float(np.trace(cov)) / d, floor)
    return weight * cov + (1 - weight) * target + floor * np.eye(d)


def weekday_dummies(weekdays: Sequence[int]) -> np.ndarray:
    """Six effect-coded columns (Monday..Saturday vs Sunday) so the intercept stays an average day."""
    out = np.zeros((len(weekdays), 6))
    for row, wd in enumerate(weekdays):
        if wd == 6:
            out[row, :] = -1.0
        else:
            out[row, wd] = 1.0
    return out


# ---------------------------------------------------------------- calibration
def conformal_pvalue(score: float, calibration: Sequence[float]) -> float | None:
    """Split-conformal tail p-value: (1 + #{s_i >= score}) / (n + 1).

    Exact (super-uniform) under exchangeability of the calibration scores and the
    new score. News time series are serially dependent and drift, so on real data
    this is an approximation whose calibration we *measure* (research/results.md).
    """
    values = np.asarray([v for v in calibration if v is not None and math.isfinite(v)], dtype=float)
    if not len(values) or score is None or not math.isfinite(score):
        return None
    return float((1 + np.sum(values >= score)) / (len(values) + 1))


def gpd_pwm(exceedances: np.ndarray) -> tuple[float, float] | None:
    """Generalized Pareto (shape xi, scale sigma) by probability-weighted moments (Hosking & Wallis 1987).

    `exceedances` must be sorted ascending and nonnegative. Shape is clamped to
    [-0.5, 0.5]: heavier tails are not identifiable from a year of daily data.
    """
    k = len(exceedances)
    if k < 3:
        return None
    a0 = float(exceedances.mean())
    a1 = float(np.mean(exceedances * (k - 1 - np.arange(k)) / (k - 1)))
    denominator = a0 - 2 * a1
    if a0 <= 0 or denominator <= 0:
        return None
    xi = -(a0 / denominator - 2)
    sigma = 2 * a0 * a1 / denominator
    if sigma <= 0 or not math.isfinite(sigma):
        return None
    return float(min(0.5, max(-0.5, xi))), float(sigma)


def tail_pvalue(score: float | None, prior: Sequence[float], *, tail_fraction: float = 0.1, min_exceed: int = 20,
                floor: float = 1e-6) -> float | None:
    """Upper-tail p-value of `score` against earlier scores: conformal in the body, GPD in the tail.

    Below the (1 - tail_fraction) quantile the split-conformal estimate is used
    as is. Above it, a peaks-over-threshold generalized Pareto fit extrapolates,
    which is what allows return periods longer than the calibration window.
    Calibration on real data is measured, not assumed (research/results.md).
    """
    if score is None or not math.isfinite(score):
        return None
    x = np.sort(np.asarray([v for v in prior if v is not None and math.isfinite(v)], dtype=float))
    n = len(x)
    if n == 0:
        return None
    conformal = float((1 + n - np.searchsorted(x, score, side="left")) / (n + 1))
    k = int(n * tail_fraction)
    if k < min_exceed:
        return conformal
    threshold = x[n - k - 1]
    if score <= threshold:
        return conformal
    fit = gpd_pwm(x[n - k:] - threshold)
    if fit is None:
        return conformal
    xi, sigma = fit
    excess = (score - threshold) / sigma
    if abs(xi) < 1e-6:
        survival = math.exp(-excess)
    else:
        base = 1 + xi * excess
        survival = 0.0 if base <= 0 else base ** (-1 / xi)
    return float(max(floor, min(1.0, (k / (n + 1)) * survival)))


def cauchy_combination(pvalues: Sequence[float | None], weights: Sequence[float] | None = None) -> float | None:
    """Cauchy combination test (Liu & Xie 2020, JASA): valid under arbitrary dependence in the tail.

    T = sum w_i tan((0.5 - p_i) pi);  p = 0.5 - arctan(T / sum w) / pi.
    """
    pairs = [(p, 1.0 if weights is None else w) for p, w in zip(pvalues, weights or [1.0] * len(pvalues)) if p is not None]
    if not pairs:
        return None
    total_weight = sum(w for _, w in pairs)
    statistic = 0.0
    for p, w in pairs:
        p = min(max(p, 1e-15), 1 - 1e-15)
        if p < 1e-12:  # tan diverges; use the asymptotic form 1 / (p pi)
            statistic += w / (p * math.pi)
        else:
            statistic += w * math.tan((0.5 - p) * math.pi)
    statistic /= total_weight
    if statistic > 1e12:
        return min(1.0, 1 / (statistic * math.pi))
    return float(min(1.0, max(0.0, 0.5 - math.atan(statistic) / math.pi)))


def benjamini_hochberg(pvalues: dict[str, float], q: float) -> set[str]:
    """Keys rejected by the BH step-up procedure at false discovery rate q (positive dependence: PRDS)."""
    items = sorted(((p, k) for k, p in pvalues.items() if p is not None), key=lambda t: t[0])
    m = len(items)
    cutoff = 0
    for rank, (p, _) in enumerate(items, 1):
        if p <= q * rank / m:
            cutoff = rank
    return {k for _, k in items[:cutoff]}


def robust_z(value: float, history: Sequence[float], min_scale: float = 1e-6) -> float | None:
    """(value - median) / (1.4826 * MAD) of a trailing history."""
    h = np.asarray([v for v in history if v is not None and math.isfinite(v)], dtype=float)
    if len(h) < 5:
        return None
    med = float(np.median(h))
    mad = float(np.median(np.abs(h - med))) * 1.4826
    return (value - med) / max(mad, min_scale, 0.05 * abs(med) if med else min_scale)


def percentile_of(value: float, history: Sequence[float]) -> float | None:
    h = np.asarray([v for v in history if v is not None and math.isfinite(v)], dtype=float)
    if not len(h):
        return None
    return float(100.0 * (np.sum(h < value) + 0.5 * np.sum(h == value)) / len(h))


def logit_pvalue_to_unusualness(p: float | None) -> float | None:
    """Display transform: -log10(p), capped. 2 = '1 in 100 days', 3 = '1 in 1,000 days'."""
    if p is None:
        return None
    return float(min(6.0, -math.log10(max(p, 1e-6))))
