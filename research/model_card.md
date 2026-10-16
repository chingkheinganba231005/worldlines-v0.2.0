# Model card — WORLDLINE detector v2.1

| | |
|---|---|
| **Version** | `worldline-v2.1` (monitor `worldline-monitor-2.0`; embeddings `ppmi-svd-cooc-2023-d16`; scenarios `ridge-var7-girf-v1`) |
| **Task** | Flag country-days on which the news record about a country is unusual *for that country* |
| **Output** | Per country and UTC day: p-value, return period (1/p days), tier (≥ 100 / 365 / 1,000 days), drivers, evidence |
| **Input** | Daily aggregates of fresh GDELT 2.0 event records (counts by country, CAMEO family, distinct articles, publishers) |
| **Coverage** | 156 countries with a median of ≥ 30 fresh events per day in 2023; 2023-01-01 onward, updated hourly |
| **Compute** | CPU only, NumPy/SciPy; full history in about two minutes; deterministic |

## How it works (short)

Three prequential channels per country (attention in distinct articles; seven-family event mix in ILR
coordinates with overdispersed-multinomial covariance; logit coercion + violence share), each forecast by a
weekday-aware ridge regression on the trailing year and scored against the country's own previous 365 days
of scores (conformal ranks, generalized Pareto tail). Channels are combined by a weighted Cauchy combination
(0.70 / 0.26 / 0.04). Alarms need a return period ≥ 100 days, ≥ 20 distinct publishers, and a healthy
instrument. Details: [`docs/methods.md`](../docs/methods.md).

## Development and evaluation

* **Development data:** 2023 (all design choices, including the v2.1 weights, article-based attention and the
  outlet gate).
* **Pre-registered test:** 2024-01-01 → 2026-10-15 against 610 Wikipedia-documented sociopolitical
  country-dates ([protocol](protocol.md), [results](results.md)).

| Metric (test period) | Pre-registered D5 | v2.1 (post hoc) | Naive volume spike | Random |
|---|---:|---:|---:|---:|
| Stratified AUC | 0.719 (0.696–0.739) | 0.781 (0.758–0.798) | 0.742 (0.719–0.762) | 0.501 |
| Precision at matched budget (1,991 alarms) | 8.5% | 11.4% | 9.7% | 1.7% |
| Rare-tier precision / lift | 10.1% / 6.8× | 16.2% / 10.8× | 6.5% / 4.4× | 2.8% / 1.8× |
| Rare-tier alarms per country-year | 2.0 | 1.6 | 17.0 | 0.9 |

* **Calibration** on 143,134 presumed-quiet country-days: P(p ≤ 0.05) = 0.051, P(p ≤ 0.01) = 0.012,
  P(p ≤ 0.001) = 0.0032. Close to nominal for return periods up to ~100 days; about 3× too frequent at
  1,000 days (an upper bound, since quiet days contain unlisted events).
* **Unbiased evaluation:** the prospective record from 2026-10-16, published on the site's *Track record* page.

## Intended use

Situational awareness and research: noticing *where* the global news record is changing unusually, and
reading *how* it changed, with links to the underlying reporting. Teaching and research on event data,
calibration and honest validation.

## Not intended for

Operational, security, humanitarian, financial or legal decisions without independent verification;
ranking countries against each other; inferring that an event happened, who is responsible, or what will
happen next; monitoring individuals.

## Known limitations

* Measures **news coverage**, which is uneven across countries and languages and shaped by editorial
  salience; a quiet news record is not a quiet country.
* GDELT records are machine-coded and contain extraction errors; one story can generate many records
  (mitigated by counting distinct articles and requiring ≥ 20 publishers).
* The best single signal is attention: v2.1 is only modestly different from "coverage rose unusually",
  and a naive volume spike is a strong baseline. The event-mix channel adds explanation more than detection;
  the conflict-share channel alone is at chance against these labels.
* Learned embeddings did not improve detection (pre-registered H4) and are not used for alarms.
* Labels are Wikipedia year articles: selective, Western-weighted, lagged. Precision against them is a
  conservative lower bound.
* Return periods beyond ~1,000 days are tail extrapolations and are displayed as "5,000+" beyond 5,000.

## Ethical considerations

Alarms about countries in crisis can attract attention to them; WORLDLINE states on every alarm that it is a
statistical signal in news metadata, links the reporting it is based on, and publishes its misses and false
alarms alongside its hits. No personal data is processed; actor names are not stored.
