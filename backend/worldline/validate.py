"""Out-of-sample validation of country alarms against independent Wikipedia labels.

Protocol v2.0 — declared in code and in research/protocol.md before the test
period was evaluated. Development year: 2023. Test period: 2024-01-01 onward.

Unit            (country, day) for monitored countries with a combined p-value.
Positive label  (country, date) from a Wikipedia year-article entry naming that country.
Primary set     entries categorised conflict or political ("sociopolitical").
Hit window      an alarm on day d matches a label dated e when d - e in [-1, +2].
Metrics         event recall, alarm precision, lift over base rate, stratified AUC of
                the windowed maximum unusualness (-log10 p) against same-country days
                with no label within +/-7 days.
Significance    circular-shift permutation tests within countries (preserve each country's
                alarm clustering and label clustering); bootstrap CIs over labels.
Baselines       random scores; naive same-weekday volume spike z-score; single channels.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

WINDOW_BEFORE = 1   # alarm may precede the listed date by one day
WINDOW_AFTER = 2    # or follow it by up to two days
NEGATIVE_EXCLUSION = 7
PROTOCOL_VERSION = "worldline-validation-protocol-2.0"
PRIMARY_CATEGORIES = ("conflict", "political")


@dataclass
class Labels:
    positives: list[tuple[int, int]]          # (day index, member index), deduplicated
    events_by_member: dict[int, np.ndarray]   # member -> sorted day indices


def label_index(labels: list[dict], dates: list[str], countries: list[str], *, categories=PRIMARY_CATEGORIES,
                start: str, end: str) -> Labels:
    day_of = {d: i for i, d in enumerate(dates)}
    member_of = {c: i for i, c in enumerate(countries)}
    pairs = set()
    for event in labels:
        if not (start <= event["date"] <= end):
            continue
        if categories and not set(event["categories"]) & set(categories):
            continue
        t = day_of.get(event["date"])
        if t is None:
            continue
        for iso in event["countries"]:
            if iso in member_of:
                pairs.add((t, member_of[iso]))
    by_member: dict[int, list[int]] = {}
    for t, m in pairs:
        by_member.setdefault(m, []).append(t)
    return Labels(sorted(pairs), {m: np.array(sorted(v)) for m, v in by_member.items()})


def windowed_max(u: np.ndarray, t: int, m: int) -> float:
    lo, hi = max(0, t - WINDOW_BEFORE), min(u.shape[0], t + WINDOW_AFTER + 1)
    values = u[lo:hi, m]
    values = values[np.isfinite(values)]
    return float(values.max()) if len(values) else float("nan")


def _auc_pairs(pos: np.ndarray, neg: np.ndarray) -> tuple[float, int]:
    """Mann-Whitney U (ties count half) and number of pairs."""
    if not len(pos) or not len(neg):
        return 0.0, 0
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv))
    sorted_values = allv[order]
    i = 0
    while i < len(allv):  # average ranks for ties
        j = i
        while j + 1 < len(allv) and sorted_values[j + 1] == sorted_values[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    u = ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2
    return float(u), len(pos) * len(neg)


def stratified_auc(u: np.ndarray, scored: np.ndarray, labels: Labels, test: np.ndarray, positives=None):
    """Within-country AUC of windowed max scores, pooled over countries (weighted by pairs)."""
    total_u, total_pairs, per_member = 0.0, 0, {}
    groups: dict[int, list[int]] = {}
    for t, m in (positives if positives is not None else labels.positives):
        groups.setdefault(m, []).append(t)
    for m, ts in groups.items():
        pos = np.array([windowed_max(u, t, m) for t in ts])
        pos = pos[np.isfinite(pos)]
        label_days = labels.events_by_member.get(m, np.array([], int))
        candidates = np.flatnonzero(test & scored[:, m])
        if len(label_days):
            distance = np.min(np.abs(candidates[:, None] - label_days[None, :]), axis=1)
            candidates = candidates[distance > NEGATIVE_EXCLUSION]
        neg = np.array([windowed_max(u, t, m) for t in candidates])
        neg = neg[np.isfinite(neg)]
        value, pairs = _auc_pairs(pos, neg)
        if pairs:
            per_member[m] = (value / pairs, len(pos))
            total_u += value
            total_pairs += pairs
    return (total_u / total_pairs if total_pairs else float("nan")), per_member


def alarm_metrics(alarm: np.ndarray, scored: np.ndarray, labels: Labels, test: np.ndarray) -> dict:
    T, M = alarm.shape
    near = np.zeros((T, M), dtype=bool)  # day d has a label e with d - e in [-1, +2]
    for t, m in labels.positives:
        near[max(0, t - WINDOW_BEFORE):min(T, t + WINDOW_AFTER + 1), m] = True
    alarms = alarm & test[:, None]
    n_alarms = int(alarms.sum())
    hits = int((alarms & near).sum())
    eligible = scored & test[:, None]
    base_rate = float((near & eligible).sum() / max(eligible.sum(), 1))
    detected = 0
    first_offsets = []
    for t, m in labels.positives:
        if not test[t]:
            continue
        window = range(max(0, t - WINDOW_BEFORE), min(T, t + WINDOW_AFTER + 1))
        found = [d - t for d in window if alarms[d, m]]
        if found:
            detected += 1
            first_offsets.append(found[0])
    n_pos = sum(1 for t, _ in labels.positives if test[t])
    precision = hits / n_alarms if n_alarms else float("nan")
    return {"alarms": n_alarms, "alarm_hits": hits, "precision": precision, "base_rate": base_rate,
            "lift": precision / base_rate if n_alarms and base_rate else float("nan"),
            "labels": n_pos, "labels_detected": detected, "recall": detected / n_pos if n_pos else float("nan"),
            "first_alarm_offsets": {str(k): first_offsets.count(k) for k in range(-WINDOW_BEFORE, WINDOW_AFTER + 1)}}


def circular_shift_null(alarm: np.ndarray, scored: np.ndarray, labels: Labels, test: np.ndarray, *,
                        permutations: int = 1000, seed: int = 20261016, min_shift: int = 30) -> dict:
    """Precision under random circular shifts of each country's alarm series within the test period."""
    rng = np.random.default_rng(seed)
    test_idx = np.flatnonzero(test)
    T, M = alarm.shape
    near = np.zeros((T, M), dtype=bool)
    for t, m in labels.positives:
        near[max(0, t - WINDOW_BEFORE):min(T, t + WINDOW_AFTER + 1), m] = True
    a = alarm[test_idx]
    nr = near[test_idx]
    L = len(test_idx)
    observed = (a & nr).sum() / max(a.sum(), 1)
    null = np.empty(permutations)
    for k in range(permutations):
        shifts = rng.integers(min_shift, L - min_shift, size=M)
        rows = (np.arange(L)[:, None] - shifts[None, :]) % L
        shifted = np.take_along_axis(a, rows, axis=0)
        null[k] = (shifted & nr).sum() / max(shifted.sum(), 1)
    return {"observed_precision": float(observed), "null_mean": float(null.mean()),
            "null_p95": float(np.quantile(null, 0.95)), "p_value": float((1 + np.sum(null >= observed)) / (permutations + 1)),
            "permutations": permutations}


def auc_null(u: np.ndarray, scored: np.ndarray, labels: Labels, test: np.ndarray, *, permutations: int = 200,
             seed: int = 7, min_shift: int = 30) -> dict:
    """AUC under circular shifts of each country's label dates within the test period."""
    rng = np.random.default_rng(seed)
    test_idx = np.flatnonzero(test)
    position = {t: i for i, t in enumerate(test_idx)}
    L = len(test_idx)
    observed, _ = stratified_auc(u, scored, labels, test)
    null = []
    for _ in range(permutations):
        shift = {m: int(rng.integers(min_shift, L - min_shift)) for m in labels.events_by_member}
        shifted = sorted({(int(test_idx[(position[t] + shift[m]) % L]), m) for t, m in labels.positives if t in position})
        by_member: dict[int, list[int]] = {}
        for t, m in shifted:
            by_member.setdefault(m, []).append(t)
        fake = Labels(shifted, {m: np.array(sorted(v)) for m, v in by_member.items()})
        value, _ = stratified_auc(u, scored, fake, test)
        null.append(value)
    null_arr = np.array(null)
    return {"observed_auc": float(observed), "null_mean": float(np.nanmean(null_arr)),
            "null_p95": float(np.nanquantile(null_arr, 0.95)),
            "p_value": float((1 + np.sum(null_arr >= observed)) / (len(null_arr) + 1)), "permutations": permutations}


def bootstrap_auc(u: np.ndarray, scored: np.ndarray, labels: Labels, test: np.ndarray, *, reps: int = 300,
                  seed: int = 11, other: np.ndarray | None = None) -> dict:
    """Percentile bootstrap over positive labels; optional paired difference against `other` scores."""
    rng = np.random.default_rng(seed)
    positives = [p for p in labels.positives if test[p[0]]]
    values, diffs = [], []
    for _ in range(reps):
        sample = [positives[i] for i in rng.integers(0, len(positives), len(positives))]
        value, _ = stratified_auc(u, scored, labels, test, positives=sample)
        values.append(value)
        if other is not None:
            reference, _ = stratified_auc(other, scored, labels, test, positives=sample)
            diffs.append(value - reference)
    out = {"auc_ci95": [float(np.nanquantile(values, 0.025)), float(np.nanquantile(values, 0.975))]}
    if other is not None:
        out["difference_ci95"] = [float(np.nanquantile(diffs, 0.025)), float(np.nanquantile(diffs, 0.975))]
        out["difference_mean"] = float(np.nanmean(diffs))
    return out


def naive_volume_spike(c_total: np.ndarray, usable: np.ndarray, members: list[int]) -> np.ndarray:
    """Baseline: z of log(n+1) against the same weekday over the previous four weeks."""
    T = c_total.shape[0]
    out = np.full((T, len(members)), np.nan)
    y = np.log(c_total[:, members] + 1)
    for t in range(28, T):
        if not usable[t]:
            continue
        prior = [t - 7 * k for k in range(1, 5) if usable[t - 7 * k]]
        if len(prior) < 3:
            continue
        mean = y[prior].mean(0)
        sd = np.maximum(y[prior].std(0, ddof=1), 0.1)
        out[t] = (y[t] - mean) / sd
    return out


def z_to_unusualness(z: np.ndarray) -> np.ndarray:
    """One-sided normal tail, as -log10 p, for baselines expressed as z-scores."""
    from scipy.stats import norm
    return -np.log10(np.clip(norm.sf(z), 1e-12, 1.0))


def calibration_on_quiet_days(p: np.ndarray, labels_all: Labels, test: np.ndarray) -> dict:
    """Share of p-values below alpha on country-days with no label of any kind within +/-7 days."""
    T, M = p.shape
    quiet = np.ones((T, M), dtype=bool)
    for t, m in labels_all.positives:
        quiet[max(0, t - NEGATIVE_EXCLUSION):min(T, t + NEGATIVE_EXCLUSION + 1), m] = False
    values = p[test[:, None] & quiet & np.isfinite(p)]
    return {"n": int(values.size), **{f"share_p_le_{a}": float(np.mean(values <= a)) for a in (0.05, 0.01, 0.001)}}


def unusualness(p: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return -np.log10(np.clip(p, 1e-12, 1.0))


def safe(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value
