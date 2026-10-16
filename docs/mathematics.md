# What the implementation actually calculates

All evaluated time windows are closed UTC calendar days for the synthetic demo. Its first 30 days form a frozen reference; those days are not presented as evaluated observations. The separate real sample is one 15-minute archive per day and is never silently interpreted as full daily coverage.

## Observation and transport

Every synthetic heuristic cluster receives one vote in one of six fixed categories. Duplicate mentions affect coverage diagnostics but not topic weights. The parser for real GDELT records only deduplicates provider IDs; cross-ID semantic real-event resolution is not implemented.

For counts c with K categories, p_k=(c_k+0.5)/(sum(c)+0.5K). An empty window has no distribution, not a uniform imputation. The frozen reference is the equal-window mean of the first 30 eligible distributions. The rolling reference averages the prior 30 eligible windows and may span more than 30 calendar days. Neither includes the selected observation. No 2019 dataset is bundled.

JSD(p,q)=0.5 sum p log(p/m)+0.5 sum q log(q/m), where m=(p+q)/2; units are nats, range [0,ln2]. Per-topic terms sum exactly to JSD. They explain a numerical distributional difference, not causal event effects.

Exact OT minimizes sum_ij pi_ij C_ij subject to row sums p and column sums q, solved with SciPy HiGHS linear programming. No entropic regularization or Sinkhorn debiasing is used. For the six-topic demonstration, identical categories have cost0, declared within-group transfers (geopolitics/economy/society; science/health; climate as its own group) cost0.5, other pairs cost1. **This group geometry is an illustrative ontology assumption, not an empirically learned semantic similarity.** It should not be reused for a research claim without sensitivity analysis. JSD is retained because it does not depend on this transport geometry. The four-slot real experiment uses CAMEO QuadClass groups instead, versioned in its output.

## Composition-aware forecasts

Use a (K−1)-by-K orthonormal Helmert contrast matrix B. z=B log(p), inverse p=softmax(B^T z). The adaptive forecaster fits ridge AR(1) with an unpenalized intercept, ridge coefficient2, and at most90 prior eligible states. Only consecutive eligible positions produce training pairs. It needs45 eligible states. A frozen coefficient matrix from the first fit and a persistence forecast are retained as baselines.

At target time t, fit beta using states through t−1, save the forecast, calculate r_t=z_t−forecast, calculate the score, then append r_t and z_t for future fits. Invalid coverage suppresses scoring and parameter updates. After a gap, the first recovery state can seed the next forecast but its gap residual does not calibrate surprise.

After20 prior out-of-sample residuals, construct Sigma=0.8Cov(r_prior)+0.2I max(trace(Cov)/d,0.025)+0.025I. Score=sqrt(r^T Sigma^−1 r). This is a regularized residual magnitude, not a probability. Covariance centering does not correct forecast bias; a biased forecast can inflate the score and must be evaluated.

After30 earlier valid scores, display 100(1+number of prior scores <= current)/(n+1), n<=90. This is a **descriptive trailing rank**. Scores come from an evolving model and covariance, with serial dependence. Real-world calibration is explicitly false. This is not a calibrated tail p-value, posterior probability, or guarantee of alert frequency.

Conditional 80% topic-share forecast intervals use400 reproducible Gaussian ILR draws transformed back to proportions. They omit parameter, selection and taxonomy uncertainty; nominal coverage is unvalidated. There is no confidence interval pretending to measure uncertainty in a physical worldline.

## Coverage and experimental candidates

Minimum40 unique synthetic clusters, at least3 publisher IDs, source-mixture JSD<=0.12 against the frozen source mixture, and a usable preceding day are required. Source JSD is based on mentions and is deliberately sensitive to syndicated-source volume. This diagnostic can suppress genuine changes too; it is not an unbiased adjustment.

Dashboard candidate rule: at least2 of the last3 windows have descriptive rank>=97.5, with7-window cooldown. Thresholds are declared design choices, not calibrated false-alarm guarantees. No automated candidate is upgraded to `corroborated`. `Resolved` means the statistical signal cooled down, never that a geopolitical event ended.

The separate benchmark freezes raw-score thresholds on the dedicated calibration period and evaluates the next120 windows. Its alert rule differs from the adaptive dashboard rank rule and is explicitly labeled as such. Do not substitute benchmark results for validation of the published rule.
