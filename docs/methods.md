# Methods

This is the technical reference for WORLDLINE v0.2: how raw GDELT exports become a return period on a
country page. The website's *Method* page explains the same ideas in plain language. The validation design
is in [`research/protocol.md`](../research/protocol.md) and its outcome in [`research/results.md`](../research/results.md).

Notation: *t* is a UTC day, *c* a country, *p* a p-value. "Prequential" means every quantity used to judge
day *t* was computed from days strictly before *t*: forecasts, their covariances, calibration scores and any
normalisation. A test (`tests/test_monitor.py::test_no_leakage_into_earlier_days`) checks this end to end by
deleting every later day and verifying that earlier scores do not change by a single bit.

---

## 1. Data

### 1.1 One stream, two encodings

GDELT 2.0 publishes its event table twice:

| Encoding | URL | Columns | Cadence |
|---|---|---|---|
| Daily file | `data.gdeltproject.org/events/YYYYMMDD.export.CSV.zip` | 58 | once per UTC day |
| 15-minute export | `data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.export.CSV.zip` | 61 | every 15 minutes |

On 2026-10-13 we checked that a daily file is exactly the union of that day's 96 fifteen-minute exports
(116,603 identical `GLOBALEVENTID`s). History therefore comes from daily files and live monitoring from
15-minute exports, and both are the same dataset. Only the attention fields differ: the daily file carries
end-of-day revised `NumArticles`, `NumMentions`, `NumSources`, `AvgTone` and `IsRootEvent`, the 15-minute
files their first extraction. **No model uses those five fields.** `tests/test_aggregate.py` checks that both
encodings produce identical day records on every other field.

### 1.2 Integrity

* Only official HTTPS archive URLs on `data.gdeltproject.org` are requested. Redirects are refused. Archives
  are size-capped (64 MB), must contain exactly one member with an official name, and may not expand more
  than 40× (zip-bomb guard).
* **Transfer integrity:** GDELT is served from Google Cloud Storage, which declares each stored object's
  MD5 (`x-goog-hash`, or a plain-MD5 `ETag`). Every download is hashed and compared; a mismatch is a
  corrupted transfer and is retried (it happened once, on 2025-02-13).
* **Publisher list:** GDELT also publishes an `md5sums` list for daily files. Agreement is recorded per day
  (`listed_md5_match`): 1,363 of 1,364 daily files match. The exception, 2023-03-22, is served intact
  (storage-layer MD5 verified) but differs from its listed checksum, so the disagreement is recorded rather
  than hidden or treated as corruption.
* **Gaps are explicit.** A day the provider never published becomes a `gap` record, never zero activity. Days
  with fewer than 92 of 96 slots are "partial" and are not modelled. Of the 1,384 days from 2023-01-01 to
  2026-10-15, 1,365 are complete, 2 are partial and 17 were never published by the provider.
* Finished days are never re-downloaded by the live pipeline; recent 15-minute days are upgraded to the daily
  file when it appears.

### 1.3 What a "day" contains

A day is defined by `DATEADDED` (when the provider published a record), never by the event's own date, so a
day's record is final once published. Only **fresh** events enter the analysis: `SQLDATE` on the same or the
previous day. GDELT re-extracts anniversaries and retrospective mentions; these are counted as `stale`, not
silently dropped. Records with malformed rows, duplicate IDs, unknown CAMEO roots or invalid QuadClass are
counted in their own fields. One record is one vote; a record is a machine-coded claim found in the news,
not a verified event.

Each day record (`schema worldline-day-v2`, gzipped JSON lines per month in `data/days/`) holds sufficient
statistics: counts by CAMEO root (20) and base code (~300); per FIPS location the event count, Goldstein sum,
root counts, number of distinct articles (`urls`) and publisher domains (`outlets`), and its top base codes;
actor-country dyads by QuadClass; the 150 largest publisher domains; a 1° grid of event locations; and full
provenance (URLs, MD5/SHA-256, retrieval time, slot counts). Two companion stores hold same-article CAMEO
co-occurrence (`data/cooc/`, for embeddings) and the top source articles per location (`data/evidence/`).
Storage is byte-deterministic (sorted keys, gzip mtime 0), so an unchanged month produces an unchanged file.

## 2. The panel

Records are assembled into calendar-aligned arrays (`backend/worldline/panel.py`). Every calendar day gets a
row; missing, partial and gap days are present but flagged `usable = False`. FIPS location codes map to ISO
3166 alpha-3 via GeoNames (Gaza and the West Bank both map to Palestine). CAMEO roots are grouped into seven
event families: statements (01–02), diplomacy (03–05), aid & cooperation (06–09), criticism & threats
(10–13), protests (14), coercion (15–17) and violence (18–20).

A country is **monitored** when its median number of fresh events per day in the development year (2023) is
at least 30: 156 countries.

## 3. The instrument channel

Before asking whether a country is unusual, WORLDLINE asks whether the *measuring instrument* is. A day is
**degraded** when global fresh volume is below 0.35× or above 1.6× the median of the same weekday over the
previous eight usable weeks, or when the publisher mix (Jensen–Shannon divergence between the day's top
publisher domains and the trailing 28-day average) exceeds 0.17, about its 99.5th percentile. Holiday lulls
lower volume but keep the publisher mix; ingestion faults and backlogs change it (the 2023-03-22 outage
reached 0.61). Degraded days are not scored, never alarm, and are excluded from training and calibration of
later days.

## 4. Country channels

Each channel turns a daily observation *y<sub>t</sub>* into a forecast surprise.

**Forecasts.** Weekday-aware ridge regression with an intercept, six effect-coded weekday terms (not
shrunk) and three standardised lag features: yesterday's value and the trailing 7- and 28-day means of usable
days. Each fit uses the trailing 365 days, needs at least 90 usable training days, and is refreshed weekly;
the block [τ, τ+7) is predicted by the fit made on days before τ. Ridge penalty: 0.05 × training rows.

**Attention** (published in *distinct articles*). *y<sub>t</sub>* = log((a<sub>c,t</sub> + 0.5) / A<sub>t</sub>),
the log share of the day's distinct articles that contain a fresh event located in *c*. Score = residual
(upper tail). Article counts are used rather than event counts because one article can yield dozens of
machine-coded events; this was chosen on 2023 data (AUC 0.773 vs 0.757).

**Event mix.** The seven-family composition with +0.5 smoothing, in isometric log-ratio coordinates
(Helmert basis). The forecast residual *r<sub>t</sub>* is scored by a Mahalanobis norm with
Σ<sub>t</sub> = Σ<sub>process</sub> + Σ<sub>sampling</sub>(n<sub>t</sub>), where the sampling part is the
multinomial covariance at the forecast shares mapped to ILR coordinates, B diag(1/(n p̂)) Bᵀ, and the process
part is the residual covariance over the calibration window minus its average sampling part (eigenvalues
floored at 10⁻⁴). This makes a 15-event day and a 5,000-event day comparable.

**Conflict share.** *y<sub>t</sub>* = logit of the coercion + violence share; residual divided by
√(process + sampling) variance in the same way.

**Semantic channel** (research only, hypothesis H4). The day's root mix is mapped to its centroid in the
learned 16-dimensional event-type space (§7) and scored like the event mix, with the sampling covariance of
a multinomial mean of embedding vectors. It did not improve detection and is not published.

## 5. Calibration: from surprise to return period

Each channel's score on day *t* is ranked against the same country's own scores over the previous 365 days
(at least 60 required):

* in the body, the split-conformal p-value p = (1 + #{s<sub>i</sub> ≥ s}) / (n + 1);
* above the 90th percentile, once at least 20 exceedances are available, a peaks-over-threshold generalized
  Pareto tail fitted by probability-weighted moments (Hosking & Wallis 1987; shape clamped to [−0.5, 0.5])
  extrapolates beyond the window,
  p = (k / (n + 1)) · (1 + ξ (s − u)/σ)<sup>−1/ξ</sup>, floored at 10⁻⁶.

Under exchangeability the conformal part is exactly valid; news is serially dependent and drifts, so on real
data calibration is **measured**: on 143,134 presumed-quiet test country-days, P(p ≤ 0.05) = 0.051,
P(p ≤ 0.01) = 0.012, P(p ≤ 0.001) = 0.0032. The tail is therefore close to nominal at 1-in-20 and 1-in-100
and about 3× too generous at 1-in-1,000 (an upper bound, since "quiet" days still contain unlisted events).

The return period shown to people is 1/p days ("a 1-in-400-days event for this country"), displayed as
"5,000+" beyond 5,000 days, where it is an extrapolation of the fitted tail.

## 6. Combination and alarms

Channels are combined with the **Cauchy combination test** (Liu & Xie 2020),
T = Σ w<sub>i</sub> tan((0.5 − p<sub>i</sub>) π) / Σ w<sub>i</sub>, p = 0.5 − arctan(T)/π, which stays valid under
arbitrary dependence between channels in the tail. The published detector **v2.1** uses weights
proportional to each channel's development-year AUC excess over 0.5: attention in articles 0.70, event mix
0.26, conflict share 0.04 (`data/model/published.json`).

A country-day **alarms** when its combined return period is at least 100 days (*unusual*), 365 (*rare*) or
1,000 (*extreme*), at least 20 distinct publishers reported from the country that day, and the instrument is
healthy. The outlet gate removes alarms driven by one or two prolific sources (chosen on 2023 data).

Global summaries on the *Today* page:

* **Turbulence:** how many monitored countries are at 1-in-20 days or rarer, against the ~5% expected by chance.
* **Global event mix:** the same ILR monitor applied to the world's root composition.
* **Displacement:** Jensen–Shannon divergence and optimal-transport distance (exact, by linear programming)
  between today's mix of CAMEO base codes and both the 2023 reference and the trailing 28 days. The
  transport ground cost is learned (§7): moving mass between semantically close event types is cheap.

## 7. Learned embeddings

**Event types.** Same-article co-occurrence of CAMEO base codes (two codes co-occur when one news article
yields fresh events of both) over 2023: 32.3 million co-occurrence pairs among 141 codes with at least 200
events. Positive pointwise mutual information with context-distribution smoothing (α = 0.75), then a rank-16
truncated SVD with deterministic sign convention, rows normalised. Nothing about CAMEO's own hierarchy is
given to the model. Checks against what it was *not* told:

| Check | Result | Chance |
|---|---:|---:|
| 5-nearest-neighbour vote recovers QuadClass | 0.539 | majority 0.312; label permutation 0.263 (95th pct 0.348) |
| Cross-validated linear readout of the Goldstein scale (Spearman) | 0.604 | 0 |

The geometry supplies the optimal-transport ground cost (1 − cosine similarity) and the research-only
semantic channel.

**Country worldlines.** For each 3-month window, a country × (partner × direction × QuadClass) matrix of
international actor dyads (domestic dyads excluded) → PPMI → rank-16 SVD. Every window is rotated onto a
whole-period anchor embedding by orthogonal Procrustes, so positions are comparable over time, and the
aligned positions are projected onto the first two principal axes of all windows pooled. Checks for the
latest month: a country's five nearest neighbours share its continent 91% of the time (permutation mean 23%,
95th percentile 28%); the median monthly step in the aligned space is 0.044 (cosine distance) against 0.93
for unaligned comparison. *Repositioning* is the 12-month cosine distance of a country's position; it is
only reported when the country's relational volume exceeds 1,500 dyadic events per window, below which
positions are mostly sampling noise.

## 8. Scenario Lab

A vector autoregression of order 7 on log(1 + daily coercion + violence events) for the 30 countries with the
most 2023 conflict events, with intercept, weekday terms and log world volume as controls, on clean days only
(every row's 7-day history must be usable and non-degraded).

* **Estimation:** equation-by-equation ridge with Minnesota-style shrinkage on standardised lags (Litterman
  1986): own lag *l* penalised λ·l, other countries' lags λ·κ·l. (λ, κ) is chosen by forward validation on the
  last 20% of the fit period (selected λ = 10, κ = 1,000, i.e. strong shrinkage of cross-country effects).
* **Scenarios:** generalized impulse responses (Pesaran & Shin 1998), which do not depend on variable order,
  to a +1 log-unit shock, 30 days ahead, with 80% bands from a 200-draw wild (Rademacher) residual bootstrap.
* **Connectedness:** generalized forecast-error variance decomposition at 10 days and the Diebold–Yilmaz
  (2012) total, to, from and net spillover indices, plus a rolling 12-month total.
* **Skill:** one-step out-of-sample RMSE from 2026-01-01 against per-country autoregressions with the same
  controls: **+0.01%** on average (range −1.3% to +1.5%).

The Lab is honest about what this means: cross-country dynamics add essentially no short-term forecasting
power. Impulse responses describe *predictive (Granger) associations learned from news coverage*, not causal
effects of events, and the site says so next to every chart.

## 9. Live monitoring and the nowcast

Every hour a GitHub Actions workflow (`.github/workflows/live.yml`) restores the live day store from the
published site, fetches the 96 newest 15-minute exports once, and uses them three ways: today's partial day
record, any recent day that is missing or still provisional (daily file if published, otherwise all 96
slots), and a **rolling 24-hour window**, which spans every time zone and is therefore comparable with a whole
day. The nowcast scores each country's article share in that window against the model's forecast for the
first unfinished day and its calibration scores. It is labelled provisional: a full day replaces it once the
UTC day closes.

## 10. Validation and the prospective record

Pre-registered before any test-period comparison: Wikipedia year-article entries (2023–2026, frozen by
SHA-256), mapped to countries by a gazetteer and to categories by declared keyword rules; development year
2023, test period 2024-01-01 → 2026-10-15; stratified AUC over complete 4-day windows; alarm precision,
recall and lift; circular-shift permutation nulls; bootstrap confidence intervals; calibration on presumed
quiet days. Hypotheses, metrics and outcomes, including the ones that failed, are in
[`research/`](../research/). The published v2.1 detector was designed after that run on 2023 data only; its
test numbers are labelled post hoc.

From **2026-10-16** every alarm is recorded before any label for it can exist. The *Track record* page scores
these prospective alarms against the same Wikipedia articles, refreshed daily (an alarm on day *d* matches an
entry dated *d* − 2 … *d* + 1 for that country). Wikipedia's year articles are edited with a lag, so recent
alarms may match later.

## 11. Reproducibility

* `python -m worldline.cli evaluate` re-runs the whole protocol from the committed day store and reproduces
  `research/results.json` exactly (random draws are seeded).
* `python -m pytest` runs 85 tests in about 20 seconds, including an end-to-end run of the full pipeline on
  synthetic data with an injected event, a no-look-ahead test, a calibration test under the null and
  checks that the frozen labels are exactly what the parser produces from the frozen Wikipedia pages.
* Pinned dependencies (`requirements.lock`): NumPy and SciPy only at runtime.

## References

* Cauchy combination: Liu, Y. & Xie, J. (2020). *Cauchy combination test.* JASA 115(529).
* Conformal prediction: Vovk, Gammerman & Shafer (2005). *Algorithmic Learning in a Random World.*
* Generalized Pareto by PWM: Hosking, J. R. M. & Wallis, J. R. (1987). *Technometrics* 29(3).
* Compositional data: Egozcue et al. (2003). *Isometric logratio transformations.* Math. Geology 35(3).
* Word embeddings as matrix factorisation: Levy, O. & Goldberg, Y. (2014); Levy, Goldberg & Dagan (2015).
* Procrustes alignment of embeddings over time: Hamilton, Leskovec & Jurafsky (2016).
* Generalized impulse responses: Pesaran, H. H. & Shin, Y. (1998). *Economics Letters* 58(1).
* Connectedness: Diebold, F. X. & Yilmaz, K. (2012). *International Journal of Forecasting* 28(1).
* Minnesota prior: Litterman, R. B. (1986). *Journal of Business & Economic Statistics* 4(1).
* False discovery rate: Benjamini, Y. & Hochberg, Y. (1995). *JRSS B* 57(1).
* GDELT: Leetaru, K. & Schrodt, P. A. (2013). *GDELT: Global data on events, location, and tone.*
