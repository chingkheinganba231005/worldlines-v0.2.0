# ADR 001 — A coverage-aware, compositional observatory

Decision date: 2026-10-14. Status: accepted for the first reproducible release.

## Design challenge

The original proposal correctly distinguishes displacement, surprise and scenario impact. Its weakest point is observational identification: a news feed is an instrument, not a census of consequential events. More compute cannot recover unobserved events or make syndicated claims independent. A changing encoder, changing publisher mix, retrospective corrections and article-count weighting can all manufacture apparent world changes. A rank against historical errors is descriptive; it is not automatically calibrated under temporal dependence or a changing forecaster. We will not fuse unlike metrics into an arbitrary world-divergence percentage.

## Alternatives compared

| Design | Benefits | Failure modes | Decision |
|---|---|---|---|
| Topic/event distribution drift alone (JSD + transport) | Cheap, inspectable, stable representation | Cannot distinguish expected trend from surprise; source confounding | Retain as independent historical displacement |
| Forecast surprise/change detection alone | Conditional novelty; chronological evaluation | Normalizes persistent shifts; sensitive covariance and adaptation | Retain adaptive and frozen forecasts, not as sole output |
| Temporal event graph + semantic hybrid | Relationships and potentially rich explanations | Extraction instability, entity linkage errors, weak labels, expensive evaluation | Defer until simpler controls establish value |
| Source-aware compositional monitoring with an instrumentation control channel | Explicitly separates event composition from feed coverage, avoids singular simplex covariance, cheaply replayable | Cannot fully correct selection bias; requires stable source cohorts for adjustment | Adopt diagnostic channel and quality gating now; source-standardized estimation remains research |
| Fully Bayesian latent-world state-space model | Explicit observation/latent-state uncertainty | World-state identifiability and prior sensitivity remain unsolved by model complexity | Defer; useful future comparison, not a shortcut to truth |

## Chosen architecture and improvements

One Python statistical pipeline emits immutable, versioned JSON snapshots. A buildless accessible browser client consumes them; a read-only FastAPI service exposes the same snapshots for self-hosted deployments. SQLite stores ingestion/provenance and snapshot runs. Static deployment makes an inspectable public demonstration possible without ongoing compute or paid inference. The inference pipeline is the product core; the UI does not invent metric values.

1. Use fixed-topic counts with pseudocount smoothing and an orthonormal isometric log-ratio (ILR) basis. This handles composition geometry without a singular covariance in redundant coordinates.
2. Keep JSD (nats), exact small-taxonomy transport (declared ground-cost units), and empirical forecast-error rank separate. For this first demo the ground geometry is a transparent, versioned domain ontology, **not a pretrained semantic encoder**. It measures topic displacement, not nuanced meaning within a topic.
3. Generate forecasts before observing a window. Estimate residual covariance from prior out-of-sample residuals with shrinkage and a positive floor. Compare an adaptive ridge AR(1), a frozen ridge model and a persistence baseline. Preserve training/calibration timestamps.
4. A distinct channel monitors record volume, unique clusters, source-mix JSD and missing windows. Gate candidate signals on minimum samples and coverage continuity. This is a conservative diagnostic, not causal bias correction.
5. Show descriptive rank only after sufficient prior scores and always label real-world calibration unvalidated. No claimed false-alarm guarantee. Sequential candidate rules have explicit experimental thresholds, cooldown and provenance.
6. Include deterministic controls for a genuine synthetic composition break, syndicated duplication, source expansion and a coverage dropout. Numerical tests and simulations validate software behavior, not real-world predictive skill.
7. Separate synthetic broad-domain taxonomy from GDELT's sociopolitical CAMEO schema. Preserve DATEADDED as historical availability time. Never imply GDELT IDs are verified unique real-world events or publisher domains are independent confirmations.

## Retained

Two core measurements, honest demo/replay labels, event provenance, chronological replay, machine-readable API, reproducible fixtures, exact JSD/OT tests, operational docs and research protocol. Scenario impact remains unavailable with an explanation.

## Changed

Static-first release plus optional Python API instead of always-on frontend/backend infrastructure. ILR forecasting instead of naive Gaussian topic shares. Exact taxonomy transport instead of expensive high-dimensional Sinkhorn for small P0 histograms. A coverage warning channel rather than arbitrary statistical fusion. Browser-native UI rather than a framework dependency where no server rendering is needed.

## Deferred

Pretrained multilingual sentence encoders, fine-tuning, learned semantic transport, broad real-world coverage, validated alarms, causal scenarios, graphs, production scheduler, external indicator vintages and a 2019 baseline. A year selector without a real reference corpus would misrepresent the data. Expose only actually available frozen and rolling references.

## A100 decision

No GPU training is justified for this version. An A100 80 GB is useful later for batched frozen embeddings and, only after labeled benchmark construction, contrastive event-resolution fine-tuning or forecasting ablations. Keep encoder revision pinned and split documents chronologically before fitting anything. The GPU is not connected to this session; no training or hardware use is claimed.

## Trade-offs and validation

The reduced architecture is more reproducible and cheaper but less semantically expressive. It deliberately makes no research novelty/performance claim. Promote embeddings or graphs only if they improve held-out event-level precision at a fixed false-alert budget over persistence, volume and topic drift, with source-shift robustness and uncertainty. Keep contracts versioned so such a component can be added without changing metric meanings.

Primary sources and implementation checks are recorded in data_sources_and_rights.md and mathematics.md. See research/protocol.md for chronological validation requirements.
