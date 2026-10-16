"""Live monitoring: keep the day store current and compute a provisional "last 24 hours" view.

Each run fetches the 96 most recent fifteen-minute exports once and uses them for
(1) today's partial day record, (2) a rolling 24-hour window that covers every
time zone and is therefore comparable with a whole day, and (3) any recent day
that is still missing or incomplete. Finished days are never re-downloaded.
"""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np

from .aggregate import DayAggregator
from .daystore import DayStore
from .gdelt import FIFTEEN, Client, NotPublished, ProviderError, rows, slot_url, unpack, utc_now
from .ingest import acquire_day
from .reference import fips_to_iso3, place_name, places
from .stats import tail_pvalue_sorted

LAUNCH_DATE = "2026-10-16"  # first day of the prospective (truly out-of-sample) track record


def fetch_slots(client: Client, stamps: list[datetime], threads: int = 8) -> dict[datetime, bytes | None]:
    def get(stamp):
        try:
            return stamp, client.fetch(slot_url(stamp))
        except NotPublished:
            return stamp, None

    with ThreadPoolExecutor(max_workers=threads) as pool:
        return dict(pool.map(get, stamps))


def aggregate_slots(day: date | None, payloads: dict[datetime, bytes | None], *, window: bool = False):
    aggregator = DayAggregator(day or date.today(), window=window)
    received = []
    digests = []
    for stamp in sorted(payloads):
        payload = payloads[stamp]
        if payload is None:
            continue
        aggregator.add_rows(rows(unpack(payload), FIFTEEN), FIFTEEN)
        received.append(stamp)
        digests.append(hashlib.sha256(payload).hexdigest())
    return aggregator, received, digests


def refresh(state: DayStore, known: dict[str, dict], client: Client, *, start: str, max_days: int = 40, log=print) -> dict:
    """Bring the state store up to date. Returns the rolling-window aggregator and a summary."""
    latest = client.latest_slot()
    md5s = client.daily_md5s()
    today = latest.date()
    window_stamps = [latest - timedelta(minutes=15 * k) for k in range(96)]
    payloads = fetch_slots(client, window_stamps)
    summary: dict[str, Any] = {"latest_slot": f"{latest:%Y%m%d%H%M%S}", "window_slots": sum(v is not None for v in payloads.values()), "acquired": []}
    # Today's partial record from the slots already in hand.
    today_payloads = {s: p for s, p in payloads.items() if s.date() == today}
    aggregator, received, digests = aggregate_slots(today, today_payloads)
    record, cooc = aggregator.finish()
    evidence = aggregator.evidence()
    record["complete"] = len(received) == 96
    record["provenance"] = {"kind": "gdelt-15min", "layout": FIFTEEN.name, "slots": len(received), "slots_expected": 96,
                            "urls": [slot_url(s) for s in received[:1]], "bytes": sum(len(p) for p in today_payloads.values() if p is not None),
                            "sha256_of_slot_sha256s": hashlib.sha256("".join(digests).encode()).hexdigest() if digests else None,
                            "retrieved_at": utc_now(), "latest_slot_considered": summary["latest_slot"]}
    state.upsert([record], "days", force=True)
    state.upsert([cooc], "cooc")
    state.upsert([evidence], "evidence")
    # Missing or provisional recent days: daily file if published, otherwise all 96 slots.
    first = date.fromisoformat(start)
    todo = []
    day = first
    while day < today:
        record_known = known.get(day.isoformat())
        age = (today - day).days
        final = record_known is not None and (
            (record_known.get("complete") and record_known.get("provenance", {}).get("kind") == "gdelt-daily")
            or (record_known.get("complete") and age > 2) or (not record_known.get("complete") and age > 3))
        if not final:
            todo.append(day)
        day += timedelta(days=1)
    for day in todo[-max_days:]:
        try:
            record, cooc, evidence = acquire_day(client, day, md5s=md5s, latest=latest)
        except ProviderError as exc:
            log(f"acquire {day}: {exc}")
            continue
        state.upsert([record], "days")
        state.upsert([cooc], "cooc")
        state.upsert([evidence], "evidence")
        summary["acquired"].append({"date": day.isoformat(), "kind": record["provenance"]["kind"], "complete": record["complete"]})
    window, received, _ = aggregate_slots(None, payloads, window=True)
    summary["window_from"] = f"{min(received):%Y-%m-%d %H:%M}" if received else None
    summary["window_to"] = f"{max(received) + timedelta(minutes=15):%Y-%m-%d %H:%M}" if received else None
    return {"window": window, "summary": summary}


def nowcast_inputs(analysis, *, calib_days: int = 365) -> dict | None:
    """From the latest analysis: each country's forecast for the first unfinished day and its calibration scores."""
    panel, country = analysis.panel, analysis.country
    complete = np.flatnonzero(panel.usable)
    if not len(complete) or complete[-1] + 1 >= panel.T:
        return None
    target = int(complete[-1] + 1)  # the day after the last complete day (today, partial)
    out = {"target_date": panel.dates[target], "countries": {}}
    for m, iso3 in enumerate(country["countries"]):
        pred = country["articles_pred"][target, m]
        scores = country["articles_score"][max(0, target - calib_days):target, m]
        scores = np.sort(scores[np.isfinite(scores)])
        if not np.isfinite(pred) or len(scores) < 60:
            continue
        out["countries"][iso3] = {"pred": float(pred), "calib": [round(float(v), 4) for v in scores]}
    return out


def nowcast(window: DayAggregator, inputs: dict | None, summary: dict) -> dict | None:
    if inputs is None or not inputs["countries"]:
        return None
    record, _ = window.finish()
    fips = fips_to_iso3()
    articles: dict[str, int] = {}
    for code, stats in record.get("geo", {}).items():
        iso = fips.get(code)
        if iso:
            articles[iso] = articles.get(iso, 0) + stats.get("urls", 0)
    world = max(record.get("urls", 0), 1)
    rows_out = []
    for iso3, info in inputs["countries"].items():
        a = articles.get(iso3, 0)
        residual = float(np.log((a + 0.5) / world) - info["pred"])
        p = tail_pvalue_sorted(residual, info["calib"])
        place = places().get(iso3)
        rows_out.append({"iso3": iso3, "name": place_name(iso3), "flag": "".join(chr(0x1F1E6 + ord(c) - 65) for c in place.iso2) if place else "",
                         "articles": a, "ratio": round(float(np.exp(residual)), 2), "p": round(p, 6),
                         "return_period": round(min(1 / max(p, 1e-9), 5000), 0)})
    rows_out.sort(key=lambda r: r["p"])
    return {"provisional": True, "computed_at": utc_now(), "through": summary.get("window_to"), "from": summary.get("window_from"),
            "slots": summary.get("window_slots"), "articles": int(record.get("urls", 0)), "events": int(record.get("fresh", 0)),
            "forecast_for": inputs["target_date"],
            "countries": [r for r in rows_out if r["p"] <= 0.2 and r["ratio"] >= 1.2][:10]}


def prospective(alarms: list[dict], labels: list[dict], *, since: str = LAUNCH_DATE) -> dict:
    """Score alarms issued on or after launch against Wikipedia entries (any category) within the hit window."""
    by_country: dict[str, set[str]] = {}
    for event in labels:
        for iso in event["countries"]:
            by_country.setdefault(iso, set()).add(event["date"])
    scored = []
    for alarm in alarms:
        if alarm["date"] < since:
            continue
        d = date.fromisoformat(alarm["date"])
        window = {(d + timedelta(days=k)).isoformat() for k in range(-2, 2)}
        scored.append({**alarm, "matched": bool(window & by_country.get(alarm["iso3"], set()))})
    return {"since": since, "alarms": len(scored), "matched": sum(a["matched"] for a in scored), "items": scored[-200:],
            "note": "Prospective: issued before any label existed. Wikipedia's year article is updated with a lag, so recent alarms "
                    "may match later."}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
