# Reproducible synthetic experiment results

45 initial training windows. Calibration through day119. Evaluation days120–239. Thresholds fixed at calibration .975 quantile. Two of three exceedances plus seven-day cooldown. Synthetic episode matching only; not verified news.

**These are software checks on a synthetic generator, not evidence of research novelty or real-world skill.**

| Detector | Mean null candidates / 30 days | Injected episodes detected | Mean injected-case false candidates / 30 days |
|---|---:|---:|---:|
| Forecast surprise | 0.05 | 10 / 10 | 0.00 |
| Topic displacement | 0.15 | 10 / 10 | 0.00 |
| Raw news volume | 0.10 | 2 / 10 | 0.60 |

Do not assume the more sophisticated detector wins: both displacement and surprise have different targets. Read the per-seed tables and failed detections. The published dashboard uses a trailing descriptive rank rule, while this benchmark freezes a raw-score threshold from the dedicated calibration period; these are explicitly different alarm experiments.

Reproduce with `python scripts/evaluate.py --seeds 5`. Full thresholds, candidate dates, detection delays and forecast-error comparisons are in `results.json`.
