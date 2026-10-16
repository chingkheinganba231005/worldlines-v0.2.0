"""Scenario Lab: how conflict reporting in one country has historically rippled to others.

Model. A vector autoregression over x_c,t = log(1 + conflict events located in
country c on day t) for the most conflict-active countries, with seven lags,
weekday effects and log world event volume as controls (so a global news surge
is not mistaken for contagion), estimated by ridge regression on days whose
whole lag window is clean.

Scenarios. Generalized impulse responses (Pesaran & Shin 1998; invariant to
variable ordering): the expected path of every country after an unexpected
jump in one country's conflict reporting, with 10-90% bands from a wild
residual bootstrap.

Connectedness. Diebold & Yilmaz (2012) spillover index from the generalized
forecast-error variance decomposition, on rolling one-year windows.

Interpretation. These are *predictive* (Granger) relationships in news
coverage, not causal effects of events: shared causes, media attention cycles
and reporting conventions all create such patterns. The UI says so.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .panel import CONFLICT_FAMILIES, Panel
from .stats import weekday_dummies

SCENARIO_VERSION = "ridge-var7-girf-v1"


@dataclass(frozen=True)
class ScenarioConfig:
    countries: int = 30
    lags: int = 7
    horizon: int = 30
    fevd_horizon: int = 10
    bootstrap: int = 200
    rolling_window: int = 365
    seed: int = 20261016
    penalties: tuple[float, ...] = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)
    minnesota: tuple[tuple[float, float], ...] = tuple((lam, kappa) for lam in (3.0, 10.0, 30.0, 100.0, 300.0)
                                                      for kappa in (1.0, 10.0, 100.0, 1000.0, 1e5))


def conflict_series(panel: Panel, clean: np.ndarray, n: int, dev_end: str) -> tuple[list[str], np.ndarray]:
    conflict = panel.c_families[:, :, CONFLICT_FAMILIES].sum(-1)
    dev = np.array([d <= dev_end for d in panel.dates]) & clean
    order = np.argsort(-conflict[dev].mean(0))[:n]
    return [panel.countries[j] for j in order], np.log1p(conflict[:, order])


def design(x: np.ndarray, world: np.ndarray, weekdays: np.ndarray, clean: np.ndarray, lags: int):
    """Rows t whose window t-lags..t is entirely clean. Columns: intercept, weekday(6), log world, lags."""
    T = len(x)
    ok = np.array([t >= lags and clean[t - lags:t + 1].all() for t in range(T)])
    rows = np.flatnonzero(ok)
    exog = np.hstack([np.ones((T, 1)), weekday_dummies(weekdays), np.log(np.maximum(world, 1))[:, None]])
    lagged = np.hstack([x[rows - l] for l in range(1, lags + 1)])
    return rows, np.hstack([exog[rows], lagged]), exog.shape[1]


def ridge_fit(X: np.ndarray, Y: np.ndarray, penalty: float, free: int) -> np.ndarray:
    mu = X[:, free:].mean(0)
    sd = X[:, free:].std(0)
    sd[sd < 1e-9] = 1.0
    Z = np.hstack([X[:, :free], (X[:, free:] - mu) / sd])
    reg = penalty * np.eye(Z.shape[1])
    reg[:free, :free] = 0
    beta_z = np.linalg.solve(Z.T @ Z + reg, Z.T @ Y)
    beta = beta_z.copy()
    beta[free:] = beta_z[free:] / sd[:, None]
    beta[0] -= (mu / sd) @ beta_z[free:]  # centring constant belongs to the intercept (column 0) only
    return beta


def minnesota_fit(X: np.ndarray, Y: np.ndarray, free: int, n: int, lags: int, lam: float, kappa: float) -> np.ndarray:
    """Equation-by-equation ridge with Minnesota-style shrinkage (Litterman 1986).

    On standardized lags, own-lag l of equation i is penalized lam * l and a
    cross-country lag lam * kappa * l. kappa -> infinity recovers univariate AR
    models, so validation can switch cross-country dynamics off where they do not help.
    """
    mu = X[:, free:].mean(0)
    sd = X[:, free:].std(0)
    sd[sd < 1e-9] = 1.0
    Z = np.hstack([X[:, :free], (X[:, free:] - mu) / sd])
    gram = Z.T @ Z
    cross = Z.T @ Y
    lag_of = np.repeat(np.arange(1, lags + 1), n)
    var_of = np.tile(np.arange(n), lags)
    beta = np.zeros((X.shape[1], Y.shape[1]))
    for i in range(Y.shape[1]):
        penalty = np.zeros(X.shape[1])
        penalty[free:] = lam * lag_of * np.where(var_of == i, 1.0, kappa)
        bz = np.linalg.solve(gram + np.diag(penalty), cross[:, i])
        b = bz.copy()
        b[free:] = bz[free:] / sd
        b[0] -= (mu / sd) @ bz[free:]
        beta[:, i] = b
    return beta


def choose_minnesota(X, Y, free, n, lags, grid) -> tuple[tuple[float, float], dict]:
    split = int(len(X) * 0.8)
    errors = {}
    for lam, kappa in grid:
        beta = minnesota_fit(X[:split], Y[:split], free, n, lags, lam, kappa)
        errors[(lam, kappa)] = float(np.mean((Y[split:] - X[split:] @ beta) ** 2))
    return min(errors, key=lambda k: errors[k]), errors


def lag_matrices(beta: np.ndarray, free: int, n: int, lags: int) -> np.ndarray:
    """A[l] (n x n): response of each variable (row) to lag-(l+1) of each variable (column)."""
    return np.stack([beta[free + l * n: free + (l + 1) * n].T for l in range(lags)])


def ma_coefficients(A: np.ndarray, horizon: int) -> np.ndarray:
    lags, n, _ = A.shape
    phi = np.zeros((horizon + 1, n, n))
    phi[0] = np.eye(n)
    for h in range(1, horizon + 1):
        for l in range(1, min(h, lags) + 1):
            phi[h] += A[l - 1] @ phi[h - l]
    return phi


def girf(phi: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Generalized IRF to a +1 log-unit shock in each variable: out[j, h, i] = response of i at h to shock j."""
    scale = sigma / np.diag(sigma)[None, :]          # column j = Sigma e_j / sigma_jj
    return np.einsum("hik,kj->jhi", phi, scale)


def gfevd(phi: np.ndarray, sigma: np.ndarray, horizon: int) -> np.ndarray:
    """Row-normalized generalized forecast error variance decomposition (Diebold-Yilmaz 2012)."""
    n = sigma.shape[0]
    numerator = np.zeros((n, n))
    denominator = np.zeros(n)
    for h in range(horizon):
        ps = phi[h] @ sigma
        numerator += ps ** 2 / np.diag(sigma)[None, :]
        denominator += np.einsum("ij,jk,ik->i", phi[h], sigma, phi[h])
    theta = numerator / denominator[:, None]
    return theta / theta.sum(1, keepdims=True)


def connectedness(theta: np.ndarray) -> dict:
    n = theta.shape[0]
    off = theta - np.diag(np.diag(theta))
    to_others = off.sum(0) * 100
    from_others = off.sum(1) * 100
    return {"total": float(off.sum() / n * 100), "to": to_others, "from": from_others, "net": to_others - from_others}


def choose_penalty(X, Y, free, penalties) -> tuple[float, dict]:
    split = int(len(X) * 0.8)
    errors = {}
    for penalty in penalties:
        beta = ridge_fit(X[:split], Y[:split], penalty, free)
        errors[penalty] = float(np.mean((Y[split:] - X[split:] @ beta) ** 2))
    return min(errors, key=lambda k: errors[k]), errors


def skill(x, world, weekdays, clean, dates, cfg: ScenarioConfig, split_date: str) -> dict:
    """One-step out-of-sample RMSE after `split_date`: VAR vs each country's own-lags AR (same controls)."""
    rows, X, free = design(x, world, weekdays, clean, cfg.lags)
    train = np.array([dates[t] < split_date for t in rows])
    test = ~train
    if test.sum() < 30 or train.sum() < 200:
        return {}
    Y = x[rows]
    n = x.shape[1]
    (lam, kappa), _ = choose_minnesota(X[train], Y[train], free, n, cfg.lags, cfg.minnesota)
    var_pred = X[test] @ minnesota_fit(X[train], Y[train], free, n, cfg.lags, lam, kappa)
    ar_pred = np.zeros_like(var_pred)
    for i in range(n):
        cols = list(range(free)) + [free + l * n + i for l in range(cfg.lags)]
        p_i, _ = choose_penalty(X[train][:, cols], Y[train][:, i:i + 1], free, cfg.penalties)
        ar_pred[:, i] = (X[test][:, cols] @ ridge_fit(X[train][:, cols], Y[train][:, i:i + 1], p_i, free))[:, 0]
    rmse_var = np.sqrt(np.mean((Y[test] - var_pred) ** 2, axis=0))
    rmse_ar = np.sqrt(np.mean((Y[test] - ar_pred) ** 2, axis=0))
    return {"split": split_date, "test_days": int(test.sum()), "rmse_var": rmse_var, "rmse_ar": rmse_ar,
            "improvement_pct": 100 * (1 - rmse_var / rmse_ar), "mean_improvement_pct": float(np.mean(100 * (1 - rmse_var / rmse_ar))),
            "lambda": lam, "kappa": kappa}


def build_scenarios(panel: Panel, clean: np.ndarray, *, dev_end: str = "2023-12-31", cfg: ScenarioConfig = ScenarioConfig(),
                    skill_split: str = "2026-01-01") -> dict:
    countries, x = conflict_series(panel, clean, cfg.countries, dev_end)
    n = len(countries)
    world = panel.total
    rows, X, free = design(x, world, panel.weekdays, clean, cfg.lags)
    Y = x[rows]
    (lam, kappa), validation = choose_minnesota(X, Y, free, n, cfg.lags, cfg.minnesota)
    beta = minnesota_fit(X, Y, free, n, cfg.lags, lam, kappa)
    fitted = X @ beta
    resid = Y - fitted
    sigma = np.cov(resid, rowvar=False)
    A = lag_matrices(beta, free, n, cfg.lags)
    phi = ma_coefficients(A, cfg.horizon)
    point = girf(phi, sigma)
    rng = np.random.default_rng(cfg.seed)
    draws = np.empty((cfg.bootstrap,) + point.shape)
    for b in range(cfg.bootstrap):
        flips = rng.choice([-1.0, 1.0], size=(len(resid), 1))  # wild (Rademacher) residual bootstrap, fixed design
        Yb = fitted + resid * flips
        beta_b = minnesota_fit(X, Yb, free, n, cfg.lags, lam, kappa)
        resid_b = Yb - X @ beta_b
        draws[b] = girf(ma_coefficients(lag_matrices(beta_b, free, n, cfg.lags), cfg.horizon), np.cov(resid_b, rowvar=False))
    bands = np.quantile(draws, [0.1, 0.5, 0.9], axis=0)
    theta = gfevd(phi, sigma, cfg.fevd_horizon)
    conn = connectedness(theta)
    rolling = []
    month_starts = sorted({d[:7] for d in panel.dates})
    for month in month_starts:
        end_index = max(i for i, d in enumerate(panel.dates) if d[:7] == month)
        window = (rows <= end_index) & (rows > end_index - cfg.rolling_window)
        if window.sum() < 0.8 * cfg.rolling_window:
            continue
        beta_w = minnesota_fit(X[window], Y[window], free, n, cfg.lags, lam, kappa)
        sigma_w = np.cov(Y[window] - X[window] @ beta_w, rowvar=False)
        phi_w = ma_coefficients(lag_matrices(beta_w, free, n, cfg.lags), cfg.fevd_horizon)
        rolling.append({"month": month, "total": connectedness(gfevd(phi_w, sigma_w, cfg.fevd_horizon))["total"]})
    return {"version": SCENARIO_VERSION, "countries": countries, "lags": cfg.lags, "horizon": cfg.horizon,
            "lambda": lam, "kappa": kappa, "validation_mse": {f"{a:g}/{b:g}": v for (a, b), v in validation.items()},
            "observations": int(len(rows)),
            "fit_period": [panel.dates[rows[0]], panel.dates[rows[-1]]],
            "girf": point, "bands": bands, "fevd": theta, "connectedness": conn, "rolling_connectedness": rolling,
            "skill": skill(x, world, panel.weekdays, clean, panel.dates, cfg, skill_split),
            "recent_level": x[np.flatnonzero(clean)[-28:]].mean(0)}
