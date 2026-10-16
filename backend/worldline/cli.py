"""Command line entry points: `python -m worldline.cli <command>`."""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .daystore import DayStore
from .gdelt import Client, ProviderError
from .ingest import acquire_day, usable

ROOT = Path(__file__).resolve().parents[2]


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _worker(day_iso: str, md5: str | None, latest_iso: str | None):
    day = date.fromisoformat(day_iso)
    latest = datetime.strptime(latest_iso, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc) if latest_iso else None
    started = time.monotonic()
    record, cooc, evidence = acquire_day(Client(), day, md5s={f"{day:%Y%m%d}": md5} if md5 else None, latest=latest)
    return record, cooc, evidence, round(time.monotonic() - started, 1)


def backfill(args) -> int:
    store = DayStore(args.store)
    client = Client()
    md5s = client.daily_md5s()
    latest = client.latest_slot()
    end = date.fromisoformat(args.end) if args.end else latest.date()
    existing = store.load("days")
    todo = [d for d in _days(date.fromisoformat(args.start), end)
            if args.refresh or not existing.get(d.isoformat()) or not existing[d.isoformat()].get("complete")]
    if existing and not args.refresh:
        # Provider outages and partial days older than three days are final; do not poll them again.
        todo = [d for d in todo if not (d.isoformat() in existing and (latest.date() - d).days > 3)]
    print(json.dumps({"store": str(args.store), "days_to_fetch": len(todo), "latest_slot": f"{latest:%Y%m%d%H%M%S}"}), flush=True)
    pending: dict[str, list] = {"days": [], "cooc": [], "evidence": []}
    failures = []
    done = 0

    def flush():
        for kind, records in pending.items():
            if records:
                store.upsert(records, kind)
                records.clear()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_worker, d.isoformat(), md5s.get(f"{d:%Y%m%d}"), f"{latest:%Y%m%d%H%M%S}"): d for d in todo}
        for future in as_completed(futures):
            day = futures[future]
            try:
                record, cooc, evidence, seconds = future.result()
            except (ProviderError, OSError) as exc:
                failures.append({"date": day.isoformat(), "error": str(exc)})
                print(json.dumps({"date": day.isoformat(), "error": str(exc)}), flush=True)
                continue
            pending["days"].append(record)
            pending["cooc"].append(cooc)
            pending["evidence"].append(evidence)
            done += 1
            if done % 25 == 0 or args.verbose:
                print(json.dumps({"done": done, "of": len(todo), "date": day.isoformat(), "fresh": record["fresh"],
                                  "kind": record["provenance"]["kind"], "slots": record["provenance"].get("slots"),
                                  "seconds": seconds}), flush=True)
            if len(pending["days"]) >= 60:
                flush()
    flush()
    summary = {"fetched": done, "failures": failures,
               "usable_days": sum(usable(r) for r in store.load("days").values())}
    print(json.dumps(summary), flush=True)
    return 1 if failures and not args.allow_failures else 0


def evaluate(args) -> int:
    from .experiments import run_protocol, write_results
    from .pipeline import analyze, load_records
    days, cooc, _ = load_records(args.store)
    analysis = analyze(days, cooc)
    labels = json.loads((ROOT / "data/labels/wikipedia_year_events.json").read_text(encoding="utf-8"))["events"]
    results, model = run_protocol(analysis, labels, quick=args.quick)
    write_results(results, ROOT / "research")
    model_path = ROOT / "data/model/published.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(model, indent=1) + "\n")
    print(json.dumps({"results": "research/results.md", "model": str(model_path.relative_to(ROOT)), "weights": model["weights"]}))
    return 0


def labels_cmd(args) -> int:
    from .labels import build_labels, save_labels
    from .wikipedia import fetch_year_article
    raw = args.dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    years = args.years or [datetime.now(timezone.utc).year]
    for year in years:
        text = fetch_year_article(year)
        (raw / f"wikipedia_{year}.wikitext").write_text(text, encoding="utf-8")
        print(json.dumps({"year": year, "bytes": len(text)}))
    if args.base and args.base.exists():
        for path in sorted(args.base.glob("wikipedia_*.wikitext")):
            target = raw / path.name
            if not target.exists():
                target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    save_labels(build_labels(raw), args.dir / "wikipedia_year_events.json")
    return 0


def build(args) -> int:
    import shutil
    from .daystore import DayStore, merge_stores
    from .geo import build_map
    from .live import nowcast, nowcast_inputs, refresh
    from .pipeline import analyze
    from .publish import publish_all
    from .scenarios import build_scenarios
    started = time.monotonic()
    seed, state = DayStore(args.seed), DayStore(args.state)
    live = None
    if args.live:
        known = merge_stores(seed, state)
        try:
            live = refresh(state, known, Client(), start=args.start)
            print(json.dumps({"live": live["summary"]}), flush=True)
        except ProviderError as exc:
            print(json.dumps({"live_error": str(exc)}), flush=True)
    days = merge_stores(seed, state, kind="days")
    cooc = merge_stores(seed, state, kind="cooc")
    evidence = merge_stores(seed, state, kind="evidence")
    analysis = analyze(days, cooc, semantic=False)
    clean = analysis.panel.usable & ~analysis.global_["instrument"]["degraded"]
    scenarios = build_scenarios(analysis.panel, clean)
    model = json.loads((ROOT / "data/model/published.json").read_text())
    live_labels = args.state / "labels" / "wikipedia_year_events.json"
    labels_doc = json.loads((live_labels if live_labels.exists() else ROOT / "data/labels/wikipedia_year_events.json").read_text(encoding="utf-8"))
    results = ROOT / "research/results.json"
    validation = json.loads(results.read_text()) if results.exists() else None
    now = nowcast(live["window"], nowcast_inputs(analysis), live["summary"]) if live else None
    out = args.out
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "web", out)
    build_info = {"commit": args.commit, "run": args.run_url, "mode": "live" if args.live else "offline",
                  "seconds": None, "live": live["summary"] if live else None}
    meta = publish_all(analysis, model, labels_doc, evidence, days, scenarios, validation, build_map(), out,
                       nowcast=now, base_url=args.base_url, build=build_info)
    (out / ".nojekyll").write_text("")
    if args.state.exists():
        shutil.copytree(args.state, out / "state", dirs_exist_ok=True)
    meta["build"]["seconds"] = round(time.monotonic() - started, 1)
    (out / "data" / "meta.json").write_text(json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
    print(json.dumps({"out": str(out), "data_as_of": meta["data_as_of"], "seconds": meta["build"]["seconds"],
                      "nowcast": bool(now and now.get("countries"))}))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="worldline", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("backfill", help="acquire missing or incomplete days from GDELT into the day store")
    p.add_argument("--store", type=Path, default=ROOT / "data")
    p.add_argument("--start", default="2023-01-01")
    p.add_argument("--end", default=None, help="last UTC day (default: day of the newest published slot)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--refresh", action="store_true", help="re-acquire days that are already complete")
    p.add_argument("--allow-failures", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=backfill)
    p = sub.add_parser("evaluate", help="run validation protocol v2.0.1 and derive the published v2.1 detector")
    p.add_argument("--store", type=Path, default=ROOT / "data")
    p.add_argument("--quick", action="store_true", help="fewer permutations and bootstrap replicates")
    p.set_defaults(func=evaluate)
    p = sub.add_parser("build", help="analyze and write the static site (optionally refreshing live data first)")
    p.add_argument("--seed", type=Path, default=ROOT / "data", help="day store committed to git")
    p.add_argument("--state", type=Path, default=ROOT / "_state", help="live day store (published with the site)")
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--live", action="store_true", help="fetch new GDELT data and compute the last-24-hours nowcast")
    p.add_argument("--start", default="2023-01-01")
    p.add_argument("--base-url", default="https://chingkheinganba231005.github.io/worldlines-v0.2.0/")
    p.add_argument("--commit", default=None)
    p.add_argument("--run-url", default=None)
    p.set_defaults(func=build)
    p = sub.add_parser("labels", help="refresh Wikipedia year-article labels (for the prospective record)")
    p.add_argument("--dir", type=Path, default=ROOT / "_state" / "labels")
    p.add_argument("--base", type=Path, default=ROOT / "data" / "labels" / "raw", help="frozen pages to include")
    p.add_argument("--years", type=int, nargs="*")
    p.set_defaults(func=labels_cmd)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
