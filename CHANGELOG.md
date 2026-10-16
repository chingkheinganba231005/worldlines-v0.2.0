# Changelog

## 0.2.0 — 2026-10-16

From a synthetic-data prototype to a live, validated observatory.

**Data**
* The full GDELT 2.0 event stream since 2023-01-01 (1,384 days) from official daily files and 15-minute
  exports, verified against storage-layer and published checksums, with explicit gap records.
* Compact daily sufficient statistics (`worldline-day-v2`), same-article co-occurrence and evidence stores;
  byte-deterministic monthly files committed as the seed.

**Monitoring**
* Per-country prequential monitor for 156 countries: attention (distinct articles), event mix (ILR with
  overdispersed-multinomial covariance) and conflict share; conformal + generalized Pareto calibration;
  weighted Cauchy combination; return-period tiers; outlet gate; instrument channel for provider faults.
* Global turbulence, global event-mix monitor, Jensen–Shannon and learned optimal-transport displacement.

**Validation**
* Pre-registered protocol (committed before evaluation), Wikipedia year-article labels, stratified AUC,
  matched-budget precision, permutation nulls, bootstrap CIs, calibration on quiet days; all results
  published, including failed hypotheses. Published detector v2.1 derived from 2023 data only.
* Prospective track record from 2026-10-16, scored automatically as labels appear.

**Learned representations and scenarios**
* Event-type embeddings (PPMI + SVD of same-article co-occurrence) with checks against CAMEO structure.
* Country worldlines: monthly relational embeddings aligned by orthogonal Procrustes.
* Scenario Lab: Minnesota-regularised VAR(7), generalized impulse responses with bootstrap bands,
  Diebold–Yilmaz connectedness, out-of-sample skill.

**Live operation and site**
* Hourly GitHub Actions pipeline with a provisional rolling 24-hour nowcast; state published with the site.
* New eight-page site (Today, Map, Countries, Country, Worldlines, Lab, Track record, Method), mobile-first,
  light and dark themes, validated palettes, table views for every chart; static JSON API and RSS feed.
* 85 tests (statistics, data integrity, no look-ahead, calibration under the null, injected-event detection,
  end-to-end publishing), type checks, and a headless-browser test of every page in CI.

**Removed**
* v0.1 synthetic demo stream, FastAPI service, SQLite storage, Docker files and the v0.1 bundle (`dist/`);
  the v0.1 code remains in git history (commit `57975be`).

## 0.1.0 — 2026-10-14

Prototype built with ChatGPT: synthetic broad-domain stream with injected breaks, ILR ridge forecasts,
Jensen–Shannon and optimal-transport displacement, a source-mix diagnostic channel, four real GDELT
15-minute samples, a static dashboard and a read-only API.
