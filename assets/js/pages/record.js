import { extLink, fmt, h, icon } from "../lib/dom.js";
import { load } from "../lib/data.js";
import { barList, tableTwin } from "../lib/charts.js";

const NAMES = {
  D0: "Random guessing", D1: "Naive volume spike", D2: "Coverage · events", D2a: "Coverage · articles",
  D3: "Kind of news", D4: "Violence share", D5: "Pre-registered mix", D6: "+ learned semantics",
  D7: "WORLDLINE v2.1",
};

function outcome(ok, text, detail) {
  return h("li", { style: { display: "grid", gridTemplateColumns: "26px 1fr", gap: "8px", padding: "10px 0", borderBottom: "1px solid var(--border)" } },
    h("span", { style: { color: ok === true ? "var(--good-ink)" : ok === false ? "var(--critical)" : "var(--muted)" } }, icon(ok === true ? "check" : ok === false ? "alert" : "info", { width: 20, height: 20 })),
    h("div", h("div", { style: { fontWeight: 600 } }, text), h("div", { class: "ink2", style: { fontSize: "14.5px" } }, detail)));
}

export async function render(page) {
  const v = await load("validation.json");
  const d = v.detectors;
  const pub = d.D7 || d.D5;
  const rare = pub.tiers.rare;
  const notable = pub.tiers.notable;
  const d5 = d.D5;
  const oneIn = (p) => (p > 0 ? Math.round(1 / p) : "—");
  page.append(h("section", { style: { marginTop: "32px" } },
    h("p", { class: "eyebrow" }, "Track record · tested against independent records"),
    h("h1", { style: { fontSize: "clamp(28px,3.6vw,46px)" } }, "Do the alarms mean anything?"),
    h("p", { class: "lead" }, `We checked every alarm from ${fmt.date(v.test_period[0])} to ${fmt.date(v.test_period[1])} against ${fmt.int(v.labels.primary)} political and conflict events that Wikipedia's editors independently listed as internationally notable. The test was written down before we ran it.`),
    h("div", { class: "grid three", style: { marginTop: "24px" } },
      h("div", { class: "card" }, h("div", { class: "big-number" }, `1 in ${oneIn(rare.precision)}`),
        h("p", { class: "ink2", style: { margin: "8px 0 0" } }, `Rare alarms with a Wikipedia-listed event for that country within days — `, h("strong", `${fmt.ratio(rare.lift)} the chance rate`), ` (${fmt.pct(rare.base_rate, 1)}).`)),
      h("div", { class: "card" }, h("div", { class: "big-number" }, fmt.pct(notable.recall)),
        h("p", { class: "ink2", style: { margin: "8px 0 0" } }, `of listed events were flagged by an alarm within days (${fmt.int(notable.labels_detected)} of ${fmt.int(notable.labels)}), with ~${notable.alarms_per_country_year.toFixed(1)} alarms per country per year.`)),
      h("div", { class: "card" }, h("div", { class: "big-number" }, pub.auc_primary.toFixed(2)),
        h("p", { class: "ink2", style: { margin: "8px 0 0" } }, `Ranking quality (AUC). On days a country appears in Wikipedia's list, its score beats an ordinary day ${fmt.pct(pub.auc_primary)} of the time. Chance: ${v.random_auc.mean.toFixed(2)}.`))),
    h("div", { class: "callout", style: { marginTop: "16px" } }, h("strong", "How to read this honestly. "),
      "Wikipedia's yearly lists hold only a few hundred events, so many alarms are about real events that simply are not on the list — these numbers are a floor, not a ceiling. ",
      d.D7 ? "The published detector (v2.1) was redesigned after the pre-registered test, using 2023 data only; its test numbers are therefore optimistic. The pre-registered detector scored " + `AUC ${d5.auc_primary.toFixed(2)} and ${fmt.ratio(d5.tiers.rare.lift)} lift. From launch day on, every alarm is scored prospectively.` : "")));

  // AUC chart
  const aucBox = h("div", { class: "chart" });
  const keys = ["D7", "D2a", "D2", "D1", "D5", "D6", "D3", "D4"].filter((k) => d[k]);
  page.append(h("section", h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Head to head"), h("h2", "Which signals find real events?"),
      h("p", { class: "note", style: { maxWidth: "70ch" } }, "Ranking quality (AUC) of each detector on the test period, with 95% bootstrap intervals. Bars start at 0.5 — what random guessing scores."))),
    h("div", { class: "card" }, aucBox, tableTwin("Detector comparison", [{ label: "Detector", value: (k) => NAMES[k] || k }, { label: "AUC", value: (k) => d[k].auc_primary.toFixed(3), num: true },
      { label: "95% CI", value: (k) => `${d[k].auc_bootstrap.auc_ci95[0].toFixed(3)}–${d[k].auc_bootstrap.auc_ci95[1].toFixed(3)}`, num: true },
      { label: "Precision (rare)", value: (k) => fmt.pct(d[k].tiers.rare.precision, 1), num: true }, { label: "Lift (rare)", value: (k) => fmt.ratio(d[k].tiers.rare.lift), num: true }], keys))));
  const drawAuc = () => {
    const style = getComputedStyle(document.documentElement);
    barList(aucBox, { zero: 0.5, max: 0.85, items: keys.map((k) => ({ label: NAMES[k] || k, value: d[k].auc_primary, lo: d[k].auc_bootstrap.auc_ci95[0], hi: d[k].auc_bootstrap.auc_ci95[1],
      color: k === "D7" ? style.getPropertyValue("--accent").trim() : k === "D5" ? style.getPropertyValue("--ink-2").trim() : style.getPropertyValue("--baseline").trim(), sub: "AUC" })),
      format: (x) => x.toFixed(3) });
  };
  drawAuc();
  window.addEventListener("themechange", drawAuc, { once: true });

  // Hypotheses
  const h2diff = d5.auc_bootstrap.difference_ci95;
  const h4diff = d.D6 ? d.D6.vs_D5.difference_ci95 : null;
  page.append(h("section", h("div", { class: "grid two" },
    h("div", { class: "card" }, h("h3", "What we predicted in advance — and what happened"),
      h("ul", { style: { listStyle: "none", padding: 0, margin: "10px 0 0" } },
        outcome(d5.auc_null.p_value < 0.01, "H1: alarms beat chance", `Supported. Pre-registered detector AUC ${d5.auc_primary.toFixed(3)} vs. ${d5.auc_null.null_mean.toFixed(3)} when event dates are shuffled (p ≈ ${d5.auc_null.p_value.toFixed(3)}).`),
        outcome(h2diff[0] > 0, "H2: beats a naive news-volume spike", `Not supported. Difference ${d5.auc_bootstrap.difference_mean.toFixed(3)} (95% CI ${h2diff[0].toFixed(3)} to ${h2diff[1].toFixed(3)}). Volume alone is a strong baseline.`),
        outcome(d.D3.auc_primary > 0.55 ? true : null, "H3: the kind of news carries signal", `Partly. Event-mix channel AUC ${d.D3.auc_primary.toFixed(3)}; the violence-share channel scored ${d.D4.auc_primary.toFixed(3)} — no better than chance.`),
        h4diff ? outcome(h4diff[0] > 0, "H4: learned embeddings improve alarms", `Not supported. Difference ${d.D6.vs_D5.difference_mean.toFixed(3)} (95% CI ${h4diff[0].toFixed(3)} to ${h4diff[1].toFixed(3)}).`) : null)),
    h("div", { class: "card" }, h("h3", "What we changed because of it"), h("div", { class: "prose", style: { fontSize: "14.5px", marginTop: "8px" } },
      h("p", "Equal weighting diluted the strongest signal — how much of the world's coverage a country suddenly gets. Using 2023 data only, v2.1 weights each signal by how well it worked in 2023, measures coverage in distinct articles rather than machine-extracted events (one article can yield dozens), and requires at least 20 outlets before raising an alarm."),
      h("p", "Coverage alone still ranks slightly better than v2.1. We keep the 'kind of news' signal at a small weight so a change in what is being reported — not just how much — can raise an alarm."),
      h("p", h("a", { href: "https://github.com/chingkheinganba231005/worldlines-v0.2.0/blob/main/research/protocol.md", rel: "noopener" }, "Read the pre-registered protocol"), " · ",
        h("a", { href: "https://github.com/chingkheinganba231005/worldlines-v0.2.0/blob/main/research/results.md", rel: "noopener" }, "Full results")))))));

  // Calibration
  const cal = v.calibration_quiet_days;
  page.append(h("section", h("div", { class: "grid two" },
    h("div", { class: "card" }, h("h3", "Are the '1 in N days' numbers honest?"),
      h("p", { class: "ink2", style: { fontSize: "14.5px" } }, `On ${fmt.int(cal.n)} country-days with nothing on Wikipedia's lists nearby, here is how often each level was reached, against what it should be if the numbers are calibrated:`),
      h("table", { class: "data-table" }, h("thead", h("tr", h("th", "Level"), h("th", { class: "num" }, "Should be"), h("th", { class: "num" }, "Observed"))),
        h("tbody", [["1 in 20 days", 0.05, cal["share_p_le_0.05"]], ["1 in 100 days", 0.01, cal["share_p_le_0.01"]], ["1 in 1,000 days", 0.001, cal["share_p_le_0.001"]]].map(([label, want, got]) =>
          h("tr", h("td", label), h("td", { class: "num" }, fmt.pct(want, 1)), h("td", { class: "num" }, fmt.pct(got, 2)))))),
      h("p", { class: "note" }, "Close at everyday levels; the rarest level happens ~3× more often than nominal — partly real events missing from the lists, partly the limits of extrapolating from a year of history.")),
    h("div", { class: "card" }, h("h3", "Base rates, so the numbers mean something"), h("dl", { class: "kv", style: { marginTop: "10px" } },
      h("dt", "Test period"), h("dd", `${fmt.date(v.test_period[0])} – ${fmt.date(v.test_period[1])} (${fmt.int(v.test_days)} days)`),
      h("dt", "Countries"), h("dd", `${v.monitored_countries}, ${fmt.int(v.scored_country_days)} scored country-days`),
      h("dt", "Labels"), h("dd", `${fmt.int(v.labels.primary)} political or conflict entries naming a monitored country (Wikipedia year articles 2024–2026)`),
      h("dt", "Hit window"), h("dd", "alarm from one day before to two days after the listed date"),
      h("dt", "Chance hit rate"), h("dd", `${fmt.pct(rare.base_rate, 1)} of country-days`),
      h("dt", "Significance"), h("dd", "circular-shift permutation tests and bootstrap intervals"))))));

  // Examples
  page.append(h("section", h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Examples"), h("h2", "The most extreme alarms of the test period"),
      h("p", { class: "note", style: { maxWidth: "70ch" } }, "One per country per month. Some match a Wikipedia entry; others are real events too small for Wikipedia's global yearly list — and some may be quirks of machine-coded news. Judge for yourself."))),
    h("div", { class: "card table-scroll", style: { maxHeight: "none" } }, h("table", { class: "data-table" },
      h("thead", h("tr", h("th", "Date"), h("th", "Country"), h("th", { class: "num" }, "Rarity"), h("th", { class: "num" }, "Outlets"), h("th", "Wikipedia lists"))),
      h("tbody", v.examples.map((e) => h("tr", h("td", { class: "tabular", style: { whiteSpace: "nowrap" } }, e.date), h("td", h("a", { href: `#/country/${e.country}` }, e.name)),
        h("td", { class: "num", style: { whiteSpace: "nowrap" } }, fmt.rp(e.return_period_days)), h("td", { class: "num" }, fmt.int(e.outlets)),
        h("td", { class: "ink2", style: { fontSize: "13.5px" } }, e.wikipedia_match.length ? e.wikipedia_match[0] : "—"))))))));
  page.append(h("section", h("p", { class: "note" }, "Labels: ", extLink("https://en.wikipedia.org/wiki/2025", "Wikipedia year articles"), " (CC BY-SA 4.0), frozen by checksum. Data and code to reproduce every number: ",
    extLink("https://github.com/chingkheinganba231005/worldlines-v0.2.0", "GitHub"), ".")));
}
