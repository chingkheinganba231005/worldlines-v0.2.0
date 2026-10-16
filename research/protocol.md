# Research protocol v2.0 — real-data validation

Declared on 2026-10-16, **before** any detector was compared with labels in the test period.
Implemented in `backend/worldline/validate.py` (`PROTOCOL_VERSION = worldline-validation-protocol-2.0`).
Supersedes protocol v0.1, which evaluated only synthetic streams.

## Question

Do WORLDLINE's country alarms, computed prequentially from GDELT event metadata, coincide with
independently documented, internationally notable events more often than chance and more often than a
naive news-volume spike detector?

## Data and periods

* **Signal:** GDELT 2.0 event stream, 2023-01-01 to the last complete UTC day. Daily aggregates of fresh
  event records (SQLDATE within one day of DATEADDED), revision-stable count fields only.
* **Development period:** 2023 — model configuration, monitored-country list, embedding training.
* **Test period:** 2024-01-01 to the last complete day. Reported once; no parameter is tuned on it.
* **Monitored countries:** median ≥ 30 fresh events per day in 2023 (156 countries).

## Labels

Entries in the "Events" sections of the English Wikipedia articles *2023*, *2024*, *2025* and *2026*,
frozen by SHA-256 (`data/labels/wikipedia_year_events.json`, `manifest`). Each entry contributes a positive
label (country, date) for every monitored country it names (gazetteer of names, demonyms, capitals and key
places in `backend/worldline/labels.py`). Categories are coarse keyword rules declared in the same file:

* **Primary label set:** entries categorised *conflict* or *political* (GDELT's CAMEO scope).
* Secondary sets: all entries; *disaster* entries.

Known biases: English-language and Western salience; editors list consequential events with hindsight; the
gazetteer can miss or over-attribute countries. Labels are therefore an *independent but noisy reference*,
not ground truth.

## Detectors (all prequential: forecasts, covariances and calibration use strictly earlier days)

| ID | Detector | Score |
|----|----------|-------|
| D0 | Random | uniform |
| D1 | Naive news spike | z of log(events+1) vs same weekday, previous 4 weeks |
| D2 | Attention channel | forecast surprise in share of world coverage |
| D3 | Event-mix channel | ILR composition surprise, overdispersed multinomial covariance |
| D4 | Conflict channel | logit coercion+violence share surprise |
| D5 | **WORLDLINE combined** | Cauchy combination of D2–D4 |
| D6 | Combined + learned semantic channel | Cauchy combination of D2–D4 and an embedding-centroid surprise |

Alarms: combined return period ≥ 100 days (*notable*), ≥ 365 (*rare*), ≥ 1000 (*extreme*); not issued on
days the instrument channel marks degraded.

## Matching and metrics

* Hit window: an alarm on day *d* matches a label dated *e* when *d − e* ∈ [−1, +2].
* **Event recall** per tier; **alarm precision** per tier; **lift** = precision / base rate, where the base
  rate is the share of scored country-days that have a label within the window.
* **Stratified AUC:** windowed maximum unusualness (−log₁₀ p) on labelled (country, date) pairs versus the
  same country's scored test days with no label within ±7 days; pooled over countries by pair count.
* **Significance:** circular-shift permutation tests within countries (1,000 shifts for precision, 200 for
  AUC), which preserve each country's alarm and label clustering.
* **Uncertainty:** percentile bootstrap over positive labels (300 replicates), including paired AUC
  differences between detectors.
* **Calibration check:** share of combined p-values ≤ α on country-days with no label of any kind within
  ±7 days (presumed quiet days).

## Hypotheses

* **H1 (primary):** D5 stratified AUC > 0.5 and alarm precision > base rate, permutation p < 0.01.
* **H2:** D5 AUC exceeds D1 AUC (paired bootstrap 95% CI of the difference excludes 0).
* **H3:** event-mix and conflict channels carry signal on their own (D3, D4 AUC > 0.5).
* **H4:** the learned semantic channel improves D5 (D6 − D5 CI excludes 0). Expected to be small or null.

Every result is reported, including failed hypotheses, in `research/results.md`.

## Disclosures made before evaluation

* Instrument (coverage) thresholds were set after inspecting the whole record's publisher-mix and volume
  series (2023 outage and backlog, 2024-06-15/16 publisher break). They do not use labels.
* During bug checks the global event-mix monitor's lowest-p dates over the whole record were printed once;
  no parameter was changed afterwards.
* GDELT records are machine-extracted and unverified; one record is one vote; NumArticles/NumMentions and tone
  are revised between encodings and are excluded from models.
