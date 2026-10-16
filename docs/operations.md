# Operations and honest freshness

This release serves frozen research snapshots. There is no hourly background task and no live data guarantee. The synthetic `generated_at` is a deterministic replay cutoff, explicitly described in its payload, not wall-clock retrieval. GDELT `generated_at`/observed timestamps record actual fetch processing; provider DATEADDED and event occurrence remain separate.

The API reads and validates a changed snapshot by file size/modification signature, writes an immutable hashed SQLite snapshot and caches it. Update JSON atomically using a temporary file and rename; acquisition scripts already do this. If replacement validation fails, readiness and data reads fail503 rather than return a fabricated new score. Keep the previous snapshot available for rollback.

Store private raw ZIPs in `data/raw/` and SQLite outside ephemeral container storage. The supplied Compose volume persists across container restarts. Back up SQLite with its online backup API, and copy the JSON plus archive manifest with checksums. Keep enough raw versions for reproducibility; choose an explicit retention policy before continuous collection rather than filling disk indefinitely.

The bounded collector uses official endpoints only, caps download/uncompressed sizes, rejects ZIP traversal paths, and stops after finite retries. A failed request is logged to stderr; `--allow-gaps` explicitly records partial acquisition. Rights markers accompany records. Never fetch/rehost linked article bodies automatically.

For public Python operation, place TLS and request limits at the reverse proxy, retain access/error logs with an appropriate retention period, monitor `/ready`, disk space, snapshot age and collector failures. Do not launch collection once per web worker or visitor. Upgrade to PostgreSQL/queues only after measured concurrency or retention needs justify it.
