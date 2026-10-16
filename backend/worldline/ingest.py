"""Acquire UTC days from GDELT: official daily file first, 15-minute exports as the live fallback.

Every returned day record carries provenance: which encoding was read, checksums
(MD5 verified against GDELT's published list when available), retrieval time,
and how many of the 96 fifteen-minute slots were received. Days the provider
never published are stored as explicit gap records, never as zero activity.
"""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

from .aggregate import DayAggregator
from .gdelt import (DAILY, FIFTEEN, Client, NotPublished, checksums, daily_url, day_slots, rows,
                    slot_url, unpack, utc_now)

USABLE_MIN_SLOTS = 92  # >= 95.8% of a day's slots; below this a day is treated as a coverage gap


def _from_daily(client: Client, day: date, expected_md5: str | None):
    url = daily_url(day)
    payload, meta = client.fetch_with_meta(url)
    sums = checksums(payload)
    aggregator = DayAggregator(day)
    aggregator.add_rows(rows(unpack(payload), DAILY), DAILY)
    record, cooc = aggregator.finish()
    evidence = aggregator.evidence()
    record["complete"] = True
    record["provenance"] = {
        "kind": "gdelt-daily", "layout": DAILY.name, "urls": [url], "md5": sums["md5"], "sha256": sums["sha256"],
        "bytes": sums["bytes"], "transfer_verified": meta["transfer_verified"],
        "listed_md5": expected_md5, "listed_md5_match": (expected_md5 == sums["md5"]) if expected_md5 else None,
        "slots": 96, "slots_expected": 96,
        "retrieved_at": utc_now(),
    }
    return record, cooc, evidence


def _from_slots(client: Client, day: date, latest: datetime | None, threads: int = 8):
    stamps = [s for s in day_slots(day) if latest is None or s <= latest]

    def get(stamp):
        try:
            return stamp, client.fetch(slot_url(stamp))
        except NotPublished:
            return stamp, None

    with ThreadPoolExecutor(max_workers=threads) as pool:
        results = list(pool.map(get, stamps))
    aggregator = DayAggregator(day)
    received, missing, digests, total_bytes = [], [], [], 0
    for stamp, payload in results:
        if payload is None:
            missing.append(f"{stamp:%H%M}")
            continue
        aggregator.add_rows(rows(unpack(payload), FIFTEEN), FIFTEEN)
        received.append(stamp)
        digests.append(hashlib.sha256(payload).hexdigest())
        total_bytes += len(payload)
    record, cooc = aggregator.finish()
    evidence = aggregator.evidence()
    record["complete"] = len(received) == 96
    record["provenance"] = {
        "kind": "gdelt-15min" if received else "unavailable", "layout": FIFTEEN.name,
        "urls": [slot_url(s) for s in received[:1]] + ([f"... {len(received) - 1} more"] if len(received) > 1 else []),
        "sha256_of_slot_sha256s": hashlib.sha256("".join(digests).encode()).hexdigest() if digests else None,
        "bytes": total_bytes, "slots": len(received), "slots_expected": 96, "missing_slots": missing[:96],
        "retrieved_at": utc_now(), "latest_slot_considered": f"{latest:%Y%m%d%H%M%S}" if latest else None,
    }
    if not received:
        record["gap"] = True
    return record, cooc, evidence


def acquire_day(client: Client, day: date, *, md5s: dict[str, str] | None = None, latest: datetime | None = None,
                prefer_slots: bool = False):
    """Return (day record, cooc record, evidence record) for one UTC day."""
    if not prefer_slots:
        try:
            return _from_daily(client, day, (md5s or {}).get(f"{day:%Y%m%d}"))
        except NotPublished:
            pass
    return _from_slots(client, day, latest)


def usable(record: dict | None) -> bool:
    """Whether a day's coverage is sufficient for modeling."""
    if not record or record.get("gap"):
        return False
    return bool(record.get("complete")) or (record.get("provenance", {}).get("slots", 0) or 0) >= USABLE_MIN_SLOTS
