# Data sources, rights and what the data can and cannot say

## Sources

| Source | Used for | Terms | In this repository |
|---|---|---|---|
| [GDELT 2.0 Event database](https://www.gdeltproject.org/) (daily files and 15-minute exports) | the signal: daily aggregates of machine-coded event records | Free to use and redistribute with attribution to The GDELT Project ([about](https://www.gdeltproject.org/about.html)) | Daily aggregates only (`data/days`, `data/cooc`, `data/evidence`); no raw archives |
| [Wikipedia year articles](https://en.wikipedia.org/wiki/2025) (*2023*–*2026*, "Events" sections) | independent validation labels and the prospective track record | CC BY-SA 4.0; attribution "Wikipedia contributors" | Frozen wikitext (`data/labels/raw`, SHA-256 in the manifest) and the parsed labels |
| [Natural Earth](https://www.naturalearthdata.com/) 1:50m via [world-atlas](https://github.com/topojson/world-atlas) 2.0.2 | map shapes, pre-projected to Equal Earth | Public domain | `data/reference/world-atlas-*.json` |
| [GeoNames](https://www.geonames.org/) `countryInfo.txt` | country names, ISO/FIPS codes, continents, capitals | CC BY 4.0 | `data/reference/geonames_countryInfo.txt` |
| [CAMEO](https://parusanalytics.com/eventdata/data.dir/cameo.html) codebook and Goldstein scale (as distributed by GDELT) | event-type labels, family grouping, embedding checks | Academic codebook, distributed with GDELT | `data/reference/CAMEO.*` |

Every page of the site and every JSON file carries these attributions (`meta.json` → `sources`).

## What is and is not collected

* **Only event metadata.** WORLDLINE never downloads, stores or displays the text of news articles. Source
  article URLs are kept for at most three top articles per country and day (`data/evidence`), so a reader
  can check what the record is based on; the links point to the publishers, whose rights are unaffected.
* **Only official endpoints.** The client accepts `https://data.gdeltproject.org/events/…` and
  `…/gdeltv2/…` archive and manifest URLs and nothing else; redirects are refused; downloads are size-capped
  and verified (see [methods §1.2](methods.md#12-integrity)).
* **No personal data processing.** Records are aggregated to country-day counts before storage. Actor
  *names* are never stored; only actor *country codes* (for country-pair statistics).
* **Polite access.** Each hourly run downloads the 96 most recent 15-minute exports (about 7 MB) and, once a
  day, the new daily file (about 8 MB); finished days are never downloaded again. Wikipedia is queried once
  a day through its API with a descriptive user agent.

## What the data can say

GDELT records are machine-extracted claims found in news coverage: "actor A did X to actor B at place P",
coded with the CAMEO taxonomy. WORLDLINE treats them as a **measurement of the news record**, not of the
world. A WORLDLINE alarm therefore means *"the news record about this country changed in a way that is
rare for this country"*, not *"something happened"*.

Known properties of the source, each of which WORLDLINE either corrects for, measures, or discloses:

| Property | Consequence | How WORLDLINE handles it |
|---|---|---|
| Coverage is uneven across countries and languages (GDELT translates 65 languages, but English-language and Western outlets dominate volume) | Raw counts are not comparable between countries | Every country is compared only with itself; return periods are per-country |
| One article can produce many event records; syndication multiplies articles | Volume spikes can be one story | Attention measured in distinct articles; alarms need ≥ 20 distinct publishers |
| Extraction errors (wrong actor, wrong location, wrong event code) | Noise and occasional artefacts | Large-sample statistics only; per-day sampling variance modelled explicitly; the *Track record* shows misses and false alarms |
| Re-extraction of old events (anniversaries, retrospectives) | Old events reappear as new | Only events dated the same or the previous day count ("fresh") |
| Provider outages, backlogs, ingestion changes | Apparent changes in the world that are changes in the instrument | Instrument channel: degraded days are flagged, not scored, and excluded from calibration |
| Attention fields are revised after first publication | Daily file and 15-minute values disagree | Revised fields (NumArticles, NumMentions, NumSources, AvgTone, IsRootEvent) are not used by any model |

## Labels (Wikipedia)

Wikipedia's year articles list internationally notable events chosen by editors. They are independent of
GDELT, freely licensed and dated, which makes them a useful reference, but they are **not ground truth**:
they are selective, English-language, Western-weighted, edited with hindsight and with a lag. Countries are
attached by a gazetteer (names, demonyms, capitals and key places) and categories by declared keyword rules
(`backend/worldline/labels.py`); both can err. Precision measured against these labels is therefore a
conservative lower bound: many alarms concern real events the year articles do not list.

## Re-use of WORLDLINE's outputs

The code is MIT-licensed. WORLDLINE's own derived statistics (p-values, return periods, alarms,
embeddings, scenario results) are released under CC BY 4.0: credit WORLDLINE and The GDELT Project. The
published JSON files and the day store also contain GDELT-derived aggregates (attribute The GDELT Project)
and Wikipedia-derived label text (CC BY-SA 4.0, attribute Wikipedia contributors). Please keep these attributions when re-using the data, and keep the caveat that alarms are
statistical signals in news metadata, not verified events.
