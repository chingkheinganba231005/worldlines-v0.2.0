"""Prequential monitoring of the world's event record.

For every day t and every monitored country, a forecast is made from days
strictly before t, the observation is scored against it, and the score is
ranked against the same country's earlier scores. Nothing at or after t enters
the forecast, its covariance, or its calibration. See docs/methods.md.

Channels (per country):
  attention  log share of world coverage located in the country (upper tail)
  mix        7-family event composition, ILR with overdispersed-multinomial covariance
  conflict   logit share of coercion + violence events (upper tail)
Combined by the Cauchy combination test into a single p-value; reported to
people as a return period ("a 1-in-N-days event for this country").
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.linalg import helmert

from .panel import CONFLICT_FAMILIES, Panel
from .reference import FAMILIES
from .stats import (benjamini_hochberg, cauchy_combination, fit_ridge, jsd, js_contributions, smoothed_counts,
                    tail_pvalue, weekday_dummies)

MODEL_VERSION = "worldline-monitor-2.0"


@dataclass(frozen=True)
class Config:
    train_days: int = 365          # trailing training window for each refit
    min_train: int = 90            # usable training days required before forecasting
    refit_every: int = 7           # refit cadence (days); predictions use the latest earlier fit
    ridge: float = 0.05            # ridge penalty as a fraction of training rows (standardized lags)
    calib_days: int = 365          # trailing window of earlier scores used for calibration
    min_calib: int = 60            # earlier scores required before a p-value is reported
    tail_fraction: float = 0.10    # generalized-Pareto tail above this upper fraction
    min_events_mix: int = 15       # events required to score composition channels
    monitor_min_median: float = 30.0   # median daily events in the development year to be monitored
    dev_start: str = "2023-01-01"
    dev_end: str = "2023-12-31"
    tiers: tuple[int, int, int] = (100, 365, 1000)   # return periods (days): notable, rare, extreme
    # Instrument (coverage) channel. Holiday lulls lower volume but keep the publisher mix; ingestion
    # faults and provider backlogs change the publisher mix (2023-03-22 outage: JS 0.61; backlog 0.2-0.3).
    instrument_min_ratio: float = 0.35     # global volume vs same-weekday norm
    instrument_max_ratio: float = 1.6
    instrument_max_source_js: float = 0.17  # publisher-mix JSD vs trailing 28 days (~99.5th percentile)
    fdr_q: float = 0.10
    rolling_days: int = 28
    covariance_floor: float = 1e-4


TIER_NAMES = ["none", "notable", "rare", "extreme"]


# ----------------------------------------------------------------------------- forecasting
def lag_features(y: np.ndarray, valid: np.ndarray):
    """Lag-1 value, trailing 7- and 28-day means of valid days; availability mask."""
    T, d = y.shape
    filled = np.where(valid[:, None], y, 0.0)
    cs = np.vstack([np.zeros((1, d)), np.cumsum(filled, axis=0)])
    cn = np.concatenate([[0], np.cumsum(valid)])
    idx = np.arange(T)

    def window(k):
        lo = np.maximum(idx - k, 0)
        s = cs[idx] - cs[lo]
        c = cn[idx] - cn[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            return s / np.maximum(c, 1)[:, None], c

    m7, c7 = window(7)
    m28, c28 = window(28)
    lag1 = np.vstack([np.full((1, d), np.nan), y[:-1]])
    prev_valid = np.concatenate([[False], valid[:-1]])
    available = prev_valid & (c7 >= 4) & (c28 >= 14)
    return np.hstack([lag1, m7, m28]), available


def prequential(y: np.ndarray, valid: np.ndarray, weekdays: np.ndarray, cfg: Config):
    """Weekday-aware ridge forecasts; block [tau, tau+refit) uses a fit on days before tau."""
    if y.ndim == 1:
        y = y[:, None]
    T, d = y.shape
    lags, available = lag_features(y, valid)
    design = np.hstack([np.ones((T, 1)), weekday_dummies(weekdays)])
    pred = np.full((T, d), np.nan)
    fitted_at = np.full(T, -1)
    for tau in range(0, T, cfg.refit_every):
        rows = np.arange(max(0, tau - cfg.train_days), tau)
        rows = rows[available[rows] & valid[rows]]
        block = np.arange(tau, min(T, tau + cfg.refit_every))
        block = block[available[block]]
        if len(rows) < cfg.min_train or not len(block):
            continue
        lag_rows = lags[rows]
        mu, sd = lag_rows.mean(0), lag_rows.std(0)
        sd[sd < 1e-9] = 1.0
        x = np.hstack([design[rows], (lag_rows - mu) / sd])
        beta = fit_ridge(x, y[rows], cfg.ridge * len(rows), unpenalized=7)
        pred[block] = np.hstack([design[block], (lags[block] - mu) / sd]) @ beta
        fitted_at[block] = tau
    return pred, fitted_at


def _calibrate(scores: np.ndarray, cfg: Config) -> np.ndarray:
    """Upper-tail p-value of each score against earlier scores in the trailing window."""
    T = len(scores)
    p = np.full(T, np.nan)
    finite = np.isfinite(scores)
    for t in np.flatnonzero(finite):
        lo = max(0, t - cfg.calib_days)
        prior = scores[lo:t][finite[lo:t]]
        if len(prior) >= cfg.min_calib:
            value = tail_pvalue(float(scores[t]), prior, tail_fraction=cfg.tail_fraction)
            if value is not None:
                p[t] = value
    return p


def _blocks(fitted_at: np.ndarray):
    for tau in np.unique(fitted_at[fitted_at >= 0]):
        yield int(tau), np.flatnonzero(fitted_at == tau)


# ----------------------------------------------------------------------------- channels
def attention_channel(n: np.ndarray, world: np.ndarray, usable: np.ndarray, weekdays: np.ndarray, cfg: Config):
    valid = usable & (world > 0)
    y = np.log((n + 0.5) / np.maximum(world, 1.0))
    pred, fitted = prequential(y, valid, weekdays, cfg)
    resid = y - pred[:, 0]
    score = np.where(valid & np.isfinite(resid), resid, np.nan)
    return {"score": score, "p": _calibrate(score, cfg), "ratio": np.exp(resid), "expected_share": np.exp(pred[:, 0]),
            "observed_share": np.exp(y)}


def conflict_channel(n: np.ndarray, v: np.ndarray, usable: np.ndarray, weekdays: np.ndarray, cfg: Config):
    valid = usable & (n >= cfg.min_events_mix)
    y = np.log((v + 0.5) / (n - v + 0.5))
    pred, fitted = prequential(y, valid, weekdays, cfg)
    resid = y - pred[:, 0]
    sampling = 1 / (v + 0.5) + 1 / (n - v + 0.5)
    score = np.full(len(n), np.nan)
    for tau, block in _blocks(fitted):
        prior = np.arange(max(0, tau - cfg.calib_days), tau)
        prior = prior[valid[prior] & np.isfinite(resid[prior])]
        if len(prior) < 20:
            continue
        process = max(float(np.var(resid[prior]) - np.mean(sampling[prior])), cfg.covariance_floor)
        ok = block[valid[block]]
        score[ok] = resid[ok] / np.sqrt(process + sampling[ok])
    expected = 1 / (1 + np.exp(-pred[:, 0]))
    observed = (v + 0.5) / (n + 1.0)
    return {"score": score, "p": _calibrate(score, cfg), "expected_share": expected, "observed_share": observed}


def mix_channel(counts: np.ndarray, usable: np.ndarray, weekdays: np.ndarray, cfg: Config, alpha: float = 0.5):
    """ILR composition surprise with Sigma_t = Sigma_process + Sigma_sampling(n_t, forecast shares)."""
    T, K = counts.shape
    n = counts.sum(1)
    valid = usable & (n >= cfg.min_events_mix)
    shares = (counts + alpha) / (n[:, None] + alpha * K)
    basis = helmert(K, full=False)
    z = np.log(shares) @ basis.T
    pred, fitted = prequential(z, valid, weekdays, cfg)
    resid = z - pred
    expz = np.exp(pred @ basis)
    forecast = expz / expz.sum(1, keepdims=True)
    score = np.full(T, np.nan)

    def sampling_cov(t):
        return (basis / (np.maximum(n[t], 1) * forecast[t])) @ basis.T

    for tau, block in _blocks(fitted):
        prior = np.arange(max(0, tau - cfg.calib_days), tau)
        prior = prior[valid[prior] & np.all(np.isfinite(resid[prior]), axis=1)]
        if len(prior) < 30:
            continue
        mean_sampling = np.mean([sampling_cov(t) for t in prior], axis=0)
        process = np.cov(resid[prior], rowvar=False) - mean_sampling
        w, v = np.linalg.eigh((process + process.T) / 2)
        process = (v * np.maximum(w, cfg.covariance_floor)) @ v.T
        for t in block[valid[block]]:
            r = resid[t]
            score[t] = float(np.sqrt(max(0.0, r @ np.linalg.solve(process + sampling_cov(t), r))))
    return {"score": score, "p": _calibrate(score, cfg), "forecast": forecast, "observed": shares}


def semantic_channel(root_counts: np.ndarray, root_vectors: np.ndarray, usable: np.ndarray, weekdays: np.ndarray,
                     cfg: Config, alpha: float = 0.5):
    """Surprise of the day's semantic centroid in the learned event-type space (16-d).

    Sampling covariance of a multinomial mean of embedding vectors:
    (E' diag(p) E - e e') / n, with p the country's trailing 28-day mean shares (prior days only).
    """
    T, K = root_counts.shape
    n = root_counts.sum(1)
    valid = usable & (n >= cfg.min_events_mix)
    shares = (root_counts + alpha) / (n[:, None] + alpha * K)
    centroid = shares @ root_vectors
    pred, fitted = prequential(centroid, valid, weekdays, cfg)
    resid = centroid - pred
    filled = np.where(valid[:, None], shares, 0.0)
    cs = np.vstack([np.zeros((1, K)), np.cumsum(filled, axis=0)])
    cn = np.concatenate([[0], np.cumsum(valid)])
    idx = np.arange(T)
    lo = np.maximum(idx - cfg.rolling_days, 0)
    prior_shares = (cs[idx] - cs[lo]) / np.maximum(cn[idx] - cn[lo], 1)[:, None]

    def sampling_cov(t):
        p = prior_shares[t] if prior_shares[t].sum() > 0 else shares[t]
        mean = p @ root_vectors
        return ((root_vectors.T * p) @ root_vectors - np.outer(mean, mean)) / max(n[t], 1)

    score = np.full(T, np.nan)
    for tau, block in _blocks(fitted):
        prior = np.arange(max(0, tau - cfg.calib_days), tau)
        prior = prior[valid[prior] & np.all(np.isfinite(resid[prior]), axis=1)]
        if len(prior) < 30:
            continue
        mean_sampling = np.mean([sampling_cov(t) for t in prior], axis=0)
        process = np.cov(resid[prior], rowvar=False) - mean_sampling
        w, v = np.linalg.eigh((process + process.T) / 2)
        process = (v * np.maximum(w, cfg.covariance_floor)) @ v.T
        for t in block[valid[block]]:
            r = resid[t]
            score[t] = float(np.sqrt(max(0.0, r @ np.linalg.solve(process + sampling_cov(t), r))))
    return {"score": score, "p": _calibrate(score, cfg)}


# ----------------------------------------------------------------------------- global
def learned_transport(panel: Panel, cost_fn, cfg: Config, top: int = 48) -> dict:
    """Optimal transport between daily CAMEO base-code mixes under the learned ground cost.

    Support: the `top` most frequent development-year codes plus one pooled 'other' bin
    (placed at the root centroid of the codes it pools) to keep exact OT fast.
    """
    from .stats import transport
    dev = np.array([cfg.dev_start <= d <= cfg.dev_end for d in panel.dates]) & panel.usable
    totals = panel.base[dev].sum(0)
    keep = list(np.argsort(-totals)[:top])
    rest = [i for i in range(len(panel.base_codes)) if i not in keep]
    codes = [panel.base_codes[i] for i in keep]
    cost = cost_fn(codes)
    other_root = max({panel.base_codes[i][:2] for i in rest}, key=lambda r: sum(totals[i] for i in rest if panel.base_codes[i][:2] == r)) if rest else None
    if rest:
        other = cost_fn(codes + [other_root + "0"])[-1, :-1]
        cost = np.vstack([np.hstack([cost, other[:, None]]), np.hstack([other, [0.0]])])
    def mix(t):
        row = panel.base[t]
        values = np.r_[row[keep], row[rest].sum()] if rest else row[keep]
        return (values + 0.5) / (values.sum() + 0.5 * len(values))
    frozen = np.mean([mix(t) for t in np.flatnonzero(dev)], axis=0)
    T = panel.T
    ot_frozen = np.full(T, np.nan)
    ot_rolling = np.full(T, np.nan)
    mixes = {t: mix(t) for t in np.flatnonzero(panel.usable)}
    for t in mixes:
        ot_frozen[t] = transport(mixes[t], frozen, cost)
        prior = [s for s in range(max(0, t - cfg.rolling_days), t) if s in mixes]
        if len(prior) >= 14:
            ot_rolling[t] = transport(mixes[t], np.mean([mixes[s] for s in prior], axis=0), cost)
    dev_values = ot_frozen[dev & np.isfinite(ot_frozen)]
    return {"ot_frozen": ot_frozen, "ot_rolling": ot_rolling, "codes": codes + (["other"] if rest else []),
            "ot_dev_median": float(np.median(dev_values)) if len(dev_values) else None}


def instrument_status(panel: Panel, cfg: Config):
    """Global coverage relative to the same weekday over the previous eight usable weeks."""
    T = panel.T
    ratio = np.full(T, np.nan)
    for t in range(T):
        same = [t - 7 * k for k in range(1, 9) if t - 7 * k >= 0 and panel.usable[t - 7 * k]]
        if len(same) >= 3 and panel.total[t] > 0:
            ratio[t] = panel.total[t] / np.median(panel.total[same])
    degraded = ~panel.usable | (np.isfinite(ratio) & ((ratio < cfg.instrument_min_ratio) | (ratio > cfg.instrument_max_ratio)))
    source_js = np.full(T, np.nan)
    for t in range(T):
        if not panel.usable[t] or not panel.domains[t]:
            continue
        prior = [s for s in range(max(0, t - cfg.rolling_days), t) if panel.usable[s] and panel.domains[s]]
        if len(prior) < 14:
            continue
        reference: dict[str, float] = {}
        for s in prior:
            total = sum(panel.domains[s].values())
            for k, v in panel.domains[s].items():
                reference[k] = reference.get(k, 0.0) + v / total / len(prior)
        keys = sorted(set(reference) | set(panel.domains[t]))
        source_js[t] = jsd([panel.domains[t].get(k, 0) + 1e-9 for k in keys], [reference.get(k, 0) + 1e-9 for k in keys])
    degraded |= np.isfinite(source_js) & (source_js > cfg.instrument_max_source_js)
    return {"volume_ratio": ratio, "degraded": degraded, "source_js": source_js}


def global_monitor(panel: Panel, cfg: Config) -> dict:
    dev = np.array([cfg.dev_start <= d <= cfg.dev_end for d in panel.dates]) & panel.usable
    instrument = instrument_status(panel, cfg)
    clean = panel.usable & ~instrument["degraded"]
    roots = panel.roots
    mix = mix_channel(roots, clean, panel.weekdays, cfg)
    shares = np.vstack([smoothed_counts(r) if r.sum() > 0 else np.full(20, np.nan) for r in roots])
    frozen = shares[dev].mean(0)
    frozen /= frozen.sum()
    T = panel.T
    js_frozen = np.full(T, np.nan)
    js_rolling = np.full(T, np.nan)
    contributions = np.full((T, 20), np.nan)
    for t in range(T):
        if not panel.usable[t]:
            continue
        js_frozen[t] = jsd(shares[t], frozen)
        contributions[t] = js_contributions(shares[t], frozen)
        prior = [s for s in range(max(0, t - cfg.rolling_days), t) if panel.usable[s]]
        if len(prior) >= 14:
            rolling = shares[prior].mean(0)
            js_rolling[t] = jsd(shares[t], rolling / rolling.sum())
    dev_js = js_frozen[dev & np.isfinite(js_frozen)]
    return {"mix": mix, "shares": shares, "frozen_reference": frozen, "js_frozen": js_frozen,
            "js_rolling": js_rolling, "js_contributions": contributions,
            "js_dev_median": float(np.median(dev_js)) if len(dev_js) else None, "instrument": instrument}


# ----------------------------------------------------------------------------- countries
def monitored_countries(panel: Panel, cfg: Config) -> list[int]:
    dev = np.array([cfg.dev_start <= d <= cfg.dev_end for d in panel.dates]) & panel.usable
    medians = np.median(panel.c_total[dev], axis=0)
    return [j for j in np.argsort(-medians) if medians[j] >= cfg.monitor_min_median]


def country_monitor(panel: Panel, cfg: Config, instrument: dict, root_vectors: np.ndarray | None = None) -> dict:
    """Score every monitored country on every day; returns arrays shaped (T, M).

    With `root_vectors` (learned event-type embeddings), a fourth semantic channel is scored
    and combined separately as `p_combined_semantic` (protocol detector D6); the published
    default remains the three-channel combination (D5).
    """
    members = monitored_countries(panel, cfg)
    T, M = panel.T, len(members)
    fam = panel.c_families
    world = panel.total
    # Degraded instrument days are neither scored nor used to train or calibrate later days.
    clean = panel.usable & ~instrument["degraded"]
    keys = ["p_attention", "p_mix", "p_conflict", "s_attention", "s_mix", "s_conflict", "attention_ratio",
            "conflict_obs", "conflict_exp", "p_combined", "p_articles", "article_ratio", "outlets", "articles", "events"]
    out = {k: np.full((T, M), np.nan) for k in keys}
    if root_vectors is not None:
        out["p_semantic"] = np.full((T, M), np.nan)
        out["p_combined_semantic"] = np.full((T, M), np.nan)
    out["mix_forecast"] = np.full((T, M, len(FAMILIES)), np.nan)
    out["mix_observed"] = np.full((T, M, len(FAMILIES)), np.nan)
    for m, j in enumerate(members):
        n = panel.c_total[:, j]
        counts = fam[:, j, :]
        v = counts[:, CONFLICT_FAMILIES].sum(1)
        att = attention_channel(n, world, clean, panel.weekdays, cfg)
        con = conflict_channel(n, v, clean, panel.weekdays, cfg)
        mix = mix_channel(counts, clean, panel.weekdays, cfg)
        out["p_attention"][:, m], out["s_attention"][:, m], out["attention_ratio"][:, m] = att["p"], att["score"], att["ratio"]
        out["p_conflict"][:, m], out["s_conflict"][:, m] = con["p"], con["score"]
        out["conflict_obs"][:, m], out["conflict_exp"][:, m] = con["observed_share"], con["expected_share"]
        out["p_mix"][:, m], out["s_mix"][:, m] = mix["p"], mix["score"]
        # Attention measured in distinct articles (one article can yield many machine-extracted events).
        art = attention_channel(panel.c_urls[:, j], panel.urls, clean, panel.weekdays, cfg)
        out["p_articles"][:, m], out["article_ratio"][:, m] = art["p"], art["ratio"]
        out["outlets"][:, m], out["articles"][:, m], out["events"][:, m] = panel.c_outlets[:, j], panel.c_urls[:, j], n
        out["mix_forecast"][:, m], out["mix_observed"][:, m] = mix["forecast"], mix["observed"]
        if root_vectors is not None:
            out["p_semantic"][:, m] = semantic_channel(panel.c_roots[:, j, :].astype(float), root_vectors, clean,
                                                       panel.weekdays, cfg)["p"]
        for t in range(T):
            ps = [out[k][t, m] for k in ("p_attention", "p_mix", "p_conflict")]
            ps = [float(p) for p in ps if np.isfinite(p)]
            if ps:
                out["p_combined"][t, m] = cauchy_combination(ps)
                if root_vectors is not None and np.isfinite(out["p_semantic"][t, m]):
                    out["p_combined_semantic"][t, m] = cauchy_combination(ps + [float(out["p_semantic"][t, m])])
    out["members"] = members
    out["countries"] = [panel.countries[j] for j in members]
    out.update(alarms(out, instrument, cfg))
    return out


def tier_of(p: float | None, cfg: Config) -> int:
    if p is None or not np.isfinite(p):
        return 0
    period = 1 / max(p, 1e-12)
    return sum(period >= threshold for threshold in cfg.tiers)


def alarms(scores: dict, instrument: dict, cfg: Config) -> dict:
    p = scores["p_combined"]
    T, M = p.shape
    tier = np.zeros((T, M), dtype=int)
    significant = np.zeros((T, M), dtype=bool)
    turbulence = np.full(T, np.nan)
    expected = np.full(T, np.nan)
    for t in range(T):
        row = {m: float(p[t, m]) for m in range(M) if np.isfinite(p[t, m])}
        if not row:
            continue
        for m, value in row.items():
            tier[t, m] = tier_of(value, cfg)
        for m in benjamini_hochberg({str(k): v for k, v in row.items()}, cfg.fdr_q):
            significant[t, int(m)] = True
        turbulence[t] = sum(v <= 0.05 for v in row.values())
        expected[t] = 0.05 * len(row)
    alarm = (tier > 0) & ~instrument["degraded"][:, None]
    return {"tier": tier, "alarm": alarm, "fdr_significant": significant,
            "turbulence": turbulence, "turbulence_expected": expected}


def config_dict(cfg: Config) -> dict:
    return asdict(cfg)
