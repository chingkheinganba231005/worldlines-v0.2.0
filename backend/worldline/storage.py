"""SQLite provenance store, preserving revisions and immutable snapshot payloads."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3
from .schemas import Snapshot

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS records (
 provider TEXT NOT NULL, source_id TEXT NOT NULL, checksum TEXT NOT NULL,
 available_at TEXT NOT NULL, observed_at TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
 PRIMARY KEY(provider,source_id,checksum)
);
CREATE TABLE IF NOT EXISTS archives (
 checksum TEXT PRIMARY KEY, url TEXT NOT NULL, observed_at TEXT NOT NULL,
 bytes INTEGER NOT NULL CHECK(bytes>=0)
);
CREATE TABLE IF NOT EXISTS snapshots (
 checksum TEXT PRIMARY KEY, mode TEXT NOT NULL, as_of TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload))
);
CREATE TRIGGER IF NOT EXISTS snapshots_immutable_update BEFORE UPDATE ON snapshots BEGIN
 SELECT RAISE(ABORT,'snapshots are immutable'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_immutable_delete BEFORE DELETE ON snapshots BEGIN
 SELECT RAISE(ABORT,'snapshots are immutable'); END;
CREATE INDEX IF NOT EXISTS record_availability ON records(available_at);
'''

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def ingest(self, records, *, archive=None):
        with self.connect() as connection:
            before = connection.total_changes
            for row in records:
                connection.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?)', (
                    row['source_provider'],row['raw_source_id'],row['source_checksum'],
                    row['available_at_utc'],row['observed_at_utc'], json.dumps(row, sort_keys=True, allow_nan=False)))
            added = connection.total_changes - before
            if archive:
                connection.execute('INSERT OR IGNORE INTO archives VALUES(?,?,?,?)', (
                    archive['sha256'], archive['url'], archive['observed_at_utc'], archive['bytes']))
            return added

    def save_snapshot(self, snapshot):
        Snapshot.model_validate(snapshot)
        payload = json.dumps(snapshot, sort_keys=True, separators=(',', ':'), allow_nan=False)
        checksum = hashlib.sha256(payload.encode()).hexdigest()
        with self.connect() as connection:
            connection.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)', (
                checksum, snapshot['mode'], snapshot['history'][-1]['date'], payload))
        return checksum

    def counts(self):
        with self.connect() as connection:
            return {table: connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('records','archives','snapshots')}
