# Release validation evidence

Checked in the build environment on2026-10-14. These are actual executed checks; no browser screenshot or Docker execution is claimed.

| Check | Actual result |
|---|---|
| `python -m pytest -q` | **27 passed**; one Starlette/httpx test-client deprecation warning |
| `python -m mypy backend/worldline` | **Success: no issues found in7 source files** |
| `npm test` | **6 DOM smoke tests passed** using jsdom26.1.0 |
| `node --check dist/app.js` | Passed |
| `python scripts/replay.py` | 210 displayed windows after30 reference windows; deterministic data version `dataset_99414ed3a452d6b8`; dashboard candidate2025-06-21 |
| Python API smoke checks | `/`, `/ready`, `/api/v1/status`, current/history metrics, events, alerts, references, methodology all returned200 |
| Real GDELT adapter | All4 requested archives acquired; 3,414 distinct provider records; no acquisition gaps |
| `python scripts/evaluate.py --seeds 5` | Five null and five injected streams, three detectors; full results stored |
| `python scripts/evaluate_real_sample.py` | Four bounded real metadata comparisons with source-mix diagnostics; forecasting withheld |

Readiness response:

```json
{"mode":"synthetic_demo","data_as_of":"2025-08-28","generated_at":"2025-08-28T23:59:59Z","data":{"status":"ready","history_windows":210}}
```

Test coverage includes exact JSD/transport values and invariances, ILR inversion, duplicate-syndication invariance, safe clustering constraints, no-future-leakage and unchanged own forecast, source-shift/dropout suppression, synthetic break detection, insufficient references, empty windows, malformed GDELT schemas, archive/path guards, retries/circuit, SQLite revisions and immutability, invalid/missing API inputs, disabled mutations, installed-package asset-root resolution, UI loading/error/retry, replay/filter/reference controls, missing values, source-link safety and real/synthetic isolation.

Verification limits: the environment has no permitted control-browser capability, so native rendered browser/mobile layout QA was not run; jsdom validates DOM behavior only. Docker executable was unavailable, so the Dockerfile/Compose configuration was not executed. Current dependency tests emit a Starlette warning about future `httpx2` migration; the existing client tests pass and dependency versions are pinned. No GPU was connected or used. No real-world forecast calibration or causal model was validated.

Publication success and source commit are reported by the deployment system at release; a registered expected URL alone is not evidence of deployment.
