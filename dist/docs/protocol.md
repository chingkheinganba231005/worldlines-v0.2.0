# Research protocol, version 0.1

This release is an engineering baseline, not a validated early-warning system or a publishable-results claim.

## Questions

1. At the same verified-event false-alert budget, does composition-aware forecast surprise add useful detections beyond topic displacement, volume and persistence?
2. How much apparent displacement is explained by publisher/language/coverage changes?
3. Does adding frozen multilingual event embeddings or temporal relations improve out-of-time results enough to justify cost and extraction errors?

## Locked evaluation design

Before fitting any learned representation, fix the provider acquisition policy, publication/availability timestamps, taxonomy, event-resolution protocol and source strata. Split training, calibration and final evaluation chronologically, with embargoes for revised/syndicated documents. Build an independently adjudicated impact-event set with documented inclusion rules and blinded annotators; do not choose memorable crises after inspecting scores. Measure disagreement and include ordinary negative periods.

Report event-level precision/recall at a fixed false-alerts-per30-days budget, detection delay, alarm duration, deduplication pair precision/recall, uncertainty coverage, forecast proper scoring rules where supported, source-missing mass, computation cost and language/region coverage. Use time-block resampling, separate false-candidate rates from event precision, and disclose all experiments tried. A descriptive score rank is not itself calibration.

## Baselines and ablations

Retain volume, JSD, declared taxonomy OT, persistence, frozen ridge, adaptive ridge, and a sequential detector such as validated CUSUM/ADWIN. Later compare a fixed-source-cohort estimator, energy distance/MMD, pretrained embeddings and graph signals. Do not report an MMD gain as an improvement over OT without matching samples and tuning budgets.

Stress-test syndication multiplied100fold, new publisher pools, missing archives, language expansion, publication delays, title paraphrases, entity collisions, sample-size changes, seasonal cycles, instrument version changes and gradual versus abrupt breaks. Include held-out regimes where the model loses to the simpler baseline.

## Executed experiments

`python scripts/evaluate.py --seeds 5` runs five null and five injected synthetic streams. Calibration is chronologically before evaluation; candidate thresholds are frozen for this benchmark. Results and per-seed dates are in `results.json`, `results.csv`, and `results.md`. These demonstrate implementation behavior only.

`python scripts/evaluate_real_sample.py` compares four genuine same-UTC-slot metadata samples descriptively, including publisher-mix differences. It does not produce forecast scores, impact labels or evidence of causal importance. See `real_sample_results.md` for counts and explicit limitations.

## A100 roadmap and go/no-go

Use the A10080GB only after a corpus, lawful data policy and held-out benchmark exist. First batch frozen multilingual embeddings with a pinned revision and saved checksums. Evaluate clustering against audited duplicate/nonduplicate pairs. Train a contrastive encoder only if representation errors remain a bottleneck, and compare against the frozen encoder with the same timestamp split. Do not train a large language model from scratch for this task. GPU throughput is not evidence of scientific validity.

## Publication decision

A paper requires real chronological validation, appropriate uncertainty, baseline comparison, negative cases, reproducible source/model versioning and a contribution beyond combining standard metrics in a dashboard. This repository provides infrastructure and an explicit hypothesis, not proof of novelty.
