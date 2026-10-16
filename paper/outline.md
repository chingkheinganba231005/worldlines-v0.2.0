# Manuscript outline — "Is today unusual for this country? A pre-registered, live evaluation of calibrated anomaly detection in the global news record"

Status: draft outline; results sections can be written from `research/results.md` now and updated with the
prospective record after 6–12 months.

1. **Introduction.** Event data (GDELT, ICEWS, ACLED) are widely used to monitor the world, but alarms built
   on them are rarely calibrated per country, rarely validated against independent records, and almost never
   tested prospectively. We ask a narrow question with a measurable answer: when is a country's news record
   unusual *for that country*, and how often do such days coincide with independently documented events?
2. **Related work.** Event-data early warning (e.g. ICEWS, ViEWS) and its validation practices; conformal
   prediction and extreme-value tails for time-series anomaly scores; combination of dependent p-values
   (Cauchy combination); compositional data analysis; distributional shift (JSD, optimal transport); word
   embeddings as PMI factorisation and their diachronic alignment; VAR connectedness. Novelty to verify by a
   current literature review before submission.
3. **Data.** GDELT 2.0 as one stream in two encodings (verified equivalence); integrity (storage-layer and
   published checksums, explicit gaps); freshness filter; revision-stable fields; the instrument channel;
   1,384 days, 156 countries.
4. **Method.** Prequential weekday-aware forecasts; three channels with explicit sampling variance;
   conformal + generalized Pareto calibration; weighted Cauchy combination; tiers as return periods; outlet
   gate. Learned event-type geometry and country worldlines; VAR scenarios.
5. **Evaluation design.** Pre-registration (protocol committed before evaluation); Wikipedia year articles as
   independent labels with declared gazetteer and category rules; stratified AUC over complete windows;
   matched-budget precision; circular-shift nulls; bootstrap CIs; calibration on presumed-quiet days;
   development/test split; disclosure of every deviation.
6. **Results.** H1 supported (AUC 0.719; alarm lift 5.7–6.8×); H2 not supported (naive volume spike 0.742);
   H3 partly (event mix 0.629, conflict share at chance); H4 not supported (learned semantic channel).
   Post hoc v2.1 (AUC 0.781, rare-tier lift 10.8×) and why it is post hoc. Calibration: near nominal to
   1-in-100, ~3× at 1-in-1,000. Per-country heterogeneity. Case studies of hits and misses.
7. **Prospective record.** Alarms published hourly before labels exist, scored automatically from
   2026-10-16; report after a fixed horizon declared in advance (e.g. 12 months).
8. **Discussion.** Attention dominates detection; composition adds explanation; what a "news-record anomaly"
   is and is not; selection bias of labels and of news; why simple, inspectable learned representations;
   scenario analysis as predictive association, not causation.
9. **Limitations and ethics.** Coverage inequality; label bias; machine-coding error; dependence between
   alarms; misuse risks (ranking countries, operational use).
10. **Reproducibility.** Code, day store, frozen labels and protocol in one repository; `evaluate`
    reproduces every number bit-for-bit; live site and JSON API.

Key references: Liu & Xie (2020); Vovk et al. (2005); Hosking & Wallis (1987); Egozcue et al. (2003); Levy &
Goldberg (2014); Hamilton et al. (2016); Pesaran & Shin (1998); Diebold & Yilmaz (2012); Leetaru & Schrodt
(2013); Benjamini & Hochberg (1995); Dawid (1984) on prequential analysis.
