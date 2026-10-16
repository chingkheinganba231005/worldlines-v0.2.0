"""End-to-end analysis: day store -> panel -> monitors -> embeddings -> scenarios -> validation."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .daystore import DayStore, merge_stores
from .embeddings import (check_event_embeddings, check_worldlines, code_cost, country_worldlines, event_type_embeddings,
                         root_embeddings)
from .monitor import Config, country_monitor, global_monitor, learned_transport
from .panel import Panel, build_panel


@dataclass
class Analysis:
    panel: Panel
    cfg: Config
    global_: dict
    country: dict
    events_model: dict
    events_check: dict
    worldlines: dict
    worldlines_check: dict
    transport: dict
    timings: dict = field(default_factory=dict)
    scenarios: dict | None = None
    validation: dict | None = None


def load_records(*roots: Path) -> tuple[dict, dict, dict]:
    stores = [DayStore(r) for r in roots if Path(r).exists()]
    days = merge_stores(*stores, kind="days")
    cooc = merge_stores(*stores, kind="cooc")
    evidence = merge_stores(*stores, kind="evidence")
    return days, cooc, evidence


def analyze(days: dict, cooc: dict, cfg: Config | None = None, *, log=print) -> Analysis:
    cfg = cfg or Config()
    timings = {}
    started = time.monotonic()
    panel = build_panel(days)
    timings["panel"] = time.monotonic() - started

    step = time.monotonic()
    model = event_type_embeddings(cooc, days, start=cfg.dev_start, end=cfg.dev_end)
    events_check = check_event_embeddings(model)
    vectors = root_embeddings(model)
    timings["event_embeddings"] = time.monotonic() - step
    log(f"event embeddings: {len(model['codes'])} codes ({timings['event_embeddings']:.1f}s)")

    step = time.monotonic()
    global_ = global_monitor(panel, cfg)
    timings["global"] = time.monotonic() - step

    step = time.monotonic()
    transport = learned_transport(panel, lambda codes: code_cost(model, codes), cfg)
    timings["learned_transport"] = time.monotonic() - step
    log(f"global monitor + learned transport ({timings['global'] + timings['learned_transport']:.1f}s)")

    step = time.monotonic()
    country = country_monitor(panel, cfg, global_["instrument"], root_vectors=vectors)
    timings["countries"] = time.monotonic() - step
    log(f"country monitor: {len(country['countries'])} countries ({timings['countries']:.1f}s)")

    step = time.monotonic()
    months = sorted({d[:7] for d in days})
    worldlines = country_worldlines(days, country["countries"], months)
    worldlines_check = check_worldlines(worldlines, country["countries"])
    timings["worldlines"] = time.monotonic() - step
    log(f"worldlines: {len(worldlines['months'])} months ({timings['worldlines']:.1f}s)")
    return Analysis(panel=panel, cfg=cfg, global_=global_, country=country, events_model=model,
                    events_check=events_check, worldlines=worldlines, worldlines_check=worldlines_check,
                    transport=transport, timings=timings)


def root_vectors_of(analysis: Analysis) -> np.ndarray:
    return root_embeddings(analysis.events_model)
