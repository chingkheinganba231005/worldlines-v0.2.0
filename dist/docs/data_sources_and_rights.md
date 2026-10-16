# Data sources, rights and information availability

Reviewed official pages on 2026-10-14:

- https://gdeltproject.org/data.html — original GDELT datasets, formats and documentation. GDELT Events focuses on CAMEO sociopolitical records; it is not an all-domain scientific discovery index.
- https://gdeltproject.org/about.html — GDELT permits use/rehosting with attribution. Always credit The GDELT Project. This does not transfer rights to linked news article text.
- https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf — original 61-column Events schema, DATEADDED and SOURCEURL.
- https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/ — historical GDELT2 format release. Do not treat old roadmap promises as current functionality.
- https://data.gdeltproject.org/gdeltv2/lastupdate.txt — official discovery manifest; direct bounded archive requests only.

## Active data

The main observatory uses deterministic, original synthetic metadata from `worldline.demo`, CC0. No listed synthetic event is a news claim. Its broad-domain taxonomy is separate from the real data source.

The real-data inspector contains four original GDELT Events archives at01:30UTC on October10–13,2026, 3,414 distinct provider IDs. Each archive is one15-minute sample, not complete daily coverage. Exact URLs, retrieval timestamps, SHA256 checksums and counts are in `dist/data/gdelt_sample.json`. ZIPs retained privately in ignored `data/raw/` are reproducible from those URLs. The public output contains structured metadata and original source links, never fetched publisher article bodies.

`SQLDATE` has day-level event occurrence. `DATEADDED` is provider insertion time. Actual pipeline `observed_at_utc` and ingestion time are also retained. A historical archive retrieved today is a retrospective sample: using DATEADDED for historical replay assumes the archive is an adequate historical availability record. It does not prove the precise content was unrevised or available to this pipeline at that historical moment. Record this limitation before real research. Archive content hashes detect later byte changes but cannot reconstruct unavailable past versions.

SourceURL often identifies an early discovered publisher. NumSources and distinct domains are diversity proxies, not independent verification. Metadata labels are generated actor/action descriptions, not publisher headlines. All actual records remain provisional. Event IDs identify provider records, not independently verified unique happenings.

GDELT-derived source attribution accompanies every actual record. Cross-provider ownership/syndication independence is not inferred. ACLED, OpenAlex, FRED and other channels are not connected or bundled. Check their current terms, publication lags and credentials separately before adding them.

## Operational limits

Only official HTTPS `data.gdeltproject.org/gdeltv2/` endpoints are allowed by the connector. Fetches have finite retries, timeouts, byte limits, ZIP expansion limits and circuit cooldown. Browser visitors cannot initiate ingestion. No requests fetch arbitrary source URLs. No third-party credentials are needed for this bounded GDELT adapter.
