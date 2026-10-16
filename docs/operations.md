# Operations

How WORLDLINE runs, how to run it yourself, and what to do when something goes wrong.

## The moving parts

```
GitHub Actions (hourly, .github/workflows/live.yml)
  1. checkout main + pip install -r requirements.lock          (NumPy, SciPy)
  2. restore _state/ from the published site (gh-pages:/state)   live day store + labels
  3. once a day: refresh Wikipedia labels for the current year   best effort
  4. python -m worldline.cli build --live
       refresh(): newest GDELT slot → 96 latest 15-min exports → today's partial day,
                  missing/provisional recent days, rolling 24-hour window
       analyze(): panel → instrument → country monitor → embeddings → worldlines
       build_scenarios(), nowcast(), publish_all() → _site/ (site + JSON API + RSS + state/)
  5. force-push _site/ to gh-pages as a single commit            GitHub Pages serves it
```

The committed seed (`data/days`, `data/cooc`, `data/evidence`) covers 2023-01-01 → 2026-10-15. Everything
after that lives in the live store, which is published at `/state/` on the site and merged with the seed on
every run (a complete daily-file record always wins over a provisional one).

## First deployment (one time)

1. Push the repository to GitHub with Actions enabled. The **Live** workflow runs on every push to the default branch,
   every hour, and on demand (*Actions → Live → Run workflow*).
2. After its first run creates the `gh-pages` branch: *Settings → Pages → Build and deployment → Source:
   Deploy from a branch → `gh-pages` / `(root)` → Save*.
3. The site appears at `https://<owner>.github.io/<repository>/` within a minute and updates hourly.

The workflow needs only the default `GITHUB_TOKEN` (`contents: write` to push `gh-pages`, `pages: read` to
check the setting). No secrets, API keys or paid services are involved.

## Running locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e .          # or: export PYTHONPATH=backend

python -m worldline.cli build --out _site            # offline, from committed data (~2 min)
python -m worldline.cli build --live --out _site     # also fetch new GDELT data (needs internet)
python -m http.server --directory _site 8000          # open http://localhost:8000

python -m pytest -q                                   # 85 tests, ~20 s
node tests/ui/check-syntax.mjs                        # browser modules parse
node tests/ui/smoke.mjs _site --shots _shots          # headless browser check of every page (needs Playwright)
```

Other commands:

| Command | What it does | Time |
|---|---|---|
| `python -m worldline.cli backfill --start 2023-01-01` | acquire or re-verify any missing/incomplete day into `data/` (`--refresh` re-downloads complete days too) | about an hour for the full history, ~11 GB transferred |
| `python -m worldline.cli evaluate` | re-run the validation protocol; rewrites `research/results.*` and `data/model/published.json` | 10–15 min |
| `python -m worldline.cli labels --years 2026` | fetch Wikipedia year articles and rebuild labels into `_state/labels` | seconds |

## Monitoring the monitor

* Every run writes a summary (data date, newest GDELT export, days acquired, alarms, build time) to the
  Actions run page.
* The site's header shows **Live · updated N minutes ago** (or *Updated …* in grey after three hours). The
  footer shows the build commit; `data/meta.json` records the run URL.
* The *Today* page shows the data-quality status (instrument channel). Each day's full provenance
  (encoding, slots, MD5, verification flags, retrieval time) is in the day store, and the latest day's is in
  `data/latest.json` → `instrument.provenance`.

## When something goes wrong

| Symptom | Likely cause | What happens / what to do |
|---|---|---|
| Header says *Updated 5 hours ago* | Scheduled runs delayed or failing | Check *Actions → Live*. GitHub sometimes delays schedules under load; a failed run leaves the previous site in place. |
| A run logs `live_error` | GDELT unreachable or returned invalid data | The run still publishes, from the data it has. The next run retries; nothing is fabricated or interpolated. |
| A day shows as a gap | GDELT never published it (17 such days since 2023) | Expected. Gaps are excluded from models and never treated as quiet days. |
| *Instrument degraded* on the Today page | Volume or publisher mix outside normal bounds (outage, backlog, ingestion change) | No alarms are issued that day, by design. |
| Schedules stopped entirely | GitHub disables schedules after 60 days without repository activity | Re-enable the workflow in the Actions tab (the hourly publish normally counts as activity). |
| The `gh-pages` branch was deleted | — | The next run rebuilds from the committed seed and backfills up to 40 recent days per run until current. |

## Costs and limits

* Public repository: GitHub Actions minutes are free. Each run takes a few minutes; about 24 runs a day.
* Site size about 19 MB (156 country files, map, API); GitHub Pages allows 1 GB.
* Downloads per run: about 7 MB of 15-minute exports, plus about 8 MB once a day for the new daily file.
* Analysis time grows linearly with the number of days (about two minutes for 2023 → late 2026).

## Release checklist

1. `python -m pytest -q`, `python -m mypy backend/worldline --ignore-missing-imports`, `node tests/ui/check-syntax.mjs`.
2. `python -m worldline.cli build --out _site` and `node tests/ui/smoke.mjs _site`.
3. If anything in `monitor.py`, `experiments.py`, `validate.py` or the data changed:
   `python -m worldline.cli evaluate` and review the diff of `research/results.md`. The protocol must reproduce
   exactly when only presentation code changed.
4. Open a pull request; CI runs the same checks and a browser test, and uploads screenshots.
