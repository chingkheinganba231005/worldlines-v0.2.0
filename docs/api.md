# Static JSON API (version 2)

Everything the website shows comes from these files, regenerated every hour. They are plain static files:
fetch them from `https://<owner>.github.io/<repository>/` + path, with no key and no rate limit beyond
GitHub Pages' own. All dates are UTC days (`YYYY-MM-DD`). Missing values are `null`, never `NaN`.

**Unusualness** `u = −log10(p)`; the **return period** is `10^u = 1/p` days ("a 1-in-N-days event for this
country"). **Tiers:** 1 *Unusual* (≥ 100 days), 2 *Rare* (≥ 365), 3 *Extreme* (≥ 1,000); 0 none.

| Path | Contents |
|---|---|
| `data/meta.json` | Build information, detector version, tiers, channel weights, families, sources and attributions, file sizes |
| `data/latest.json` | The latest complete day: pulse, brief, alarms, watch list, last 14 days, global mix, displacement, instrument, provisional 24-hour nowcast |
| `data/timeline.json` | Every day since 2023-01-01: turbulence, expected turbulence, global mix unusualness, displacement, alarm counts per tier, top alarming countries, label IDs |
| `data/grid.json` | Country × day matrix of unusualness ×10 (integers, −1 = not scored) and tiers |
| `data/countries.json` | One row per monitored country: today's unusualness, tier, 90-day sparkline, alarms in the past year |
| `data/country/{ISO3}.json` | One country's full series, its 60 most recent alarms with explanations, Wikipedia entries, top partners, worldline |
| `data/worldlines.json` | Monthly 2-D positions of every country in the learned relation space, 12-month repositioning, checks |
| `data/event_space.json` | The 141 learned CAMEO event-type vectors projected to 2-D, with family, QuadClass and checks |
| `data/scenarios.json` | Scenario Lab: impulse responses (median and 80% band), connectedness, rolling connectedness, skill |
| `data/validation.json` | The pre-registered validation results (`research/results.json`) plus the live prospective record |
| `data/labels.json` | Wikipedia year-article entries with countries and categories (CC BY-SA 4.0) |
| `data/map.json` | Country outlines pre-projected to Equal Earth (SVG path strings, centroids) |
| `feed.xml` | RSS 2.0: every alarm of the last 60 days |
| `state/{days,cooc,evidence}/YYYY-MM.jsonl.gz` | The live day store since the committed seed (gzipped JSON lines) |

## `latest.json`

```jsonc
{
  "api": "2",
  "generated_at": "2026-10-16T09:23:41Z",
  "date": "2026-10-15",                       // latest complete UTC day
  "pulse": {
    "label": "Calm",                          // Calm | Typical | Busy | Turbulent | Exceptional (percentile of the past year)
    "turbulence": 5, "expected": 7.8,         // countries at 1-in-20 days or rarer vs expected by chance
    "ratio": 0.64, "percentile_365": 27.0, "scored_countries": 156,
    "global_mix_p": 0.59, "global_mix_return_period": 2, "global_mix_text": "1-in-2 days"
  },
  "brief": ["5 of 156 monitored countries look unusual today — about what chance alone would produce (~8).", "…"],
  "alarms": [ /* country-day objects, most unusual first (see below) */ ],
  "watchlist": [ /* the 12 most unusual countries, alarm or not */ ],
  "recent": [ { "date": "2026-10-02", "turbulence": 9, "expected": 7.8, "alarms": [ { "iso3": "…", "tier": 2, "return_period": 512 } ] } ],
  "mix": { "families": ["statements", "diplomacy", "…"], "today": [0.31, "…"], "typical": [0.30, "…"] },
  "displacement": { "js_frozen": 0.0042, "js_rolling": 0.0019, "ot_frozen": 0.021, "ot_rolling": 0.011, "js_dev_median": 0.004, "ot_dev_median": 0.02 },
  "instrument": { "degraded": false, "volume_ratio": 1.02, "source_js": 0.03, "events": 118000, "articles": 24000, "outlets": 5200,
                  "provenance": { "kind": "gdelt-daily", "slots": 96, "md5": "…", "transfer_verified": true, "listed_md5_match": true, "retrieved_at": "…" } },
  "nowcast": {                                 // provisional; null if not computed
    "provisional": true, "from": "2026-10-15 09:00", "through": "2026-10-16 09:00", "slots": 96,
    "articles": 23772, "events": 119602, "forecast_for": "2026-10-16",
    "countries": [ { "iso3": "ALB", "name": "Albania", "flag": "🇦🇱", "articles": 52, "ratio": 2.32, "p": 0.032, "return_period": 31 } ]
  }
}
```

### Country-day object (alarms, country pages)

```jsonc
{
  "iso3": "BEN", "name": "Benin", "flag": "🇧🇯", "date": "2025-12-07",
  "tier": 3, "tier_label": "Extreme",
  "p": 0.00012, "return_period": 8333, "return_period_text": "1-in-5,000+ days", "unusualness": 3.92,
  "events": 412, "articles": 296, "outlets": 95,
  "drivers": [                                 // why, most unusual channel first
    { "channel": "attention", "p": 0.00004, "ratio": 9.8, "text": "Coverage is 9.8× its usual share of world news" },
    { "channel": "mix", "p": 0.003, "family": "coercion", "observed": 0.31, "expected": 0.07, "text": "Coercion makes up 31% of reports (usually about 7%)" },
    { "channel": "conflict", "p": 0.01, "observed": 0.41, "expected": 0.12, "text": "Coercion and violence are 41% of reports (usually about 12%)" }
  ],
  "evidence": [ { "url": "https://…", "domain": "…", "events": 12 } ],        // top source articles that day
  "top_codes": [ { "code": "1712", "label": "…", "events": 40, "family": "coercion" } ],
  "wikipedia": [ { "date": "2025-12-07", "text": "Elements of the Benin Armed Forces …", "id": "wp2025-…" } ]
}
```

(Values in these examples are illustrative.)

## `country/{ISO3}.json`

`series` holds one value per day from `first_date`: `u` (unusualness), `tier`, `events`, `articles`,
`outlets`, `article_ratio` (observed / expected share of world coverage), `conflict_obs` / `conflict_exp`
(coercion + violence share), and `families_permille` (seven-family composition in ‰). `today` is the latest
country-day object; `alarms` the 60 most recent alarms; `labels` the Wikipedia entries naming the country;
`partners` the top international counterparts over the last 30 days (cooperation vs conflict events);
`worldline` its nearest neighbours and month-to-month drift in the learned relation space.

## `validation.json`

The full output of `python -m worldline.cli evaluate` (see [`research/results.md`](../research/results.md)),
plus `prospective`: every alarm since 2026-10-16 with whether a Wikipedia entry for that country appeared
within the hit window (`matched`).

## Stability

Field additions do not change `api`. Renaming or removing a field, or changing a meaning, increments it.
The detector version (`meta.detector`, currently `worldline-v2.1`) changes whenever alarms would change.
