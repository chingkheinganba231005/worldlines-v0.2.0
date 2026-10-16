"""Synthetic day records with the real schema, for fast deterministic end-to-end tests."""
from __future__ import annotations

from datetime import date, timedelta

import io
import zipfile

import numpy as np

from worldline.gdelt import DAILY, FIFTEEN, Layout

# FIPS location code -> (mean daily events, CAMEO actor code)
COUNTRIES = {"US": (420, "USA"), "UK": (130, "GBR"), "IN": (120, "IND"), "RS": (95, "RUS"), "UP": (85, "UKR"),
             "CH": (75, "CHN"), "IS": (65, "ISR"), "FR": (55, "FRA"), "GM": (50, "DEU"), "NI": (45, "NGA"),
             "SU": (40, "SDN"), "BR": (36, "BRA"), "JA": (60, "JPN"), "KS": (50, "KOR"), "TU": (55, "TUR"),
             "IR": (70, "IRN"), "EG": (45, "EGY"), "PK": (65, "PAK"), "MX": (50, "MEX"), "SF": (45, "ZAF"),
             "AS": (55, "AUS"), "CA": (60, "CAN"), "IT": (50, "ITA"), "SP": (45, "ESP")}
BASE = np.array([.20, .09, .07, .21, .08, .03, .04, .04, .03, .02, .07, .02, .01, .01, .005, .01, .025, .015, .03, .005])
BASE = BASE / BASE.sum()


def make_records(days: int = 430, seed: int = 7, start: date = date(2023, 1, 1), spikes=()):
    """spikes: iterable of (day_index, fips, volume_multiplier, violence_share)."""
    rng = np.random.default_rng(seed)
    spike_map = {(t, f): (mult, share) for t, f, mult, share in spikes}
    profiles = {f: rng.dirichlet(BASE * 400) for f in COUNTRIES}
    records = {}
    cooc = {}
    for t in range(days):
        day = (start + timedelta(days=t)).isoformat()
        weekday = (start + timedelta(days=t)).weekday()
        factor = 0.65 if weekday >= 5 else 1.0
        geo = {}
        total_roots = np.zeros(20, dtype=int)
        urls_total = 0
        for fips, (mean, _) in COUNTRIES.items():
            mult, violence = spike_map.get((t, fips), (1.0, None))
            n = int(rng.poisson(mean * factor * mult))
            probs = profiles[fips].copy()
            if violence is not None:
                probs[17:20] = probs[17:20] / probs[17:20].sum() * violence
                rest = [i for i in range(20) if i < 17]
                probs[rest] = probs[rest] / probs[rest].sum() * (1 - violence)
            roots = rng.multinomial(n, probs / probs.sum())
            urls = max(1, int(n / 4 * mult))
            geo[fips] = {"n": n, "articles": urls * 3, "tone": -1.0 * n, "gold": 0.5 * n, "isroot": n // 2,
                         "root": roots.tolist(), "urls": urls, "outlets": max(1, urls // 2),
                         "top": [[f"{i + 1:02d}0", int(roots[i])] for i in np.argsort(-roots)[:3]]}
            total_roots += roots
            urls_total += urls
        actors = [a for _, a in COUNTRIES.values()]
        dyad = {}
        for i, a in enumerate(actors):
            for b in actors[i + 1:i + 4]:
                dyad[f"{a}>{b}"] = [int(v) for v in rng.poisson([30, 6, 8, 4])]
        base = {f"{i + 1:02d}0": int(v) for i, v in enumerate(total_roots) if v}
        fresh = int(total_roots.sum())
        records[day] = {
            "schema": "worldline-day-v2", "date": day, "rows": fresh + 50, "malformed": 0, "duplicates": 0, "offday": 0,
            "invalid": 0, "stale": 50, "fresh": fresh, "root": total_roots.tolist(), "base": base, "isroot": fresh // 2,
            "articles": urls_total * 3, "mentions": urls_total * 4, "sources": urls_total, "tone": -fresh * 1.0, "goldstein": 0.0,
            "urls": urls_total, "domains_unique": 400,
            "domains": {f"outlet{k}.example": int(v) for k, v in enumerate(rng.poisson(np.linspace(80, 5, 40)))},
            "nogeo": 10, "geo": geo, "dyad": dyad, "spots": [], "complete": True,
            "provenance": {"kind": "gdelt-daily", "slots": 96, "slots_expected": 96, "md5": "0" * 32, "transfer_verified": True},
        }
        pairs = {}
        codes = sorted(base)
        for i, a in enumerate(codes):
            for b in codes[i + 1:]:
                ia, ib = int(a[:2]), int(b[:2])
                same = (ia <= 5) == (ib <= 5) and (ia >= 15) == (ib >= 15)
                pairs[f"{a}|{b}"] = int(rng.poisson(40 if same else 8))
        cooc[day] = {"schema": "worldline-cooc-v1", "date": day, "urls": urls_total, "pairs": pairs}
    return records, cooc


def gdelt_row(layout: Layout, *, event_id: str, sqldate: str, added: str, root: str = "01", base: str | None = None,
              quad: str = "1", country: str = "US", actor1: str = "USA", actor2: str = "", url: str = "https://www.example.com/a",
              lat: str = "38.9", lon: str = "-77.0", articles: int = 3, goldstein: str = "1.0", is_root: str = "1") -> list[str]:
    """One raw GDELT event row in either official encoding (fields not used by WORLDLINE are left blank)."""
    fields = [""] * layout.columns
    fields[0], fields[1], fields[7], fields[17] = event_id, sqldate, actor1, actor2
    fields[25], fields[26], fields[27], fields[28], fields[29], fields[30] = is_root, base or root + "0", base or root + "0", root, quad, goldstein
    fields[31], fields[32], fields[33], fields[34] = str(articles + 1), "1", str(articles), "-2.5"
    fields[layout.action_type], fields[layout.action_country] = "4", country
    fields[layout.action_lat], fields[layout.action_lon] = lat, lon
    fields[layout.date_added] = added if layout is DAILY else added + "120000"
    fields[layout.source_url] = url
    return fields


def tsv(rows: list[list[str]]) -> bytes:
    return ("\n".join("\t".join(r) for r in rows) + "\n").encode()


def archive(member: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, payload)
    return buffer.getvalue()


__all__ = ["COUNTRIES", "DAILY", "FIFTEEN", "archive", "gdelt_row", "make_records", "tsv"]
