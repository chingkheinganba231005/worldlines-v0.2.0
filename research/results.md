# WORLDLINE v0.2 — real-data validation results

Protocol `worldline-validation-protocol-2.0.1` (see `research/protocol.md`). Generated 2026-10-16T08:04:55+00:00.

* Test period: **2024-01-01 → 2026-10-15** (1019 days), 156 monitored countries, 153,504 scored country-days.
* Labels (Wikipedia year articles, country-tagged): 610 sociopolitical (primary), 815 all, 127 disaster.
* Hit window: alarm from -1 to +2 days around the listed date.

## Threshold-free discrimination (primary labels)

| Detector | AUC | 95% CI | Shift-null mean | Permutation p |
|---|---:|---:|---:|---:|
| D0 Random scores (200 draws) | 0.501 | 0.480–0.522 | — | — |
| D1 Naive news-volume spike | 0.742 | 0.719–0.762 | 0.501 | 0.0050 |
| D2 Attention channel | 0.771 | 0.749–0.792 | 0.499 | 0.0050 |
| D2a Attention in articles (post hoc) | 0.796 | 0.773–0.814 | 0.498 | 0.0050 |
| D3 Event-mix channel | 0.629 | 0.604–0.656 | 0.500 | 0.0050 |
| D4 Conflict channel | 0.511 | 0.488–0.537 | 0.501 | 0.2438 |
| D5 WORLDLINE combined (published) | 0.719 | 0.696–0.739 | 0.500 | 0.0050 |
| D6 Combined + learned semantic channel | 0.713 | 0.690–0.734 | 0.500 | 0.0050 |
| D7 WORLDLINE v2.1 published (post hoc) | 0.781 | 0.758–0.798 | 0.499 | 0.0050 |

AUC = probability that a labelled country-date window has a higher maximum unusualness than an unlabelled day of the same country. 0.5 is chance.

## Paired comparisons

* **D5 − D1 (WORLDLINE vs naive volume spike):** -0.023 (95% CI -0.047 to +0.001).
* **D5 − D2 (adding event-mix and conflict channels to attention):** -0.052 (95% CI -0.071 to -0.034).
* **D6 − D5 (adding the learned semantic channel):** -0.006 (95% CI -0.016 to +0.004).

## Precision at a matched alarm budget

Each detector raises exactly as many test alarms as D5's notable tier (1991), taking its most unusual country-days. This removes differences in alarm rates.

| Detector | Precision | Lift | Recall |
|---|---:|---:|---:|
| D0 Random scores | 0.017 | 1.10× | 0.052 |
| D1 Naive news-volume spike | 0.097 | 6.49× | 0.208 |
| D2 Attention channel | 0.116 | 7.73× | 0.287 |
| D2a Attention in articles (post hoc) | 0.127 | 8.47× | 0.328 |
| D3 Event-mix channel | 0.055 | 3.68× | 0.151 |
| D4 Conflict channel | 0.036 | 2.41× | 0.110 |
| D5 WORLDLINE combined (published) | 0.085 | 5.66× | 0.239 |
| D6 Combined + learned semantic channel | 0.082 | 5.49× | 0.223 |
| D7 WORLDLINE v2.1 published (post hoc) | 0.114 | 7.57× | 0.307 |

## Alarms (primary labels)

| Detector | Tier | Alarms / country-year | Precision | Base rate | Lift | Shift-null precision (p) | Recall |
|---|---|---:|---:|---:|---:|---:|---:|
| D0 | notable | 3.44 | 0.017 | 0.015 | 1.11× | 0.014 (p=0.2008) | 26/610 = 0.043 |
| D0 | rare | 0.91 | 0.028 | 0.015 | 1.85× | 0.015 (p=0.0360) | 12/610 = 0.020 |
| D0 | extreme | 0.34 | 0.020 | 0.015 | 1.33× | 0.016 (p=0.4505) | 3/610 = 0.005 |
| D1 | notable | 23.84 | 0.055 | 0.015 | 3.68× | 0.015 (p=0.0010) | 277/610 = 0.454 |
| D1 | rare | 16.98 | 0.065 | 0.015 | 4.35× | 0.015 (p=0.0010) | 252/610 = 0.413 |
| D1 | extreme | 13.72 | 0.070 | 0.015 | 4.65× | 0.015 (p=0.0010) | 234/610 = 0.384 |
| D2 | notable | 4.50 | 0.117 | 0.015 | 7.79× | 0.014 (p=0.0010) | 175/610 = 0.287 |
| D2 | rare | 1.62 | 0.160 | 0.015 | 10.67× | 0.014 (p=0.0010) | 98/610 = 0.161 |
| D2 | extreme | 0.83 | 0.169 | 0.015 | 11.23× | 0.014 (p=0.0010) | 55/610 = 0.090 |
| D2a | notable | 4.46 | 0.128 | 0.015 | 8.52× | 0.014 (p=0.0010) | 198/610 = 0.325 |
| D2a | rare | 1.65 | 0.179 | 0.015 | 11.94× | 0.015 (p=0.0010) | 113/610 = 0.185 |
| D2a | extreme | 0.85 | 0.192 | 0.015 | 12.83× | 0.013 (p=0.0010) | 67/610 = 0.110 |
| D3 | notable | 3.81 | 0.059 | 0.015 | 3.94× | 0.017 (p=0.0010) | 84/610 = 0.138 |
| D3 | rare | 1.26 | 0.084 | 0.015 | 5.57× | 0.016 (p=0.0010) | 44/610 = 0.072 |
| D3 | extreme | 0.68 | 0.091 | 0.015 | 6.04× | 0.016 (p=0.0010) | 25/610 = 0.041 |
| D4 | notable | 3.57 | 0.033 | 0.015 | 2.19× | 0.016 (p=0.0010) | 49/610 = 0.080 |
| D4 | rare | 1.27 | 0.054 | 0.015 | 3.62× | 0.016 (p=0.0010) | 30/610 = 0.049 |
| D4 | extreme | 0.74 | 0.043 | 0.015 | 2.90× | 0.016 (p=0.0020) | 14/610 = 0.023 |
| D5 | notable | 4.57 | 0.085 | 0.015 | 5.66× | 0.015 (p=0.0010) | 146/610 = 0.239 |
| D5 | rare | 2.02 | 0.101 | 0.015 | 6.76× | 0.015 (p=0.0010) | 81/610 = 0.133 |
| D5 | extreme | 1.29 | 0.101 | 0.015 | 6.75× | 0.015 (p=0.0010) | 51/610 = 0.084 |
| D6 | notable | 4.61 | 0.082 | 0.015 | 5.44× | 0.015 (p=0.0010) | 136/610 = 0.223 |
| D6 | rare | 2.15 | 0.095 | 0.015 | 6.34× | 0.016 (p=0.0010) | 79/610 = 0.130 |
| D6 | extreme | 1.44 | 0.094 | 0.015 | 6.26× | 0.015 (p=0.0010) | 51/610 = 0.084 |
| D7 | notable | 3.89 | 0.136 | 0.015 | 9.07× | 0.017 (p=0.0010) | 188/610 = 0.308 |
| D7 | rare | 1.64 | 0.162 | 0.015 | 10.83× | 0.017 (p=0.0010) | 106/610 = 0.174 |
| D7 | extreme | 1.00 | 0.159 | 0.015 | 10.60× | 0.018 (p=0.0010) | 62/610 = 0.102 |

## Calibration on presumed-quiet country-days

On 143,134 test country-days with no Wikipedia entry for that country within ±7 days: P(p ≤ 0.05) = 0.0511, P(p ≤ 0.01) = 0.0122, P(p ≤ 0.001) = 0.00317 (nominal 0.05, 0.01, 0.001; detector D7). Quiet days still contain real but unlisted events, so excess here is an upper bound on miscalibration.

## Most extreme test-period alarms of the published detector (one per country-month)

Return periods beyond 5,000 days are extrapolations of the fitted tail and are shown as ≥ 5,000.

| Date | Country | Return period (days) | Outlets | Matching Wikipedia entry (±window) |
|---|---|---:|---:|---|
| 2025-07-21 | Costa Rica | ≥ 5,000 | 75 | — |
| 2025-12-21 | North Korea | ≥ 5,000 | 27 | — |
| 2024-07-14 | United States | ≥ 5,000 | 2297 | While campaigning for the 2024 United States presidential election, former President Donald Trump is shot in the right ear in an assassinati |
| 2025-10-27 | Brunei | ≥ 5,000 | 49 | — |
| 2026-04-13 | Algeria | ≥ 5,000 | 168 | — |
| 2025-03-11 | Philippines | ≥ 5,000 | 251 | The former President of the Philippines, Rodrigo Duterte, is arrested in the Philippines after being served an arrest warrant from the Inter |
| 2026-05-28 | Kenya | ≥ 5,000 | 131 | — |
| 2024-08-07 | Austria | ≥ 5,000 | 116 | — |
| 2025-11-28 | Senegal | ≥ 5,000 | 65 | — |
| 2025-11-17 | Bangladesh | ≥ 5,000 | 200 | Former prime minister of Bangladesh Sheikh Hasina is found guilty of crimes against humanity by a Bangladeshi tribunal and sentenced to deat |
| 2025-07-24 | Cambodia | ≥ 5,000 | 240 | Armed conflicts break out between Cambodia and Thailand after the escalation of a border dispute. At least 39 people are killed and more tha |
| 2025-12-07 | Benin | ≥ 5,000 | 95 | Elements of the Benin Armed Forces, led by Pascal Tigri, announce a coup d'état against president Patrice Talon and the creation of a milita |
| 2025-12-26 | Nigeria | ≥ 5,000 | 362 | The United States, in cooperation with the Nigerian government, initiates a series of airstrikes targeting Islamic State-affiliated militant |
| 2024-03-11 | Jamaica | ≥ 5,000 | 84 | — |
| 2024-02-24 | Mali | ≥ 5,000 | 37 | — |
| 2024-03-12 | Romania | ≥ 5,000 | 153 | — |
| 2024-07-27 | Laos | ≥ 5,000 | 111 | — |
| 2025-08-17 | Finland | ≥ 5,000 | 62 | — |
| 2026-02-28 | United Arab Emirates | ≥ 5,000 | 277 | — |
| 2025-07-19 | Congo-Brazzaville | ≥ 5,000 | 36 | — |
| 2026-05-03 | Morocco | ≥ 5,000 | 64 | — |
| 2025-11-11 | Bhutan | ≥ 5,000 | 85 | — |
| 2025-05-25 | Malaysia | ≥ 5,000 | 79 | — |
| 2024-08-06 | Fiji | ≥ 5,000 | 35 | — |
| 2024-05-01 | Georgia | ≥ 5,000 | 67 | — |

## Per-country AUC (D5, countries with ≥ 5 primary labels)

| Country | Labels | AUC |
|---|---:|---:|
| United States | 43 | 0.552 |
| Israel | 37 | 0.680 |
| Iran | 36 | 0.626 |
| Palestine | 25 | 0.519 |
| Pakistan | 19 | 0.749 |
| Russia | 18 | 0.705 |
| Syria | 14 | 0.763 |
| India | 13 | 0.689 |
| Lebanon | 12 | 0.559 |
| South Korea | 11 | 0.818 |
| Thailand | 11 | 0.693 |
| Turkey | 9 | 0.837 |
| Yemen | 8 | 0.678 |
| Brazil | 8 | 0.683 |
| China | 8 | 0.633 |
| Saudi Arabia | 8 | 0.797 |
| Bangladesh | 7 | 0.890 |
| Indonesia | 7 | 0.639 |
| Philippines | 7 | 0.623 |
| Afghanistan | 7 | 0.825 |
| Japan | 6 | 0.727 |
| Ethiopia | 6 | 0.815 |
| Ukraine | 6 | 0.578 |
| Spain | 6 | 0.683 |
| Bulgaria | 6 | 0.755 |
| Denmark | 5 | 0.754 |
| Portugal | 5 | 0.750 |
| Ireland | 5 | 0.414 |
| Nigeria | 5 | 0.670 |
| United Kingdom | 5 | 0.842 |
| France | 5 | 0.745 |
| Germany | 5 | 0.848 |
| Colombia | 5 | 0.786 |
| Nepal | 5 | 0.824 |

## The published v2.1 detector (D7)

Weighted Cauchy combination of attention measured in distinct articles (weight 0.70), event mix (0.26) and conflict share (0.04); alarms additionally require at least 20 distinct outlets that day and a healthy instrument. Every design choice was made on 2023 development data after the pre-registered run (D0–D6) showed that equal weighting diluted the attention channel. **Its test-period numbers are therefore post hoc and optimistic**; its unbiased evaluation is the prospective live track record that starts on 2026-10-16. Attention alone (D2a) ranks slightly better (higher AUC) in both development and test; v2.1 keeps the event-mix and conflict channels at small weights so that a change in the *kind* of news, not only its volume, can raise an alarm.

## Development period (2023) and the v2.1 redesign

Development labels: 179 sociopolitical entries, 2023-01-01 → 2023-12-31 (p-values exist from roughly mid-2023 after warm-up).

| Detector | Dev AUC |
|---|---:|
| D0 Random scores | 0.480 |
| D1 Naive news-volume spike | 0.709 |
| D2 Attention channel | 0.757 |
| D2a Attention in articles | 0.773 |
| D3 Event-mix channel | 0.600 |
| D4 Conflict channel | 0.515 |
| D5 WORLDLINE combined (published) | 0.694 |
| D6 Combined + learned semantic channel | 0.702 |

Development rule: weight each channel by max(dev AUC − 0.5, 0); attention unit (articles vs events) and outlet gate (0/5/10/20) chosen by development AUC and precision.

## Reading these numbers

* Labels are an independent but incomplete and Western-weighted record; many alarms concern real events Wikipedia's year articles do not list, so precision here is a conservative lower bound.
* Return periods come from conformal ranks with a generalized-Pareto tail; on real data they are approximately, not exactly, calibrated (see the calibration section).
* Nothing here is a forecast of future events: alarms describe unusual reporting patterns as they happen.

Reproduce: `python -m worldline.cli evaluate` (writes `research/results.json` and this file).
