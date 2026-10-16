# System boundaries

`backend/worldline/ingest.py` validates original GDELT archives; `storage.py` retains provider revisions, archive hashes and immutable snapshots. `demo.py` generates original synthetic records. `core.py` performs deterministic clustering, observations, references, forecasting and scores. `scripts/replay.py` serializes the same result consumed by the static client and FastAPI.

The browser performs presentation and filtering, not model fitting. `dist/app.js` has no API key or generated fallbacks. It fetches `demo.json` for computed synthetic metrics and lazily fetches `gdelt_sample.json` for the separate real-record inspector. Synthetic events are never blended with actual source records.

The optional Python API exposes read-only views of one selected snapshot. SQLite permits idempotent record revision storage and immutable replay audit. Static hosting consumes only the public `dist/` output; raw ZIPs, SQLite and local runtime state are not published.

Future learned embeddings require a new feature/model/reference version, compatible historical computation, and evidence against this baseline. Keep each metric's semantics stable or increment the schema version. Scenario features must remain separate from descriptive observational signals.
