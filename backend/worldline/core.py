"""Small, deterministic statistical engine. All fits use strictly prior windows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import re
import unicodedata
from typing import Any

import numpy as np
from scipy.linalg import helmert
from scipy.optimize import linprog
from scipy.special import softmax

TAXONOMY = [
    {"id": "geopolitics", "label": "Geopolitics", "color": "#ebaa6b"},
    {"id": "science", "label": "Science & technology", "color": "#afbaef"},
    {"id": "economy", "label": "Economy", "color": "#e5cf8d"},
    {"id": "climate", "label": "Climate & environment", "color": "#7ebfab"},
    {"id": "health", "label": "Public health", "color": "#e793a1"},
    {"id": "society", "label": "Society & culture", "color": "#8dbbd4"},
]
MODEL_VERSION = "ilr-ridge-ar1-shrinkage-v1"
FEATURE_VERSION = "fixed-topics-ilr-alpha0.5-v1"


def probability(values: Any) -> np.ndarray:
    p = np.asarray(values, dtype=float)
    if p.ndim != 1 or len(p) < 2 or not np.all(np.isfinite(p)) or np.any(p < 0) or p.sum() <= 0:
        raise ValueError("A finite, nonnegative, nonempty distribution with at least two bins is required")
    return p / p.sum()


def jsd(p: Any, q: Any) -> float:
    p, q = probability(p), probability(q)
    if p.shape != q.shape:
        raise ValueError("Distribution dimensions differ")
    m = (p + q) / 2
    value = 0.0
    for r in (p, q):
        active = r > 0
        value += float(np.sum(r[active] * np.log(r[active] / m[active]))) / 2
    return max(0.0, value)


def js_contributions(p: Any, q: Any) -> np.ndarray:
    p, q = probability(p), probability(q)
    m = (p + q) / 2
    result = np.zeros_like(p)
    for r in (p, q):
        mask = r > 0
        result[mask] += 0.5 * r[mask] * np.log(r[mask] / m[mask])
    return result


def taxonomy_cost(k: int = 6) -> np.ndarray:
    """Declared ontology prior; social/economic, science/health, environment."""
    # Custom taxonomies must provide their own geometry. The generic fallback
    # makes all distinct categories equally distant instead of inventing links.
    groups = [0, 1, 0, 2, 1, 0] if k == 6 else list(range(k))
    c = np.ones((k, k))
    for i in range(k):
        for j in range(k):
            if groups[i] == groups[j]:
                c[i, j] = 0.5
    np.fill_diagonal(c, 0)
    return c


def transport(p: Any, q: Any, cost: Any) -> float:
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


def smoothed_counts(counts: Any, alpha: float = 0.5) -> np.ndarray:
    c = np.asarray(counts, dtype=float)
    probability(c)  # Reject genuinely empty windows, not pseudocount them into observations.
    if alpha <= 0:
        raise ValueError("Positive smoothing required")
    return probability(c + alpha)


def canonical_title(text: str) -> str:
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def cluster_mentions(mentions: list[dict]) -> list[dict]:
    """Conservative exact normalized-title/entity/day/region heuristic, not truth verification.

    Provider IDs deduplicate repeated records. Identical titles with aligned entity,
    day and region context also cluster. Near duplicates use deterministic token
    overlap >= .92, only for >= 8 tokens and the same nonempty entity context.
    """
    groups: list[dict] = []
    provider_ids: set[tuple] = set()
    for item in sorted(mentions, key=lambda v: (v.get("observed_at", ""), v["id"])):
        key = (item.get("provider", "synthetic"), item["id"])
        if key in provider_ids:
            continue
        provider_ids.add(key)
        title = canonical_title(item["title"])
        entities = tuple(sorted(item.get("entities", [])))
        context = (item["date"], item["domain"], item.get("region", ""), entities)
        target = None
        tokens = set(title.split())
        for g in groups:
            if g["_context"] != context:
                continue
            if g["_title"] == title:
                target = g
                break
            prior = g["_tokens"]
            if entities and min(len(tokens), len(prior)) >= 8 and len(tokens & prior) / len(tokens | prior) >= .92:
                target = g
                break
        if target is None:
            target = dict(item, _context=context, _title=title, _tokens=tokens, source_ids=[], mention_ids=[])
            target["cluster_id"] = "cluster_" + sha256(json.dumps([context, title]).encode()).hexdigest()[:16]
            groups.append(target)
        target["source_ids"] = sorted(set(target["source_ids"] + [item["source"]]))
        target["mention_ids"].append(item["id"])
    for g in groups:
        for internal_key in ("_context", "_title", "_tokens"):
            g.pop(internal_key)
        g["source_count"] = len(g["source_ids"])
        g["cluster_version"] = "conservative-lexical-v1"
    return sorted(groups, key=lambda g: g["cluster_id"])


@dataclass(frozen=True)
class Config:
    reference_windows: int = 30
    train_windows: int = 45
    covariance_min: int = 20
    rank_min: int = 30
    trailing_windows: int = 90
    min_events: int = 40
    min_sources: int = 3
    ridge: float = 2.0
    covariance_floor: float = 0.025
    source_js_limit: float = 0.12
    candidate_rank: float = 97.5
    cooldown: int = 7


def fit_ridge(states: list[np.ndarray], positions: list[int], penalty: float) -> np.ndarray:
    pairs = [(states[i - 1], states[i]) for i in range(1, len(states)) if positions[i] == positions[i - 1] + 1]
    if not pairs:
        raise ValueError("No adjacent training windows")
    x = np.array([np.r_[1, a] for a, _ in pairs])
    y = np.array([b for _, b in pairs])
    reg = np.eye(x.shape[1]) * penalty
    reg[0, 0] = 0
    return np.linalg.solve(x.T @ x + reg, x.T @ y)


def shrinkage_covariance(residuals: list[np.ndarray], floor: float) -> np.ndarray:
    cov = np.atleast_2d(np.cov(np.asarray(residuals), rowvar=False))
    d = cov.shape[0]
    target = np.eye(d) * max(float(np.trace(cov)) / d, floor)
    return .8 * cov + .2 * target + floor * np.eye(d)


def build_snapshot(windows: list[dict], *, config: Config = Config(), taxonomy: list[dict] | None = None,
                   cost: np.ndarray | None = None, mode: str = "synthetic_demo") -> dict:
    taxonomy = taxonomy or TAXONOMY
    k = len(taxonomy)
    cost = taxonomy_cost(k) if cost is None else cost
    if len(windows) <= config.reference_windows:
        raise ValueError("Insufficient windows for a frozen reference")
    dates = [w["date"] for w in windows]
    if dates != sorted(set(dates)):
        raise ValueError("Windows must be chronological and dates unique")
    for w in windows:
        if len(w["counts"]) != k or np.any(np.asarray(w["counts"]) < 0):
            raise ValueError("Invalid taxonomy counts")
    initial = windows[:config.reference_windows]
    if any(sum(w["counts"]) < config.min_events or len(w["sources"]) < config.min_sources for w in initial):
        raise ValueError("Insufficient coverage in frozen reference; do not fabricate baseline")
    reference = np.mean([smoothed_counts(w["counts"]) for w in initial], axis=0)
    ref_sources: dict[str, float] = {}
    for w in initial:
        total = sum(w["sources"].values())
        for source, count in w["sources"].items():
            ref_sources[source] = ref_sources.get(source, 0) + count / total / len(initial)
    ref_id = "reference_" + sha256(json.dumps(initial, sort_keys=True).encode()).hexdigest()[:12]
    states: list[np.ndarray] = []
    positions: list[int] = []
    residuals: list[np.ndarray] = []
    scores: list[float] = []
    valid_shares: list[np.ndarray] = []
    frozen = None
    history: list[dict] = []
    last_alert = -100
    recent_high: list[bool] = []
    for t, w in enumerate(windows):
        count = int(sum(w["counts"]))
        source_names = sorted(set(ref_sources) | set(w["sources"]))
        source_js = (jsd([ref_sources.get(s, 0) for s in source_names], [w["sources"].get(s, 0) for s in source_names])
                     if sum(w["sources"].values()) > 0 else None)
        warnings = []
        if count < config.min_events:
            warnings.append(f"Only {count} clusters; minimum {config.min_events}. Signal suppressed.")
        if len(w["sources"]) < config.min_sources:
            warnings.append("Too few source domains for a coverage comparison.")
        if source_js is None or source_js > config.source_js_limit:
            warnings.append("Publisher mix differs from reference. Treat this as an instrumentation warning.")
        if t and (date.fromisoformat(w["date"]) - date.fromisoformat(windows[t - 1]["date"])).days != 1:
            warnings.append("Missing daily window. Do not interpret a gap as zero events.")
        coverage_ok = not warnings
        p = smoothed_counts(w["counts"]) if count else None
        z = ilr(p) if p is not None else None
        prediction = None
        raw = None
        rank = None
        frozen_error = None
        persistence_error = None
        covariance = None
        train_through = None
        residual = None
        if len(states) >= config.train_windows:
            states_recent, pos_recent = states[-config.trailing_windows:], positions[-config.trailing_windows:]
            beta = fit_ridge(states_recent, pos_recent, config.ridge)
            if frozen is None:
                frozen = beta.copy()
            prediction = np.r_[1, states[-1]] @ beta
            train_through = windows[positions[-1]]["date"]
            if z is not None:
                residual = z - prediction
                persistence_error = float(np.linalg.norm(z - states[-1]))
                frozen_error = float(np.linalg.norm(z - np.r_[1, states[-1]] @ frozen))
            if positions[-1] != t - 1:
                warnings.append("Previous usable state is not the preceding day. Surprise suppressed.")
                coverage_ok = False
            if len(residuals) >= config.covariance_min and residual is not None and coverage_ok:
                covariance = shrinkage_covariance(residuals[-config.trailing_windows:], config.covariance_floor)
                raw = float(np.sqrt(max(0, residual @ np.linalg.solve(covariance, residual))))
                if len(scores) >= config.rank_min:
                    rank = 100 * (1 + sum(s <= raw for s in scores[-config.trailing_windows:])) / (len(scores[-config.trailing_windows:]) + 1)
        rolling = np.mean(valid_shares[-30:], axis=0) if len(valid_shares) >= 30 else None
        current_js = jsd(p, reference) if p is not None else None
        current_ot = transport(p, reference, cost) if p is not None else None
        high = rank is not None and rank >= config.candidate_rank and coverage_ok
        recent_high.append(high)
        candidate = high and sum(recent_high[-3:]) >= 2 and t - last_alert >= config.cooldown
        if not coverage_ok:
            alert = {"state": "suppressed", "reason": " ".join(warnings)}
        elif candidate:
            alert = {"state": "candidate", "reason": "Two of three windows exceed the experimental 97.5th descriptive rank threshold. Not a verified world event or calibrated alarm."}
            last_alert = t
        elif t == last_alert + config.cooldown and not high:
            alert = {"state": "resolved", "reason": "Statistical candidate cooled down; this is not resolution of an actual world event."}
        else:
            alert = {"state": "none", "reason": "No sequential candidate under the experimental rule." if rank is not None else "Insufficient prior out-of-sample scores for a descriptive rank."}
        if t >= config.reference_windows:
            contributions = js_contributions(p, reference) if p is not None else np.zeros(k)
            output = {
                "date": w["date"], "phase": "training" if t < 45 else "calibration" if t < 120 else "evaluation",
                "unique_events": count, "raw_mentions": w["raw_mentions"], "source_count": len(w["sources"]),
                "coverage_ok": coverage_ok, "coverage_warnings": warnings, "source_js": source_js,
                "topic_shares": p.tolist() if p is not None else None, "reference_shares": reference.tolist(),
                "rolling_reference_shares": rolling.tolist() if rolling is not None else None,
                "js_topic": current_js, "transport_cost": current_ot,
                "rolling_js": jsd(p, rolling) if p is not None and rolling is not None else None,
                "rolling_transport": transport(p, rolling, cost) if p is not None and rolling is not None else None,
                "surprise_raw": raw, "surprise_percentile": rank, "calibration_n": len(scores[-config.trailing_windows:]),
                "calibration_valid": False, "surprise_interval": None,
                "forecast_shares": inverse_ilr(prediction).tolist() if prediction is not None else None,
                "forecast_train_through": train_through,
                "covariance_prior_residuals": min(len(residuals), config.trailing_windows),
                "alert": alert, "events": w.get("events", []),
                "domain_contributions": [dict(taxonomy[i], share=float(p[i]) if p is not None else None,
                    reference_share=float(reference[i]), js_contribution=float(contributions[i])) for i in range(k)],
                "baselines": {"persistence_error": persistence_error, "frozen_error": frozen_error,
                              "adaptive_error": float(np.linalg.norm(residual)) if residual is not None else None},
                "reference_id": ref_id,
                "reference_end": initial[-1]["date"],
            }
            # Conditional model interval only; does not include model/selection uncertainty.
            if prediction is not None and covariance is not None:
                draws = np.random.default_rng(t + 1234).multivariate_normal(prediction, covariance, 400)
                shares = softmax(draws @ helmert(k, full=False), axis=1)
                output["forecast_share_interval_80"] = np.quantile(shares, [.1, .9], axis=0).tolist()
            history.append(output)
        # Predict -> score -> update. Invalid observations never train covariance or the rank.
        if coverage_ok and z is not None:
            assert p is not None
            if residual is not None:
                residuals.append(residual)
            if raw is not None:
                scores.append(raw)
            states.append(z)
            positions.append(t)
            valid_shares.append(p)
        elif z is not None and count >= config.min_events and len(w["sources"]) >= config.min_sources and source_js is not None and source_js <= config.source_js_limit:
            assert p is not None
            # Recover after a one-day gap without using the gap residual for calibration.
            states.append(z)
            positions.append(t)
            valid_shares.append(p)
    version = "dataset_" + sha256(json.dumps(windows, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "schema_version": "1.0", "mode": mode, "title": "WORLDLINE / OBSERVER",
        "description": "Separate changes in reported event composition from unexpected observations and feed changes.",
        "generated_at": windows[-1]["date"] + "T23:59:59Z", "generated_at_meaning": "Deterministic replay cutoff, not wall-clock ingestion time",
        "model_version": MODEL_VERSION, "feature_version": FEATURE_VERSION, "data_version": version,
        "taxonomy": taxonomy, "transport_geometry": {"id": "declared-taxonomy-cost-v1", "matrix": cost.tolist(), "units": "taxonomy ground-cost units; not embedding distance"},
        "references": [
            {"id": "frozen", "label": "Frozen training reference", "description": f"Equal-weight mean of {len(initial)} daily compositions, {initial[0]['date']} to {initial[-1]['date']}. Version {ref_id}."},
            {"id": "rolling", "label": "Prior 30 usable windows", "description": "Trailing eligible windows, excluding the selected observation. Gaps can make this span longer than 30 calendar days."},
        ],
        "methodology": {
            "summary": "Fixed taxonomy; one vote per heuristic event cluster; alpha=.5 count smoothing; JSD in nats; exact taxonomy optimal transport; ILR ridge AR(1) and prior-residual covariance; descriptive historical rank.",
            "limitations": [
                "Synthetic observations demonstrate code behavior; they are not news or evidence of predictive skill.",
                "Descriptive percentiles are not shift probabilities, calibrated p-values or validated false-alarm rates.",
                "Coverage checks cannot eliminate unobserved reporting bias or establish source independence.",
                "Transport uses a declared topic ontology, not learned semantic embeddings.",
                "Experimental thresholds and conditional intervals have not been validated on real-world event labels.",
                "A frozen reference shows sustained displacement; adaptive surprise can fall as a new regime becomes expected.",
            ],
        }, "history": history, "experiments": {"summary": "Seeded controls and benchmark results are provided in research/results.json."},
    }
