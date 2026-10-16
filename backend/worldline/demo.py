"""Seeded, openly redistributable synthetic controls. No actual news claims."""
from __future__ import annotations
from datetime import date, timedelta
import numpy as np
from .core import TAXONOMY, cluster_mentions

SEED = 73129
START = date(2025, 1, 1)
SOURCES = [f"synthetic-source-{n:02d}" for n in range(1, 9)]
TOPIC_TITLES = [
    "Delegations open a new round of regional talks",
    "Research consortium announces an experimental computing milestone",
    "Statistical office releases an economic activity report",
    "Monitoring network issues a regional climate assessment",
    "Public health laboratories report a change in surveillance results",
    "Civic institutions announce a new community programme",
]


def generate_windows(days: int = 240, seed: int = SEED, controls: bool = True) -> list[dict]:
    rng = np.random.default_rng(seed)
    base = np.array([.23, .16, .22, .15, .12, .12])
    windows = []
    for t in range(days):
        day = (START + timedelta(days=t)).isoformat()
        shares = base.copy()
        shares[1] += .025 * np.sin(t / 18)
        shares[2] -= .025 * np.sin(t / 18)
        intervention = None
        if controls and 170 <= t < 185:
            shares = np.array([.11, .08, .12, .08, .53, .08])
            intervention = "injected_health_composition_break"
        if controls and t >= 220:
            shares = np.array([.12, .54, .11, .09, .07, .07])
            intervention = "injected_science_composition_break"
        n = int(rng.integers(90, 125))
        if controls and t == 150:
            n = 8
            intervention = "injected_coverage_dropout"
        domains = rng.choice(len(shares), n, p=shares / shares.sum())
        mentions = []
        for j, domain in enumerate(domains):
            # An opaque entity identifier makes independent hypothetical events distinct.
            entity = f"fictional-entity-{t:03d}-{j:03d}"
            title = f"Synthetic study {t:03d}.{j:03d}: {TOPIC_TITLES[domain]}"
            for report in range(int(rng.integers(1, 4))):
                source = str(rng.choice(SOURCES))
                mentions.append({
                    "id": f"syn-{t:03d}-{j:03d}-{report}", "provider": "worldline_synthetic_v1",
                    "date": day, "observed_at": day + f"T12:{report:02d}:00Z", "title": title,
                    "domain": TAXONOMY[domain]["id"], "entities": [entity],
                    "region": ["Hypothetical region A", "Hypothetical region B", "Hypothetical region C"][j % 3],
                    "source": source, "is_synthetic": True,
                })
        if controls and 135 <= t <= 138:
            original = mentions[0]
            for repetition in range(100):
                mentions.append(dict(original, id=f"syndicated-{t}-{repetition}"))
            intervention = "injected_syndication_burst"
        if controls and 155 <= t <= 160:
            for j, original in enumerate(list(mentions)):
                mentions.append(dict(original, id=f"new-source-{t}-{j}", source=f"new-synthetic-publisher-{j % 12}"))
            intervention = "injected_source_expansion"
        clusters = cluster_mentions(mentions)
        counts = [sum(c["domain"] == topic["id"] for c in clusters) for topic in TAXONOMY]
        source_counts: dict[str, int] = {}
        for mention in mentions:
            source_counts[mention["source"]] = source_counts.get(mention["source"], 0) + 1
        # Display all unique clusters; filtering in the client is a view, not sampling for scores.
        events = [{
            "id": c["cluster_id"], "title": c["title"], "domain": c["domain"], "region": c["region"],
            "source_count": c["source_count"], "source_ids": c["source_ids"], "source_urls": [],
            "verification_status": "synthetic", "is_synthetic": True,
            "observed_at": c["observed_at"], "cluster_version": c["cluster_version"],
            "mention_count": len(c["mention_ids"]), "metadata_rights": "CC0 synthetic metadata created for WORLDLINE",
            "explanation": "One vote in its topic histogram after deterministic deduplication. A topic's JSD contribution is a distributional attribution, not this event's causal impact.",
        } for c in clusters]
        windows.append({"date": day, "counts": counts, "raw_mentions": len(mentions), "sources": source_counts,
                        "events": events, "intervention": intervention, "sample_policy": "complete synthetic daily window"})
    return windows
