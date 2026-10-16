"""Turn one UTC day of GDELT event rows into compact, auditable sufficient statistics.

Design rules
* A day is defined by DATEADDED (provider availability), never by the event's
  own SQLDATE, so a day's record is fixed once the provider has published it.
* Only "fresh" events (SQLDATE on the same or previous day) enter compositions.
  GDELT re-extracts anniversaries and retrospective mentions (lags of 7, 30 and
  365 days are common); these are counted as `stale`, not discarded silently.
* Provider vocabularies are kept raw (FIPS location codes, CAMEO actor codes).
  Mapping to ISO3 happens downstream, so a mapping fix never needs a re-download.
* One GDELT event record is one vote. Record IDs are deduplicated. A record is not
  a verified real-world event; see docs/data_sources_and_rights.md.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from .gdelt import (ACTOR1_COUNTRY, ACTOR2_COUNTRY, AVG_TONE, BASE_CODE, GOLDSTEIN, ID, IS_ROOT,
                    NUM_ARTICLES, NUM_MENTIONS, NUM_SOURCES, QUAD, ROOT_CODE, SQLDATE, Layout)

SCHEMA = "worldline-day-v1"
TOP_DOMAINS = 150
TOP_SPOTS = 400
EVIDENCE_PER_COUNTRY = 3
EVIDENCE_MIN_EVENTS = 50
MIN_DYAD = 2
MIN_COOC = 2
_ROOT_INDEX = {f"{i:02d}": i - 1 for i in range(1, 21)}


def _domain(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return ""
    host = url.split("/", 3)[2].split("@")[-1].split(":")[0].lower()
    return host[4:] if host.startswith("www.") else host


class DayAggregator:
    """Accumulate rows for one target UTC day from one or more archives."""

    def __init__(self, day: date):
        self.day = day
        self.day_key = f"{day:%Y%m%d}"
        self.prev_key = f"{day - timedelta(days=1):%Y%m%d}"
        self.seen: set[str] = set()
        self.counts = Counter()  # rows, malformed, duplicates, offday, stale, fresh, invalid
        self.root = [0] * 20
        self.base: Counter = Counter()
        self.isroot = self.articles = self.mentions = self.sources = 0
        self.tone = self.gold = 0.0
        self.geo: dict[str, list] = {}
        self.dyad: dict[tuple[str, str], list[int]] = {}
        self.url_codes: dict[str, set[str]] = {}
        self.spots: dict[tuple[int, int], list[int]] = {}
        self.url_country: Counter = Counter()

    def add_rows(self, row_iter, layout: Layout) -> None:
        counts, root, base, geo, dyad, urls, spots = self.counts, self.root, self.base, self.geo, self.dyad, self.url_codes, self.spots
        url_country = self.url_country
        seen, day_key, prev_key = self.seen, self.day_key, self.prev_key
        i_country, i_lat, i_lon, i_added, i_url = layout.action_country, layout.action_lat, layout.action_lon, layout.date_added, layout.source_url
        for fields in row_iter:
            counts["rows"] += 1
            if fields is None:
                counts["malformed"] += 1
                continue
            if fields[i_added][:8] != day_key:
                counts["offday"] += 1
                continue
            event_id = fields[ID]
            if event_id in seen:
                counts["duplicates"] += 1
                continue
            seen.add(event_id)
            occurred = fields[SQLDATE]
            if occurred != day_key and occurred != prev_key:
                counts["stale"] += 1
                continue
            root_index = _ROOT_INDEX.get(fields[ROOT_CODE])
            quad = fields[QUAD]
            base_code = fields[BASE_CODE]
            try:
                n_articles = int(fields[NUM_ARTICLES])
                n_mentions = int(fields[NUM_MENTIONS])
                n_sources = int(fields[NUM_SOURCES])
                tone = float(fields[AVG_TONE])
                gold = float(fields[GOLDSTEIN]) if fields[GOLDSTEIN] else 0.0
            except ValueError:
                root_index = None
            if root_index is None or quad not in ("1", "2", "3", "4") or not event_id.isdigit() or not base_code.startswith(fields[ROOT_CODE]):
                counts["invalid"] += 1
                continue
            counts["fresh"] += 1
            is_root = fields[IS_ROOT] == "1"
            root[root_index] += 1
            base[base_code] += 1
            self.isroot += is_root
            self.articles += n_articles
            self.mentions += n_mentions
            self.sources += n_sources
            self.tone += tone
            self.gold += gold
            country = fields[i_country]
            if country:
                stats = geo.get(country)
                if stats is None:
                    stats = geo[country] = [0, 0, 0.0, 0.0, 0] + [0] * 20
                stats[0] += 1
                stats[1] += n_articles
                stats[2] += tone
                stats[3] += gold
                stats[4] += is_root
                stats[5 + root_index] += 1
                lat, lon = fields[i_lat], fields[i_lon]
                if lat and lon:
                    try:
                        key = (round(float(lat)), round(float(lon)))
                    except ValueError:
                        key = None
                    if key is not None:
                        spot = spots.get(key)
                        if spot is None:
                            spot = spots[key] = [0, 0]
                        spot[0] += 1
                        spot[1] += quad == "4"
            else:
                counts["nogeo"] += 1
            a1, a2 = fields[ACTOR1_COUNTRY], fields[ACTOR2_COUNTRY]
            if a1 and a2:
                pair = dyad.get((a1, a2))
                if pair is None:
                    pair = dyad[(a1, a2)] = [0, 0, 0, 0]
                pair[int(quad) - 1] += 1
            url = fields[i_url]
            if url:
                codes = urls.get(url)
                if codes is None:
                    codes = urls[url] = set()
                codes.add(base_code)
                if country:
                    url_country[(country, url)] += 1

    def evidence(self) -> dict:
        """Top source URLs per location: articles that contributed the most fresh events there."""
        by_country: dict[str, list[tuple[int, str]]] = {}
        for (country, url), count in self.url_country.items():
            by_country.setdefault(country, []).append((count, url))
        table: list[str] = []
        index: dict[str, int] = {}
        top: dict[str, list[list[int]]] = {}
        for country in sorted(by_country):
            stats = self.geo.get(country)
            if not stats or stats[0] < EVIDENCE_MIN_EVENTS:
                continue
            chosen = sorted(by_country[country], key=lambda item: (-item[0], item[1]))[:EVIDENCE_PER_COUNTRY]
            entries = []
            for count, url in chosen:
                if url not in index:
                    index[url] = len(table)
                    table.append(url)
                entries.append([index[url], count])
            top[country] = entries
        return {"schema": "worldline-evidence-v1", "date": self.day.isoformat(), "urls": table, "top": top}

    def finish(self) -> tuple[dict, dict]:
        """Return (day record, same-article co-occurrence record)."""
        domains: Counter = Counter()
        cooc: Counter = Counter()
        for url, codes in self.url_codes.items():
            domains[_domain(url)] += 1
            if len(codes) > 1:
                ordered = sorted(codes)
                for i, a in enumerate(ordered):
                    for b in ordered[i + 1:]:
                        cooc[a + "|" + b] += 1
        domains.pop("", None)
        c = self.counts
        record = {
            "schema": SCHEMA, "date": self.day.isoformat(),
            "rows": c["rows"], "malformed": c["malformed"], "duplicates": c["duplicates"],
            "offday": c["offday"], "invalid": c["invalid"], "stale": c["stale"], "fresh": c["fresh"],
            "root": self.root,
            "base": dict(sorted(self.base.items())),
            "isroot": self.isroot, "articles": self.articles, "mentions": self.mentions, "sources": self.sources,
            "tone": round(self.tone, 2), "goldstein": round(self.gold, 2),
            "urls": len(self.url_codes), "domains_unique": len(domains),
            "domains": dict(domains.most_common(TOP_DOMAINS)),
            "nogeo": c["nogeo"],
            "geo": {k: {"n": v[0], "articles": v[1], "tone": round(v[2], 2), "gold": round(v[3], 2), "isroot": v[4], "root": v[5:]}
                    for k, v in sorted(self.geo.items())},
            "dyad": {f"{a}>{b}": v for (a, b), v in sorted(self.dyad.items()) if sum(v) >= MIN_DYAD},
            "spots": [[lat, lon, v[0], v[1]] for (lat, lon), v in sorted(self.spots.items(), key=lambda kv: (-kv[1][0], kv[0]))[:TOP_SPOTS]],
        }
        cooc_record = {"schema": "worldline-cooc-v1", "date": self.day.isoformat(), "urls": len(self.url_codes),
                       "pairs": {k: v for k, v in sorted(cooc.items()) if v >= MIN_COOC}}
        return record, cooc_record
