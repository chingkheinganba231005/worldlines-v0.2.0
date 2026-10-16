"""Run validation protocol v2.0 and render research/results.{json,md}."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .monitor import Config
from .reference import place_name
from .validate import (PRIMARY_CATEGORIES, PROTOCOL_VERSION, WINDOW_AFTER, WINDOW_BEFORE, alarm_metrics, auc_null,
                       bootstrap_auc, calibration_on_quiet_days, circular_shift_null, label_index, naive_volume_spike,
                       safe, stratified_auc, unusualness, window_max_array, z_to_unusualness)

DETECTORS = [
    ("D0", "Random scores"),
    ("D1", "Naive news-volume spike"),
    ("D2", "Attention channel"),
    ("D3", "Event-mix channel"),
    ("D4", "Conflict channel"),
    ("D5", "WORLDLINE combined (published)"),
    ("D6", "Combined + learned semantic channel"),
]


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return safe(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


CHANNELS = {"D2": "p_attention", "D3": "p_mix", "D4": "p_conflict"}


def dev_weights(dev_results: dict) -> dict[str, float]:
    """Declared rule (v2.1): weight each channel by its development-period AUC excess over chance."""
    raw = {CHANNELS[k]: max(dev_results["detectors"][k]["auc_primary"] - 0.5, 0.0) for k in CHANNELS}
    total = sum(raw.values())
    if total <= 0:
        return {k: 1 / len(raw) for k in raw}
    return {k: v / total for k, v in raw.items()}


def weighted_combination(country: dict, weights: dict[str, float]) -> np.ndarray:
    """Weighted Cauchy combination per country-day; weights renormalized over available channels."""
    from .stats import cauchy_combination
    keys = [k for k, w in weights.items() if w > 0]
    stack = np.stack([country[k] for k in keys], axis=-1)
    out = np.full(stack.shape[:2], np.nan)
    w = np.array([weights[k] for k in keys])
    for t, m in zip(*np.nonzero(np.isfinite(stack).any(-1))):
        ok = np.isfinite(stack[t, m])
        out[t, m] = cauchy_combination(list(stack[t, m][ok]), list(w[ok]))
    return out


def detector_pvalues(panel, country: dict, seed: int = 20240101) -> dict[str, np.ndarray]:
    from scipy.stats import norm
    scored = np.isfinite(country["p_combined"])
    rng = np.random.default_rng(seed)
    random_p = np.where(scored, rng.uniform(size=scored.shape), np.nan)
    naive_z = naive_volume_spike(panel.c_total, panel.usable, country["members"])
    out = {"D0": random_p, "D1": np.where(scored, norm.sf(naive_z), np.nan), "D2": country["p_attention"],
           "D3": country["p_mix"], "D4": country["p_conflict"], "D5": country["p_combined"]}
    if "p_combined_semantic" in country:
        out["D6"] = country["p_combined_semantic"]
    return {k: np.where(scored, v, np.nan) for k, v in out.items()}


def random_auc_distribution(scored, labels, test, draws: int = 200, seed: int = 10_000) -> dict:
    """Random-score AUC over many draws: the honest way to report a chance baseline."""
    from .validate import _negatives
    negatives = _negatives(labels, scored, test)
    draws_auc = []
    for k in range(draws):
        rng = np.random.default_rng(seed + k)
        p = np.where(scored, rng.uniform(size=scored.shape), np.nan)
        draws_auc.append(stratified_auc(window_max_array(unusualness(p), scored), scored, labels, test, negatives=negatives)[0])
    values = np.array(draws_auc)
    return {"draws": draws, "mean": float(values.mean()), "sd": float(values.std()),
            "q025": float(np.quantile(values, 0.025)), "q975": float(np.quantile(values, 0.975))}


def run_validation(panel, country: dict, instrument: dict, label_events: list[dict], cfg: Config, *,
                   test_start: str = "2024-01-01", test_end: str | None = None, quick: bool = False,
                   extra: dict[str, tuple[str, np.ndarray]] | None = None,
                   alarm_gate: dict[str, np.ndarray] | None = None, published: str = "D5") -> dict:
    dates = panel.dates
    scored = np.isfinite(country["p_combined"])
    last = max(d for d, ok in zip(dates, scored.any(1)) if ok)
    if test_end:
        last = min(last, test_end)
    test = np.array([test_start <= d <= last for d in dates])
    countries = country["countries"]
    primary = label_index(label_events, dates, countries, categories=PRIMARY_CATEGORIES, start=test_start, end=last)
    everything = label_index(label_events, dates, countries, categories=None, start=test_start, end=last)
    disaster = label_index(label_events, dates, countries, categories=("disaster",), start=test_start, end=last)
    degraded = instrument["degraded"]
    pvals = detector_pvalues(panel, country)
    detectors = list(DETECTORS)
    for key, (name, values) in (extra or {}).items():
        pvals[key] = np.where(scored, values, np.nan)
        detectors.append((key, name))
    W = {k: window_max_array(unusualness(p), scored) for k, p in pvals.items()}
    perms_auc, perms_prec, reps = (40, 200, 60) if quick else (200, 1000, 300)
    budget_alarms = int(((pvals["D5"] <= 1 / cfg.tiers[0]) & scored & ~degraded[:, None] & test[:, None]).sum())
    results = {}
    for key, name in detectors:
        if key not in pvals:
            continue
        auc, per_member = stratified_auc(W[key], scored, primary, test)
        entry = {"name": name, "auc_primary": auc,
                 "auc_all_labels": stratified_auc(W[key], scored, everything, test)[0],
                 "auc_disaster_labels": stratified_auc(W[key], scored, disaster, test)[0],
                 "auc_null": auc_null(W[key], scored, primary, test, permutations=perms_auc),
                 "auc_bootstrap": bootstrap_auc(W[key], scored, primary, test, reps=reps,
                                                other=W["D1"] if key in ("D5", "D6") else None),
                 "tiers": {}}
        if key == "D6":
            entry["vs_D5"] = bootstrap_auc(W["D6"], scored, primary, test, reps=reps, other=W["D5"])
        if key == "D5":
            entry["vs_D2"] = bootstrap_auc(W["D5"], scored, primary, test, reps=reps, other=W["D2"])
            entry["per_country"] = {countries[m]: {"auc": a, "labels": n} for m, (a, n) in per_member.items() if n >= 5}
        entry["matched_budget"] = matched_budget(pvals[key], budget_alarms, scored, degraded, primary, test)
        for tier_name, period in zip(("notable", "rare", "extreme"), cfg.tiers):
            alarm = (pvals[key] <= 1 / period) & scored & ~degraded[:, None]
            if alarm_gate and key in alarm_gate:
                alarm &= alarm_gate[key]
            metrics = alarm_metrics(alarm, scored, primary, test)
            metrics["permutation"] = circular_shift_null(alarm, scored, primary, test, permutations=perms_prec)
            metrics["alarms_per_country_year"] = metrics["alarms"] / max(len(countries), 1) / (test.sum() / 365.25)
            entry["tiers"][tier_name] = metrics
        results[key] = entry
    calibration = calibration_on_quiet_days(pvals[published], everything, test)
    calibration["detector"] = published
    chance = random_auc_distribution(scored, primary, test, draws=40 if quick else 200)
    gate = (alarm_gate or {}).get(published)
    examples = alarm_examples(panel, country, pvals[published], degraded if gate is None else (degraded[:, None] | ~gate),
                              label_events, test, cfg)
    return _clean({
        "protocol": PROTOCOL_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_period": [test_start, last], "test_days": int(test.sum()), "monitored_countries": len(countries),
        "window_days": [-WINDOW_BEFORE, WINDOW_AFTER],
        "labels": {"primary": sum(1 for t, _ in primary.positives if test[t]),
                   "all": sum(1 for t, _ in everything.positives if test[t]),
                   "disaster": sum(1 for t, _ in disaster.positives if test[t])},
        "scored_country_days": int((scored & test[:, None]).sum()),
        "detectors": results, "calibration_quiet_days": calibration, "examples": examples, "quick": quick,
        "random_auc": chance})


def matched_budget(p: np.ndarray, budget: int, scored, degraded, labels, test) -> dict:
    """Precision/recall when each detector raises exactly `budget` test alarms (its top-ranked cells)."""
    eligible = scored & ~degraded[:, None] & test[:, None] & np.isfinite(p)
    values = np.sort(p[eligible])
    if not len(values) or budget <= 0:
        return {"budget": budget}
    cut = values[min(budget, len(values)) - 1]
    alarm = eligible & (p <= cut)
    metrics = alarm_metrics(alarm, scored, labels, test)
    return {"budget": budget, "alarms": metrics["alarms"], "precision": metrics["precision"],
            "lift": metrics["lift"], "recall": metrics["recall"]}


def alarm_examples(panel, country, p, degraded, label_events, test, cfg, limit: int = 25) -> list[dict]:
    """Most extreme test-period alarms, each with any matching Wikipedia entry (for the research record)."""
    countries = country["countries"]
    by_country_date: dict[tuple[str, str], list[str]] = {}
    for event in label_events:
        for iso in event["countries"]:
            by_country_date.setdefault((iso, event["date"]), []).append(event["text"])
    blocked = degraded if degraded.ndim == 2 else np.repeat(degraded[:, None], p.shape[1], axis=1)
    cells = [(float(p[t, m]), t, m) for t, m in zip(*np.nonzero(np.isfinite(p) & test[:, None] & ~blocked))]
    cells.sort()
    seen, out = set(), []
    for value, t, m in cells:
        key = (countries[m], panel.dates[t][:7])
        if key in seen:
            continue
        seen.add(key)
        matches = []
        for offset in range(-WINDOW_AFTER, WINDOW_BEFORE + 1):
            other = t + offset
            if 0 <= other < panel.T:
                matches += by_country_date.get((countries[m], panel.dates[other]), [])
        out.append({"date": panel.dates[t], "country": countries[m], "name": place_name(countries[m]),
                    "return_period_days": 1 / max(value, 1e-9), "wikipedia_match": matches[:2],
                    "outlets": int(country["outlets"][t, m]) if "outlets" in country else None})
        if len(out) >= limit:
            break
    return out


def _ordered(d: dict):
    return [(k, d[k]["name"]) for k in sorted(d)]


def render_markdown(results: dict) -> str:
    d = results["detectors"]
    lines = ["# WORLDLINE v0.2 — real-data validation results", "",
             f"Protocol `{results['protocol']}` (see `research/protocol.md`). Generated {results['generated_at']}.", "",
             f"* Test period: **{results['test_period'][0]} → {results['test_period'][1]}** ({results['test_days']} days), "
             f"{results['monitored_countries']} monitored countries, {results['scored_country_days']:,} scored country-days.",
             f"* Labels (Wikipedia year articles, country-tagged): {results['labels']['primary']} sociopolitical "
             f"(primary), {results['labels']['all']} all, {results['labels']['disaster']} disaster.",
             f"* Hit window: alarm from {results['window_days'][0]} to +{results['window_days'][1]} days around the listed date.", "",
             "## Threshold-free discrimination (primary labels)", "",
             "| Detector | AUC | 95% CI | Shift-null mean | Permutation p |", "|---|---:|---:|---:|---:|"]
    chance = results.get("random_auc")
    for key, name in _ordered(d):
        e = d[key]
        ci = e["auc_bootstrap"]["auc_ci95"]
        if key == "D0" and chance:
            lines.append(f"| D0 Random scores ({chance['draws']} draws) | {chance['mean']:.3f} | {chance['q025']:.3f}–{chance['q975']:.3f} | — | — |")
            continue
        lines.append(f"| {key} {name} | {e['auc_primary']:.3f} | {ci[0]:.3f}–{ci[1]:.3f} | "
                     f"{e['auc_null']['null_mean']:.3f} | {e['auc_null']['p_value']:.4f} |")
    lines += ["", "AUC = probability that a labelled country-date window has a higher maximum unusualness than an "
              "unlabelled day of the same country. 0.5 is chance.", "", "## Paired comparisons", ""]
    if "D5" in d:
        b = d["D5"]["auc_bootstrap"]
        lines.append(f"* **D5 − D1 (WORLDLINE vs naive volume spike):** {b['difference_mean']:+.3f} "
                     f"(95% CI {b['difference_ci95'][0]:+.3f} to {b['difference_ci95'][1]:+.3f}).")
        v = d["D5"]["vs_D2"]
        lines.append(f"* **D5 − D2 (adding event-mix and conflict channels to attention):** {v['difference_mean']:+.3f} "
                     f"(95% CI {v['difference_ci95'][0]:+.3f} to {v['difference_ci95'][1]:+.3f}).")
    if "D6" in d:
        v = d["D6"]["vs_D5"]
        lines.append(f"* **D6 − D5 (adding the learned semantic channel):** {v['difference_mean']:+.3f} "
                     f"(95% CI {v['difference_ci95'][0]:+.3f} to {v['difference_ci95'][1]:+.3f}).")
    lines += ["", "## Precision at a matched alarm budget", "",
              f"Each detector raises exactly as many test alarms as D5's notable tier ({d['D5']['matched_budget']['budget']}), "
              "taking its most unusual country-days. This removes differences in alarm rates.", "",
              "| Detector | Precision | Lift | Recall |", "|---|---:|---:|---:|"]
    for key, name in _ordered(d):
        if "precision" not in d[key]["matched_budget"]:
            continue
        mb = d[key]["matched_budget"]
        lines.append(f"| {key} {d[key]['name']} | {mb['precision']:.3f} | {mb['lift']:.2f}× | {mb['recall']:.3f} |")
    lines += ["", "## Alarms (primary labels)", "",
              "| Detector | Tier | Alarms / country-year | Precision | Base rate | Lift | Shift-null precision (p) | Recall |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for key, name in _ordered(d):
        for tier, m in d[key]["tiers"].items():
            perm = m["permutation"]
            lines.append(f"| {key} | {tier} | {m['alarms_per_country_year']:.2f} | {m['precision']:.3f} | {m['base_rate']:.3f} | "
                         f"{m['lift']:.2f}× | {perm['null_mean']:.3f} (p={perm['p_value']:.4f}) | "
                         f"{m['labels_detected']}/{m['labels']} = {m['recall']:.3f} |")
    c = results["calibration_quiet_days"]
    lines += ["", "## Calibration on presumed-quiet country-days", "",
              f"On {c['n']:,} test country-days with no Wikipedia entry for that country within ±7 days: "
              f"P(p ≤ 0.05) = {c['share_p_le_0.05']:.4f}, P(p ≤ 0.01) = {c['share_p_le_0.01']:.4f}, "
              f"P(p ≤ 0.001) = {c['share_p_le_0.001']:.5f} (nominal 0.05, 0.01, 0.001; detector {c.get('detector', 'D5')}). Quiet days still contain real "
              "but unlisted events, so excess here is an upper bound on miscalibration.", "",
              "## Most extreme test-period alarms of the published detector (one per country-month)", "",
              "Return periods beyond 5,000 days are extrapolations of the fitted tail and are shown as ≥ 5,000.", "",
              "| Date | Country | Return period (days) | Outlets | Matching Wikipedia entry (±window) |", "|---|---|---:|---:|---|"]
    for ex in results["examples"]:
        match = ex["wikipedia_match"][0][:140].replace("|", "/") if ex["wikipedia_match"] else "—"
        period = "≥ 5,000" if ex["return_period_days"] >= 5000 else f"{ex['return_period_days']:,.0f}"
        lines.append(f"| {ex['date']} | {ex['name']} | {period} | {ex.get('outlets') or '—'} | {match} |")
    if "D5" in d and d["D5"].get("per_country"):
        lines += ["", "## Per-country AUC (D5, countries with ≥ 5 primary labels)", "", "| Country | Labels | AUC |", "|---|---:|---:|"]
        for iso, v in sorted(d["D5"]["per_country"].items(), key=lambda kv: -kv[1]["labels"]):
            lines.append(f"| {place_name(iso)} | {v['labels']} | {v['auc']:.3f} |")
    published = results.get("published")
    if published:
        lines += ["", "## The published v2.1 detector (D7)", "", published["description"]]
    dev = results.get("development")
    if dev:
        lines += ["", "## Development period (2023) and the v2.1 redesign", "",
                  f"Development labels: {dev['labels']['primary']} sociopolitical entries, {dev['test_period'][0]} → {dev['test_period'][1]} "
                  "(p-values exist from roughly mid-2023 after warm-up).", "",
                  "| Detector | Dev AUC |", "|---|---:|"]
        for key, name in _ordered(dev["detectors"]):
            lines.append(f"| {key} {name} | {dev['detectors'][key]['auc_primary']:.3f} |")
        lines += ["", dev.get("note", "")]
    lines += ["", "## Reading these numbers", "",
              "* Labels are an independent but incomplete and Western-weighted record; many alarms concern real events "
              "Wikipedia's year articles do not list, so precision here is a conservative lower bound.",
              "* Return periods come from conformal ranks with a generalized-Pareto tail; on real data they are "
              "approximately, not exactly, calibrated (see the calibration section).",
              "* Nothing here is a forecast of future events: alarms describe unusual reporting patterns as they happen.",
              "", "Reproduce: `python -m worldline.cli evaluate` (writes `research/results.json` and this file)."]
    return "\n".join(lines) + "\n"


def write_results(results: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (directory / "results.md").write_text(render_markdown(results), encoding="utf-8")


# ----------------------------------------------------------------------------- full protocol
PUBLISHED_VERSION = "worldline-v2.1"
MIN_OUTLETS = 20


def derive_published(dev_results: dict) -> dict:
    """The v2.1 detector, derived from development-period results only (deterministic)."""
    auc = {k: dev_results["detectors"][k]["auc_primary"] for k in ("D2a", "D3", "D4")}
    raw = {"p_articles": max(auc["D2a"] - 0.5, 0.0), "p_mix": max(auc["D3"] - 0.5, 0.0), "p_conflict": max(auc["D4"] - 0.5, 0.0)}
    total = sum(raw.values()) or 1.0
    return {"version": PUBLISHED_VERSION, "weights": {k: v / total for k, v in raw.items()}, "min_outlets": MIN_OUTLETS,
            "dev_auc": auc, "rule": "weight = max(dev AUC - 0.5, 0), normalized; alarms need >= 20 outlets and a healthy instrument"}


def published_pvalues(country: dict, model: dict) -> np.ndarray:
    return weighted_combination(country, model["weights"])


def run_protocol(analysis, label_events: list[dict], *, quick: bool = False) -> tuple[dict, dict]:
    panel, country, cfg = analysis.panel, analysis.country, analysis.cfg
    instrument = analysis.global_["instrument"]
    extra_dev = {"D2a": ("Attention in articles", country["p_articles"])}
    dev = run_validation(panel, country, instrument, label_events, cfg, test_start=cfg.dev_start, test_end=cfg.dev_end,
                         quick=True, extra=extra_dev)
    model = derive_published(dev)
    p_v21 = published_pvalues(country, model)
    gate = country["outlets"] >= model["min_outlets"]
    extra = {"D2a": ("Attention in articles (post hoc)", country["p_articles"]),
             "D7": ("WORLDLINE v2.1 published (post hoc)", p_v21)}
    results = run_validation(panel, country, instrument, label_events, cfg, quick=quick, extra=extra,
                             alarm_gate={"D7": gate}, published="D7")
    w = model["weights"]
    results["published"] = {"detector": "D7", **model, "description":
        "Weighted Cauchy combination of attention measured in distinct articles (weight %.2f), event mix (%.2f) and conflict "
        "share (%.2f); alarms additionally require at least %d distinct outlets that day and a healthy instrument. Every design "
        "choice was made on 2023 development data after the pre-registered run (D0–D6) showed that equal weighting diluted the "
        "attention channel. **Its test-period numbers are therefore post hoc and optimistic**; its unbiased evaluation is the "
        "prospective live track record that starts on 2026-10-16. Attention alone (D2a) ranks slightly better (higher AUC) in "
        "both development and test; v2.1 keeps the event-mix and conflict channels at small weights so that a change in the "
        "*kind* of news, not only its volume, can raise an alarm." % (w["p_articles"], w["p_mix"], w["p_conflict"], model["min_outlets"])}
    results["development"] = {"test_period": dev["test_period"], "labels": dev["labels"], "detectors": dev["detectors"],
                              "note": "Development rule: weight each channel by max(dev AUC − 0.5, 0); attention unit (articles "
                                      "vs events) and outlet gate (0/5/10/20) chosen by development AUC and precision."}
    return results, model
