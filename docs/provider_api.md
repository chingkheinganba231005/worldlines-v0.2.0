# GDELT ingestion and read-only service

The real adapter fetches **GDELT 2.0 Events metadata only** from official HTTPS archive URLs. It never downloads linked news articles. A supplied local official ZIP is supported when network access is unavailable. The included `data/fixtures/gdelt_toy.tsv` is explicitly synthetic test input; it is never mixed into real snapshots.

## Reproduce

```bash
python scripts/backfill.py --latest
python scripts/backfill.py --start 20250101000000 --slots 4
python scripts/backfill.py --start 20261010013000 --slots 4 --daily --allow-gaps
python scripts/backfill.py --archive /path/to/20250101000000.export.CSV.zip
PYTHONPATH=backend uvicorn worldline.api:app --host 0.0.0.0 --port 8000
python scripts/verify_deployment.py http://localhost:8000 --api
```

`--slots` defaults to one and is limited to 31 contiguous 15-minute files. `--daily` instead samples the same UTC 15-minute slot on successive days and is capped at four files. `--allow-gaps` permits publication of successful files while listing every failed archive, requested count, received count and completeness ratio; it never implies complete days. A four-slot sample is **one hour of provider insertions**, never a whole day. Archive completeness of 1 means all requested tiny samples were received, not full daily coverage. No full-history performance or calibration claim follows from this sample. Backfill errors are explicit nonzero exits; no synthetic fallback occurs. Without `--allow-gaps`, a failed multi-file run can leave successfully downloaded records in SQLite, but never publishes a partial output JSON. Rerunning is idempotent. SHA-256-named archives in `data/raw` preserve provenance. Ignore local SQLite and raw archives in source control as configured by the repository.

`dist/data/gdelt_sample.json` is a separately labeled `historical_sample`; `dist/data/demo.json` remains the synthetic broad-domain statistical demonstration. Set `WORLDLINE_SNAPSHOT_PATH` to the real JSON to serve its records through the API. Real sample metrics are null with an explicit reason: insufficient historical coverage and no compatible CAMEO reference. The real and synthetic taxonomies must not be mixed. `WORLDLINE_DB_PATH` overrides `data/worldline.sqlite`. Startup imports cause no ingestion or database writes. Reading the first valid snapshot initializes SQLite and stores the snapshot immutably.

## Schema and timestamp integrity

The parser requires the official 61-field GDELT 2.0 Events layout (tab-separated despite `.CSV`). It keeps every field under `raw_metadata`. Zero-based indices: SQLDATE=1, DATEADDED=59, SOURCEURL=60. SQLDATE is occurrence day with midnight used as a representation, **not exact occurrence time**. DATEADDED is provider insertion/availability time. `observed_at_utc` and `ingested_at_utc` preserve actual pipeline retrieval and processing times. Article publication time and original language are unknown in this Events-only adapter; Mentions integration is future work. Historical availability replay assumes archived DATEADDED accurately reflects provider availability and does not claim our pipeline observed those records at the time. If provider availability is later than our retrieval clock, a credibility flag explicitly records clock skew or a provider timestamp issue; neither timestamp is silently rewritten.

`label` is explicitly marked `generated_actor_action_label`: actor name → CAMEO code → actor name. It is not an article headline or a verified assertion. SOURCEURL can be a citation; only valid HTTP(S) links become clickable `source_url`. Publisher domain is metadata. NumSources is publisher/source diversity and **never independent confirmation**. All records remain provisional, with `independent_source_count=null`. Provider record IDs provide record-level deduplication only; they do not establish unique real events. Store revisions under `(provider, source ID, row checksum)` rather than erasing them. The current sample uses one row per provider ID; this is not a validated semantic clustering method.

Snapshot shape:

```text
mode, generated_at, data_as_of, archives[], references[], methodology,
history[{date, events[], cameo_root_counts, provider_record_count,
         js_topic:null, transport_cost:null, predictive_surprise:null,
         alert:null, coverage_status, metric_unavailable_reason}]
```

## API contracts

All API responses, including errors, carry `mode`, `data_as_of`, `generated_at` and `data`. Liveness can have `mode=unavailable` before a snapshot has been loaded. `/ready` confirms valid snapshot and writable persistence. There are no write/admin routes, keys or user accounts.

| Route | Content |
|---|---|
| `GET /health` | Liveness |
| `GET /ready` | Snapshot readiness |
| `GET /api/v1/status` | Mode, snapshot checksum, history count |
| `GET /api/v1/metrics/current` | Latest observed metric window |
| `GET /api/v1/metrics/history` | Bounded replay windows; `/api/v1/history` alias |
| `GET /api/v1/events` | Paginated event observations |
| `GET /api/v1/events/{id}` | Specific observation or 404 |
| `GET /api/v1/alerts` | Candidate, corroborated or resolved entries |
| `GET /api/v1/references` | Available reference versions |
| `GET /api/v1/methodology` | Declared formulas, scope and limits |

History/events support optional inclusive `start=YYYY-MM-DD`, `end=YYYY-MM-DD`, `domain`, `limit` and `offset`. Alerts support start/end. Invalid dates, reversed bounds, unknown parameters/domains and out-of-range pagination return 422. Missing IDs return 404. Missing or invalid data/storage returns 503. Domain filtering selects observations; global metrics remain explicitly global. Metrics are not silently recomputed from filtered rows. History is capped at 3,660 windows and events at 1,000 records per response. `/docs` exposes OpenAPI documentation.

## Acquisition bounds and remaining operations work

Downloads permit only the exact official HTTPS host and matching Events paths. Redirects are refused, downloads capped at 16 MiB, ZIP expansion at 64 MiB and 250x, and archives must have exactly one expected root-level TSV member. Parsing never extracts ZIP members to disk. Retry at most three attempts for 429/5xx and transient network errors, with short exponential jitter; three failed fetch calls open a process-local 60-second circuit. This is a bounded research CLI, not a distributed rate-limited production collector. Add shared rate control, monitored scheduling, backups, error budgets and disk-retention policy before continuous operations. No full-text redistribution or API keys are involved.

## Verified source documentation

- [GDELT 2.0 Event codebook](https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf), layout, day resolution, DATEADDED and SOURCEURL.
- [GDELT data access](https://www.gdeltproject.org/data.html), Events/Mentions separation and update files.
- [GDELT terms](https://www.gdeltproject.org/about.html), dataset usage and attribution; these do not grant ownership of linked publisher full text.

Consulted 2026-10-14. The first connectivity check fetched 1,252 metadata rows from `20261014013000.export.CSV.zip`. The delivered comparison sample subsequently fetched all four requested 01:30 UTC archive slots on 2026-10-10 through 2026-10-13, totaling 3,414 provider records. Full manifests and content checksums are in the sample JSON. This demonstrates working acquisition and parsing, not substantive verification of those event assertions.
