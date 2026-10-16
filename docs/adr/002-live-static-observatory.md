# ADR 002 — A live, validated observatory on static hosting

Decision date: 2026-10-16. Status: accepted for v0.2. Supersedes the architecture of
[ADR 001](001-coverage-aware-observatory.md); keeps its principles.

## Context

v0.1 demonstrated the method on synthetic streams and four 15-minute GDELT samples. The goals for v0.2 were
real data, continuous live monitoring, alarms validated against the real world, learned representations and
scenario analysis, published on GitHub Pages for a general audience, at no running cost.

## Decisions

### 1. Real data: the full GDELT event stream as daily sufficient statistics

All 1,384 UTC days since 2023-01-01 are acquired from official daily files (15-minute exports for the
current day), verified (storage-layer MD5, publisher checksum list, explicit gap records) and reduced to
compact per-day aggregates: about 1.6 MB per month for days, co-occurrence and evidence together. The raw
archives (~10 GB) are not stored; they can be re-downloaded and re-verified from the recorded URLs and hashes.
*Rejected:* storing raw archives in git (size), a database server (running cost), BigQuery (credentials
and cost for every visitor or run).

### 2. No server: hourly GitHub Actions + a static site

The whole pipeline (fetch, aggregate, model, publish) takes a few minutes and runs hourly on a free GitHub
runner (`.github/workflows/live.yml`). It writes a static site and a documented JSON API to the `gh-pages`
branch as a single commit (no history growth). The live day store is published inside the site
(`/state/`) and restored from there at the start of the next run, so the site is its own database and its
data is public and auditable. If GDELT is unreachable the run publishes the previous data and the site shows
its age; nothing is fabricated.
*Rejected:* FastAPI service from v0.1 (hosting cost, attack surface, nothing dynamic is needed); GitHub's
`actions/deploy-pages` (needs a separate state store and restricts deployments to the default branch).

### 3. Statistics people can read: return periods

Each country is compared only with its own history. Surprise in three channels (attention, event mix,
conflict share) is turned into a calibrated p-value (conformal ranks + generalized Pareto tail) and shown as a
return period, "a 1-in-N-days event for this country". Unlike a z-score or an index, a return period has the
same meaning everywhere and its calibration can be checked; it is checked in `research/results.md`.

### 4. Validation before claims, and a prospective record after

The validation protocol was written and committed before any test-period comparison
([`research/protocol.md`](../../research/protocol.md), commit `ac96c09`), and every result, including failed
hypotheses, is published. The published detector (v2.1) was redesigned afterwards using 2023 data only and
its test numbers are labelled post hoc. From launch (2026-10-16) every alarm is published before any label for
it can exist and is scored automatically: the unbiased test.

### 5. Learned, but small and inspectable

Event-type embeddings (PPMI + SVD of same-article co-occurrence) and country worldlines (PPMI + SVD of
country-pair interactions, Procrustes-aligned over time) train in seconds on a CPU, have checks against
information they were not given, and are deterministic. ADR 001 required that embeddings be *promoted only
if they improve held-out precision*; the pre-registered test (H4) found they do not improve detection, so
they are used for transport geometry, the worldlines map and research, not for alarms.
*Rejected:* transformer text embeddings (would require article text, which WORLDLINE does not collect;
GPU dependence for hourly runs; harder to reproduce). A GPU was offered and is not needed.

### 6. Scenarios as predictive associations, labelled as such

A regularised VAR(7) with generalized impulse responses and connectedness indices answers "historically,
when conflict coverage rose in A, what tended to follow in B?". It is fitted on news-record counts and its
out-of-sample skill over univariate models is about zero, which the Lab reports. It is presented as an
exploratory, Granger-predictive model with uncertainty bands, never as causal effects of events.

### 7. A browser client without a framework

Eight pages in vanilla ES modules, hand-built SVG charts, a pre-projected Equal Earth map, light and dark
themes from validated palettes, mobile-first layout and no build step. The only third-party request is the
Inter web font (the system font is used if it is blocked). The client never computes a statistic; it renders
the JSON the pipeline publishes.

## Consequences

* Running cost is zero; the only dependencies at runtime are NumPy and SciPy.
* Freshness is hourly, not 15-minute; GitHub may delay scheduled runs at busy times, and GitHub disables
  schedules in repositories with no activity for 60 days (the hourly publish keeps the repository active).
* The site is as trustworthy as its pipeline is checkable: tests run on every pull request, the protocol
  reproduces bit-for-bit from the committed data, and every number on the site can be traced to a JSON file
  and from there to code.
