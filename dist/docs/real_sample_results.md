# Bounded real-data experiment

Descriptive metadata comparison, not validated historical displacement or surprise.

One 15-minute archive at the same UTC slot per day. Incomplete daily coverage.

| UTC date | Provider records | Publisher domains | Topic JSD (nats) | Taxonomy OT | Source-mix JSD (nats) |
|---|---:|---:|---:|---:|---:|
| 2026-10-10 | 1193 | 96 | 0.0000 | 0.0000 | 0.0000 |
| 2026-10-11 | 731 | 51 | 0.0104 | 0.0812 | 0.5864 |
| 2026-10-12 | 688 | 55 | 0.0122 | 0.0637 | 0.6487 |
| 2026-10-13 | 802 | 87 | 0.0087 | 0.0621 | 0.6612 |

All comparisons use the first small archive as reference. These exploratory numbers are **not** promoted to dashboard historical displacement, anomaly percentiles or alerts. Large source-mix differences make apparent topic shifts especially hard to interpret.

Five sanity checks: fixed UTC slot; strictly distinct provider IDs after deduplication; codebook-validated root codes; archive checksums retained; no publisher fulltext or verified-event claims. Forecasting is withheld because history is inadequate.

Reproduce after acquiring the sample with `python scripts/evaluate_real_sample.py`. Exact metadata and caveats are in `real_sample_results.json`.
