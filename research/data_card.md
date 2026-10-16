# Data card — WORLDLINE day store

| | |
|---|---|
| **What** | Daily sufficient statistics of the GDELT 2.0 event stream, one record per UTC day |
| **Period** | Committed seed: 2023-01-01 → 2026-10-15 (1,384 days); live store from 2026-10-16, published at `/state/` on the site |
| **Size** | ~72 MB for the seed (gzipped JSON lines, one file per month and store) |
| **Stores** | `data/days` (schema `worldline-day-v2`), `data/cooc` (`worldline-cooc-v1`), `data/evidence` (`worldline-evidence-v1`) |
| **Source** | Official GDELT daily files (58 columns) and 15-minute exports (61 columns), verified (see below) |
| **Licence** | GDELT-derived: free use with attribution to The GDELT Project. Code: MIT |

## Composition

Per day: rows read and how each was handled (malformed, duplicate, other day, stale, invalid, fresh); fresh
event counts by CAMEO root (20) and base code; per GDELT location (FIPS code): events, Goldstein sum, root
counts, distinct articles and publishers, top base codes; actor-country dyads by QuadClass (pairs with ≥ 2
events); top 150 publisher domains; 1° event-location grid (top 400 cells); provenance. Companion stores:
same-article co-occurrence of base codes (pairs seen in ≥ 2 articles) and up to three top source article
URLs per location with ≥ 50 events.

| Day status (seed) | Days |
|---|---:|
| Complete, from the daily file | 1,364 |
| Complete, from all 96 fifteen-minute exports | 1 |
| Partial (< 92 slots; not modelled) | 2 |
| Never published by GDELT (explicit gap records) | 17 |

## Collection and verification

* Official HTTPS endpoints only; archives verified against the storage layer's MD5 for every transfer
  (1,364 of 1,364 daily files verified) and against GDELT's published checksum list (1,363 match; the
  2023-03-22 listing differs from the intact served file and is recorded as such).
* A day is defined by `DATEADDED` (publication by GDELT), and only events dated the same or previous day
  ("fresh") enter compositions; re-extracted old events are counted as stale.
* Byte-deterministic storage: re-running acquisition on an unchanged day reproduces the same bytes.

## Fields deliberately not used by models

`NumArticles`, `NumMentions`, `NumSources`, `AvgTone`, `IsRootEvent` are revised between GDELT's two
encodings and are stored for reference only.

## Known biases

GDELT measures the news, not the world: coverage is uneven across countries, languages and topics;
syndication multiplies stories; machine coding misattributes actors, places and event types; provider outages
and ingestion changes alter volume and publisher mix. See
[`docs/data_sources_and_rights.md`](../docs/data_sources_and_rights.md) for how each is handled.

## Labels

`data/labels/`: entries of the English Wikipedia articles *2023*–*2026* ("Events" sections), frozen as
wikitext with SHA-256 manifest, parsed to dated entries with countries and categories (877 entries; 610
sociopolitical entries naming a monitored country in the test period). CC BY-SA 4.0, Wikipedia contributors.
Selective, Western-weighted and edited with hindsight: a reference, not ground truth.
