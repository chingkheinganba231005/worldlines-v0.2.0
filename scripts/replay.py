#!/usr/bin/env python3
"""Rebuild the exact demo payload and audit input. No network or credentials."""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from worldline.core import build_snapshot
from worldline.demo import generate_windows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist/data/demo.json")
    parser.add_argument("--seed", type=int, default=73129)
    parser.add_argument("--days", type=int, default=240)
    args = parser.parse_args()
    started = time.monotonic()
    windows = generate_windows(days=args.days, seed=args.seed)
    snapshot = build_snapshot(windows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, separators=(",", ":"), allow_nan=False) + "\n")
    temporary.replace(args.output)
    audit = ROOT / "data/fixtures/synthetic_windows.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    # The generator reconstructs event-level records; compact audit stores sufficient statistics.
    audit.write_text(json.dumps([{k:v for k,v in w.items() if k != "events"} for w in windows], indent=2) + "\n")
    print(json.dumps({"mode": snapshot["mode"], "history_windows": len(snapshot["history"]),
                      "candidates": [h["date"] for h in snapshot["history"] if h["alert"]["state"] == "candidate"],
                      "data_version": snapshot["data_version"], "output": str(args.output),
                      "seconds": round(time.monotonic()-started,2)}))

if __name__ == "__main__":
    main()
