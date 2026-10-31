import { extLink, fmt, h } from "../lib/dom.js";
import { load } from "../lib/data.js";

function block(id, eyebrow, title, ...body) {
  return h("section", { id }, h("p", { class: "eyebrow" }, eyebrow), h("h2", title), h("div", { class: "prose", style: { marginTop: "12px" } }, ...body));
}

function expert(summary, ...body) {
  return h("details", { class: "card flat", style: { marginTop: "12px" } }, h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, summary),
    h("div", { class: "prose", style: { marginTop: "10px", fontSize: "14.5px" } }, ...body));
}

const API = [
  ["meta.json", "Versions, data freshness, tiers, model weights, sources and file sizes."],
  ["latest.json", "Today: the pulse, plain-language brief, alarms with drivers and evidence, watch list, event mix, data quality, live 24-hour nowcast."],
  ["timeline.json", "One row per day since 2023: countries unusual, expected by chance, alarms by tier, global event-mix surprise, displacement (JSD and learned optimal transport), data quality, Wikipedia entries."],
  ["grid.json", "Unusualness (×10) and alarm tier for every monitored country on every day — the map's time machine."],
  ["countries.json", "Index of monitored countries with today's status, 90-day sparkline and alarm counts."],
  ["country/{ISO3}.json", "A country's full daily series (unusualness, articles, outlets, event mix), every alarm with drivers and evidence, partners, and worldline neighbours."],
  ["worldlines.json", "Monthly 2-D positions of every country in learned relational space, recent movement and quality checks."],
  ["event_space.json", "Learned map of CAMEO event types with quality checks."],
  ["scenarios.json", "What-if lab: impulse responses with 80% bands, connectedness index and skill test."],
  ["validation.json", "The full validation results behind the track record."],
  ["labels.json", "Wikipedia year-article entries used as validation labels (CC BY-SA 4.0)."],
  ["map.json", "Pre-projected Equal Earth country outlines (Natural Earth, public domain)."],
];

export async function render(page, route) {
  const meta = await load("meta.json").catch(() => null);
  const w = meta ? meta.weights : {};
  page.append(h("section", { style: { marginTop: "32px" } }, h("p", { class: "eyebrow" }, "How it works"),
    h("h1", { style: { fontSize: "clamp(28px,3.6vw,46px)" } }, "A seismograph for the world's news"),
    h("p", { class: "lead" }, "WORLDLINE does one thing carefully: every day it asks, for each country, “how unusual was today's news record compared with this country's own past?” — and then checks itself in public."),
    h("nav", { class: "chips", style: { marginTop: "18px" }, "aria-label": "On this page" }, [["#data", "The data"], ["#unusual", "Measuring unusual"], ["#alarms", "Alarms"], ["#learned", "Learned embeddings"],
      ["#scenarios", "Scenarios"], ["#limits", "Limits"], ["#api", "Open data & API"], ["#reproduce", "Reproduce"]].map(([href, text]) =>
      h("a", { class: "chip", href: "#/method", onclick: (e) => { e.preventDefault(); document.querySelector(href)?.scrollIntoView({ behavior: "smooth" }); } }, text)))));

  page.append(block("data", "1 · The data", "The world's news, as machine-coded events",
    h("p", "The ", extLink("https://www.gdeltproject.org/", "GDELT Project"), " reads news from around the world in over 100 languages and, every 15 minutes, publishes structured records: which actors did what to whom, where, with a link to the article. Each record uses the CAMEO codebook — around 300 event types, from “make a public statement” to “use conventional military force”."),
    h("p", "WORLDLINE downloads ", h("strong", "only this metadata"), ", never the articles. Since 2023 that is about 120,000 events from 25,000 articles a day. Every download is checked against the storage system's own checksum; days the provider never published (for example a 17-day outage in June 2025) are recorded as gaps, never as quiet days."),
    h("p", "Two quirks we measured and designed around: events dated weeks or years in the past (anniversaries, retrospectives) are set aside, and GDELT revises attention counts during the day — so only counts that never change are used to model."),
    expert("For experts: data details",
      h("p", "A day is defined by DATEADDED (provider availability, UTC). Fresh events have SQLDATE within one day of DATEADDED (98% of records). We verified that a daily export is exactly the union of its 96 fifteen-minute exports (116,603 identical IDs on 2026-10-13), so history and live monitoring are one dataset. NumArticles/NumMentions/NumSources, AvgTone and IsRootEvent differ between encodings (end-of-day revisions) and are excluded from models."),
      h("p", "An instrument channel compares each day's volume with the same weekday over eight weeks and its publisher mix (Jensen–Shannon divergence over the top 150 domains) with the previous 28 days. It caught the 2023-03-22 outage, the backlog that followed, and a 2024 publisher break; those days are not scored and do not train later forecasts."))));

  page.append(block("unusual", "2 · Measuring unusual", "Each country against its own past",
    h("p", "For 156 countries with enough coverage, WORLDLINE forecasts each day from earlier days only, then measures how far reality landed from the forecast. Three questions are asked:"),
    h("ul", h("li", h("strong", "Attention: "), "is the country getting an unusual share of the world's news articles?"),
      h("li", h("strong", "Kind: "), "has the mix of events — statements, diplomacy, aid, criticism, protests, coercion, violence — shifted unusually?"),
      h("li", h("strong", "Conflict: "), "has the share of coercion and violence jumped?")),
    h("p", "Each surprise is compared with the same country's surprises over the previous year and turned into a ", h("strong", "return period"), ": “a 1-in-400-days event for this country.” The three answers are combined into one score."),
    expert("For experts: the statistics",
      h("p", "Forecasts: weekday-effect ridge regressions on lag-1, 7- and 28-day means of the target, refit weekly on a trailing 365-day window (strictly prequential). Attention: log share of the world's distinct articles. Mix: isometric log-ratio coordinates of seven event families with covariance Σ = Σ_process + B diag(1/(n p̂)) Bᵀ, so small samples do not masquerade as surprises. Conflict: logit share with binomial sampling variance added."),
      h("p", "Calibration: conformal ranks against the trailing 365 scores, with a generalized Pareto tail (peaks over the 90th percentile, probability-weighted moments) so return periods can exceed the window; displayed values are capped at 5,000 days."),
      h("p", `Combination: weighted Cauchy combination test (Liu & Xie 2020), valid under dependence between channels. Weights (v2.1, set on 2023 data): attention ${fmt.pct(w.p_articles || 0)}, kind ${fmt.pct(w.p_mix || 0)}, conflict ${fmt.pct(w.p_conflict || 0)}.`))));

  page.append(block("alarms", "3 · Alarms", "When a country lights up",
    h("p", "An alarm needs three things: a day rarer than once in 100 days for that country, at least 20 different news outlets reporting from it, and healthy data that day. Alarms come in three levels:"),
    h("ul", h("li", h("strong", "Unusual"), " — rarer than 1 in 100 days"), h("li", h("strong", "Rare"), " — rarer than 1 in 365 days"), h("li", h("strong", "Extreme"), " — rarer than 1 in 1,000 days")),
    h("p", "Every alarm shows why it fired, the most common event types, links to real coverage, and any matching entry in Wikipedia's lists. An alarm is a prompt to look, not a verdict: news coverage is not the world, and machine coding makes mistakes.")));

  page.append(block("learned", "4 · Learned embeddings", "Teaching the system what events mean",
    h("p", "Two maps are learned from the data alone, with no human labels:"),
    h("ul", h("li", h("strong", "A map of event types. "), "Kinds of events that the same articles keep reporting together end up close. Without being told, it rediscovers the cooperation–conflict scale (rank correlation 0.60 with the expert Goldstein scale) and powers a “how far has the world moved” measure where fighting is closer to assault than to praise."),
      h("li", h("strong", "Worldlines. "), "Each month each country gets a position from who it deals with and how. 91% of a country's nearest neighbours share its continent (chance: 23%) — and the paths show relations shifting over time.")),
    h("p", "Honest result: adding the learned event map as an alarm signal did not improve accuracy. The embeddings earn their place as instruments for exploration, not as a magic accuracy boost."),
    expert("For experts: embeddings",
      h("p", "Event types: positive PMI of same-article co-occurrence of CAMEO base codes (2023, 32 million pairs, context smoothing 0.75), 16-dimensional truncated SVD (Levy, Goldberg & Dagan 2015). Countries: PPMI + SVD of partner × direction × QuadClass counts over 3-month windows, rotated onto a whole-period anchor with orthogonal Procrustes. Checks: k-NN QuadClass accuracy, cross-validated Goldstein readout, continent purity under permutation nulls."))));

  page.append(block("scenarios", "5 · Scenarios", "What if conflict news surged?",
    h("p", "The What-if Lab fits a vector autoregression to daily conflict reporting in the 30 most conflict-active countries and asks how others have historically moved after an unexpected jump in one. Uncertainty comes from 200 bootstrap refits."),
    h("p", h("strong", "What it is not: "), "a causal model or a forecast. We tested it honestly — other countries' recent conflict news does not improve next-day forecasts beyond each country's own history. The ripples describe co-coverage: the stories that are told together.")));

  page.append(block("limits", "6 · Limits", "What WORLDLINE cannot do",
    h("ul",
      h("li", "It sees the world through news. Places with little coverage are under-watched; the news has its own fashions and blind spots."),
      h("li", "GDELT's events are machine-extracted and sometimes wrong — wrong place, wrong actor, duplicated stories."),
      h("li", "Unusual is not important, and important is not always unusual: a slow-burning catastrophe can look ‘typical’."),
      h("li", "Return periods are estimates from a year of history; the rarest levels are extrapolations."),
      h("li", "Validation labels come from English Wikipedia's yearly lists, which favour some regions and kinds of event."),
      h("li", "Nothing here predicts the future or identifies causes."))));

  page.append(h("section", { id: "api" }, h("p", { class: "eyebrow" }, "7 · Open data & API"), h("h2", "Use the data"),
    h("p", { class: "prose", style: { marginTop: "12px" } }, "Everything on this site is a static JSON file you can fetch directly — no key, no limits beyond GitHub Pages'. Files are regenerated by the live pipeline; ", h("code", "meta.json"), " says when."),
    h("div", { class: "card table-scroll", style: { marginTop: "12px", maxHeight: "none" } }, h("table", { class: "data-table" }, h("thead", h("tr", h("th", "Path"), h("th", "Contents"), h("th", { class: "num" }, "Size"))),
      h("tbody", API.map(([path, text]) => h("tr", h("td", h("a", { href: `data/${path.replace("{ISO3}", "USA")}` }, h("code", `data/${path}`))), h("td", { class: "ink2" }, text),
        h("td", { class: "num muted" }, meta && meta.files[path.includes("{") ? "country/*.json" : path] ? fmt.compact(meta.files[path.includes("{") ? "country/*.json" : path] / 1024) + " KB" : "")))))),
    h("pre", { class: "card", style: { overflowX: "auto", fontSize: "13px", marginTop: "12px" } }, `// Today's alarms in three lines
const res = await fetch("https://chingkheinganba231005.github.io/worldlines-v0.2.0/data/latest.json");
const today = await res.json();
today.alarms.forEach(a => console.log(a.name, a.return_period_text, a.drivers[0].text));`),
    h("p", { class: "note" }, "Alarm feed: ", h("a", { href: "feed.xml" }, "feed.xml"), " (RSS). Derived statistics: CC BY 4.0 — please credit WORLDLINE and The GDELT Project. Wikipedia text: CC BY-SA 4.0.")));

  page.append(block("reproduce", "8 · Reproduce", "Run it yourself",
    h("pre", { class: "card", style: { overflowX: "auto", fontSize: "13px", whiteSpace: "pre" } }, `git clone https://github.com/chingkheinganba231005/worldlines-v0.2.0
cd worldlines-v0.2.0 && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock && pip install --no-deps -e .
python -m worldline.cli backfill --start 2023-01-01   # optional: data/ already holds the history
python -m worldline.cli evaluate                      # validation protocol -> research/results.md
python -m worldline.cli build --out _site             # analysis + this website
python -m http.server -d _site 8000`),
    h("p", "Cite as: WORLDLINE contributors (2026). ", h("em", "WORLDLINE v0.2: a validated, live observatory of unusual change in the world's news record."), " https://github.com/chingkheinganba231005/worldlines-v0.2.0")));
  if (route.args[0] === "api") setTimeout(() => document.getElementById("api")?.scrollIntoView(), 50);
}
