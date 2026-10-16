# Deployment

## Static release

The initial release is the complete `dist/` directory hosted through Sites. It contains an interactive client, computed synthetic snapshots, a bounded real-data metadata sample, methodology and downloadable source. Site identity is retained in `.openai/hosting.json`; source is synchronized through the Sites workflow and exact committed output packaged before deployment. The static release has no Python server or automatic ingestion job.

Any static HTTP host can serve this same directory without a build step. Preserve `data/` paths, enable gzip/Brotli, use HTTPS, and avoid long-lived immutable caching on `demo.json`/`gdelt_sample.json` unless filenames are content-hashed. Relative URLs permit subdirectory hosting. No private keys or publisher fulltext are present.

Public machine-readable data: `/data/demo.json` and `/data/gdelt_sample.json`. These static downloads are not the dynamic `/api/v1/` service. Fetch costs depend on hosting terms; no paid compute plan was selected by this build.

## Python service

```bash
docker compose up --build -d
python scripts/verify_deployment.py http://127.0.0.1:8000 --api
docker compose logs --tail 100
```

The container runs as non-root with one worker and a named persistent SQLite volume. Port8000 is bound to localhost; use a TLS reverse proxy for public access. All API routes are read-only, parameters are bounded, no CORS wildcard is set and there are no admin endpoints. Add reverse-proxy request and connection rate limits before public high-traffic use. Browser visitors cannot trigger downloads, model updates or expensive recomputation.

For development without Docker, follow README. `WORLDLINE_ROOT=/app` locates bundled assets in the installed Docker package; source checkouts infer their own root. `WORLDLINE_DB_PATH` selects writable durable storage. `WORLDLINE_SNAPSHOT_PATH` selects the validated JSON artifact. Missing/corrupt data returns readiness503 and never creates replacement simulated values. Set those variables in a service manager or secret environment rather than editing source; no credential is needed for demo/GDELT archive access.

## Continuous operation is a separate release

No active unattended scheduler is configured. A live version requires a collection schedule independent of the web process, complete declared UTC coverage, archival retries/gap tracking, versioned aggregation, point-in-time backfill, sufficient calibration history and retained durable state. Merely running `backfill.py --latest` on a timer is not a validated daily world-state monitor. Do not display `LIVE` until that acquisition and closed-window pipeline exists and freshness has been verified.

## Verification and rollback

Run `python scripts/verify_deployment.py https://your-host` for the static site, adding `--api` only when the Python service is also hosted. Check both data modes and the current Git/source version. Redeploy a previous saved Sites version for static rollback. For self-hosting, retain a previous image digest and versioned snapshot; stop writes, back up SQLite using its backup API and restore the previous release. No migrations beyond idempotent schema creation are required in this version.

Docker configuration is supplied but Docker execution may not be available in the build environment; exact verification scope is recorded in validation.md. Do not interpret an unrun container build as verified deployment.
