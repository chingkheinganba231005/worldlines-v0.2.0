"""Append-friendly store of daily aggregates: one gzipped JSON-lines file per month.

Layout (both the seed in git and the live state published with the site):

    <root>/days/YYYY-MM.jsonl.gz    one day record per line, sorted by date
    <root>/cooc/YYYY-MM.jsonl.gz    same-article co-occurrence per day (embedding training)

Writes are atomic (temp file + rename) and byte-deterministic (gzip mtime=0,
sorted keys), so an unchanged month produces an unchanged file and a clean diff.
"""
from __future__ import annotations

import gzip
import io
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# Fields whose values depend on which official encoding was read. The daily file
# carries end-of-day revised attention counts; 15-minute exports carry first
# extraction values. Models never use these fields (see docs/methods.md §Data).
REVISED_FIELDS = ("articles", "mentions", "sources", "tone", "isroot")


def _month(day: str) -> str:
    return day[:7]


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0, compresslevel=9) as gz:
        for record in sorted(records, key=lambda r: r["date"]):
            gz.write((json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode())
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(buffer.getvalue())
    os.replace(temporary, path)


def preference(record: dict) -> tuple:
    """Order competing records for one day: complete > partial; daily file > 15-minute; more slots > fewer."""
    provenance = record.get("provenance", {})
    return (bool(record.get("complete")), provenance.get("kind") == "gdelt-daily", provenance.get("slots", 0) or 0)


class DayStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def path(self, kind: str, month: str) -> Path:
        return self.root / kind / f"{month}.jsonl.gz"

    def months(self, kind: str = "days") -> list[str]:
        directory = self.root / kind
        return sorted(p.name[:7] for p in directory.glob("*.jsonl.gz")) if directory.exists() else []

    def load(self, kind: str = "days", start: str | None = None, end: str | None = None) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for month in self.months(kind):
            if (start and month < start[:7]) or (end and month > end[:7]):
                continue
            for record in _read(self.path(kind, month)):
                if (start and record["date"] < start) or (end and record["date"] > end):
                    continue
                out[record["date"]] = record
        return dict(sorted(out.items()))

    def upsert(self, records: Iterable[dict], kind: str = "days", *, force: bool = False) -> int:
        """Insert or replace day records; a stored record is only replaced by a preferred one unless forced."""
        by_month: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            by_month[_month(record["date"])].append(record)
        changed = 0
        for month, incoming in by_month.items():
            path = self.path(kind, month)
            existing = {r["date"]: r for r in _read(path)}
            dirty = False
            for record in incoming:
                current = existing.get(record["date"])
                if current == record:
                    continue
                if current is None or force or kind != "days" or preference(record) >= preference(current):
                    existing[record["date"]] = record
                    dirty = True
                    changed += 1
            if dirty:
                _write(path, list(existing.values()))
        return changed


def merge_stores(primary: DayStore, *others: DayStore, kind: str = "days") -> dict[str, dict]:
    """Union of stores; per day the preferred record wins (used to combine git seed and live state)."""
    merged = primary.load(kind)
    for store in others:
        for day, record in store.load(kind).items():
            current = merged.get(day)
            if current is None or (kind == "days" and preference(record) > preference(current)):
                merged[day] = record
    return dict(sorted(merged.items()))
