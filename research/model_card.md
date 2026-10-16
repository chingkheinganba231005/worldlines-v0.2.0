# Model card

Model: `ilr-ridge-ar1-shrinkage-v1`; feature transform:`fixed-topics-ilr-alpha0.5-v1`. CPU-only; deterministic Python/NumPy/SciPy. Input: daily deduplicated synthetic topic counts with coverage metadata. Output: next-composition point forecast, conditional topic-share intervals, regularized residual magnitude and descriptive historical rank. No learned sentence encoder or large model is active.

Training: expanding then trailing90 eligible states, minimum45; ridge2; covariance uses only prior out-of-sample residuals, minimum20; rank minimum30 earlier scores. Freeze first-fit coefficients as a comparison model. Source shifts and missing/low-count windows suppress scoring. Exact defaults and formulas are in docs/mathematics.md.

Intended use: inspect pipeline behavior and conduct reproducible methodological experiments. Not intended for geopolitical, medical, financial or security decisions. Does not forecast physical alternate timelines or assign causal consequences to events. Synthetic results do not validate external accuracy. Scenario impact and real-world calibration are not available.
