# WORLDLINE / OBSERVER

A working, reproducible research observatory that separates **historical event-pattern displacement**, **predictive surprise**, and **changes in data coverage**. It does not measure alternate universes or validated probabilities of crises.

## What works

- Responsive dashboard with chronological replay, frozen/rolling references, topic contributions, forecast intervals, event inspection, alert history and JSON downloads.
- CPU statistical engine: deduplication, fixed taxonomy, JSD, exact taxonomy transport, ILR ridge forecasts, prior-residual covariance, coverage gating and descriptive anomaly ranks.
- Deterministic 240-day synthetic stream; 210 displayed windows after the frozen reference. Every simulated observation is explicitly labeled.
- Separate real-data inspector: **3,414 provisional GDELT records**, four 01:30 UTC archive samples on October10–13,2026. These are small 15-minute samples, not four complete days of world events. Real-data anomaly scores are deliberately withheld.
- Read-only FastAPI, SQLite provenance/revisions, bounded GDELT backfill, tests, pinned dependencies, Docker, CI, experiment results and research documentation.

## Run locally

Python3.12 is the tested version. No API key, GPU or paid inference is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python scripts/bootstrap.py
python -m uvicorn worldline.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 . API documentation: http://127.0.0.1:8000/docs . The first request loads the selected snapshot and persists it in local SQLite. Use `python scripts/verify_deployment.py http://127.0.0.1:8000 --api` to verify a running server.

For the browser-only demonstration, the shipped `dist/` directory can be served by any static HTTP host. Opening `index.html` with `file://` is unsupported because the client fetches JSON. The hosted release serves versioned snapshots; it does **not** run live Python ingestion or auto-refresh the data.

## Reproduce and test

```bash
python scripts/replay.py
python -m pytest -q
python -m mypy backend/worldline
node --check dist/app.js
npm ci
npm test
python scripts/evaluate.py --seeds 5
python scripts/evaluate_real_sample.py
```

Node22+ is recommended for development checks; the deployed client needs no Node runtime. Tests cover metric identities, exact transport examples, deduplication, no future leakage, source/dropout suppression, parser failures, retry bounds, SQLite revisions, API validation and six DOM scenarios. DOM tests do not replace a rendered browser review. See `docs/validation.md` for actual release evidence.

## Acquire real metadata

```bash
python scripts/backfill.py --start 20261010013000 --slots 4 --daily --allow-gaps
python scripts/evaluate_real_sample.py
```

This re-fetches the same four bounded archives from official GDELT URLs. It never fetches publisher article bodies. `--latest` fetches one recent archive; `--archive /path/to/file.export.CSV.zip` accepts a downloaded official file. All records retain provider availability, actual retrieval timestamps and checksums. See `docs/provider_api.md` for bounds and caveats.

To serve the real sample through the Python API, set `WORLDLINE_SNAPSHOT_PATH` to its absolute JSON path. This changes API records; the browser deliberately retains its two distinct synthetic and real views. Setting a label does not turn a retrospective sample into a live service.

## Deploy

Static demonstration: deploy `dist/` unchanged. Python API: `docker compose up --build -d` and put the localhost-bound service behind an HTTPS reverse proxy. No paid resource is created by the repository. Host charges, scheduled jobs and retention need an explicit operational setup. See `docs/deployment.md` and `docs/operations.md`.

## Design decision and limitations

`docs/architecture_decision.md` compares five approaches and explains the chosen coverage-aware compositional model. The A10080GB is unnecessary for this baseline. A useful later GPU stage would extract pinned multilingual embeddings and test event-resolution quality on an audited held-out set.

This release is a **functional research MVP**, not a completed scientific claim. Deferred: real continuous monitoring, a validated historical baseline year, learned semantic embeddings, cross-ID real-event resolution, source independence verification, regional scoring, temporal graphs and scenario/causal models. The broad synthetic taxonomy must never be substituted for GDELT's sociopolitical CAMEO taxonomy. Thresholds and forecast intervals are experimental.

## Research record

Start with `research/results.md`, `research/real_sample_results.md`, `research/protocol.md`, `research/data_card.md`, `research/model_card.md`, and `paper/outline.md`. Synthetic benchmarks exercise code; the four-slot real comparison exercises ingestion and descriptive statistics. Neither establishes top-journal novelty or real-world forecasting superiority.

Code: MIT. Original synthetic metadata: CC0. GDELT metadata: attribution to **The GDELT Project**, with linked publisher rights retained. See `LICENSE` and `docs/data_sources_and_rights.md`.
