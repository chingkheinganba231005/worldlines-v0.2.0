import { fill, fmt, h } from "../lib/dom.js";
import { load } from "../lib/data.js";
import { barList, legend, lineChart, tableTwin, ttRow } from "../lib/charts.js";
import { worldMap } from "../lib/map.js";

const SIZES = [[0.25, "+25%"], [0.5, "+50%"], [1, "doubles (+100%)"], [2, "triples (+200%)"]];
const CATEGORICAL = { light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"], dark: ["#3987e5", "#d95926", "#199e70", "#c98500"] };

export async function render(page, route) {
  const [sc, mapData] = await Promise.all([load("scenarios.json"), load("map.json")]);
  const names = sc.countries.map((c) => c.name);
  const isos = sc.countries.map((c) => c.iso3);
  let j = Math.max(0, isos.indexOf((route.args[0] || "ISR").toUpperCase()));
  let size = 1;
  const countrySelect = h("select", { "aria-label": "Country where conflict reporting jumps" }, sc.countries.map((c, i) => h("option", { value: i }, c.name)));
  countrySelect.value = String(j);
  const sizeSelect = h("select", { "aria-label": "Size of the jump" }, SIZES.map(([v, text]) => h("option", { value: v }, text)));
  sizeSelect.value = String(size);
  const mapBox = h("div", { class: "map" });
  const barsBox = h("div", { class: "chart" });
  const lineBox = h("div", { class: "chart" });
  const lineLegend = h("div");
  const headline = h("h2", { "aria-live": "polite" });
  const skill = sc.skill || {};

  page.append(h("section", { style: { marginTop: "32px" } },
    h("p", { class: "eyebrow" }, "Scenario lab · vector autoregression"), h("h1", { style: { fontSize: "clamp(28px,3.6vw,42px)" } }, "What if conflict news suddenly surged?"),
    h("p", { class: "lead" }, `Pick one of ${sc.countries.length} countries and imagine its conflict reporting jumps unexpectedly. The lab shows how conflict reporting in other countries has historically moved alongside such jumps, with uncertainty.`),
    h("div", { class: "callout", style: { marginTop: "18px" } }, h("strong", "Read this first. "),
      `These are patterns in news coverage learned from ${fmt.date(sc.fit_period[0])}–${fmt.date(sc.fit_period[1])}, not causal effects and not forecasts. In an honest out-of-sample test, knowing other countries' recent conflict reporting improved next-day forecasts by ${skill.mean_improvement_pct === null || skill.mean_improvement_pct === undefined ? "—" : skill.mean_improvement_pct.toFixed(1) + "%"} on average — essentially nothing. The ripples mostly show which countries' conflicts are covered together (same stories, same day), and how long that lasts.`),
    h("div", { class: "card", style: { marginTop: "18px" } },
      h("div", { class: "controls", style: { fontSize: "17px" } }, h("span", "If conflict reporting about"), countrySelect, h("span", "suddenly"), sizeSelect, h("span", "…")),
      h("div", { style: { marginTop: "16px" } }, headline),
      h("div", { class: "split", style: { marginTop: "14px" } },
        h("div", mapBox, h("p", { class: "note" }, "Colour: average change in each country's conflict reporting over the following week. Only the 30 most conflict-active countries are modelled.")),
        h("div", h("h3", "Largest ripples, first week"), h("p", { class: "note", style: { marginTop: "2px" } }, "Median change with 80% interval (wild bootstrap, 200 refits)."), barsBox)))),
    h("section", h("div", { class: "card" }, h("h3", "How the ripple unfolds, day by day"), h("p", { class: "note", style: { marginTop: "2px" } }, "Expected change in conflict reporting after the jump (day 0), for the country itself and its three largest responders."), lineBox, lineLegend)));

  const pct = (logResponse) => 100 * (Math.exp(logResponse) - 1);
  function compute() {
    const delta = Math.log(1 + size);
    const H = sc.horizon;
    const week = (arr, i) => { let total = 0; for (let k = 0; k < 7; k++) total += arr[j][k][i]; return (total / 7) * delta; };
    return sc.countries.map((c, i) => ({ i, iso3: c.iso3, name: c.name, week: pct(week(sc.median, i)), lo: pct(week(sc.lo, i)), hi: pct(week(sc.hi, i)),
      path: Array.from({ length: H + 1 }, (_, k) => pct(sc.median[j][k][i] * delta)) }));
  }
  function draw() {
    const style = getComputedStyle(document.documentElement);
    const dark = style.colorScheme === "dark" || document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    const results = compute();
    const self = results[j];
    const others = results.filter((r) => r.i !== j).sort((a, b) => b.week - a.week);
    fill(headline, `…then over the next week, conflict reporting about ${others[0].name} typically rises ${others[0].week.toFixed(0)}%, and ${others[1].name} ${others[1].week.toFixed(0)}%.`);
    // Diverging map: increases red, decreases blue, ~0 neutral.
    const values = {};
    const colors = {};
    for (const r of results) {
      const v = r.week;
      values[r.iso3] = v;
      const steps = v >= 0 ? ["--land", "--fam-disputes", "--fam-protest", "--fam-coercion", "--fam-violence"] : ["--land", "--fam-diplomacy", "--fam-cooperation"];
      const k = v >= 0 ? (v < 2 ? 0 : v < 8 ? 1 : v < 20 ? 2 : v < 50 ? 3 : 4) : (v > -2 ? 0 : v > -8 ? 1 : 2);
      colors[r.iso3] = style.getPropertyValue(steps[k]).trim();
    }
    const svg = worldMap(mapBox, mapData, { values: Object.fromEntries(Object.keys(values).map((k) => [k, 0])), selected: self.iso3,
      onClick: (iso) => { const index = isos.indexOf(iso); if (index >= 0) { j = index; countrySelect.value = String(j); history.replaceState(null, "", `#/lab/${iso}`); draw(); } },
      tooltip: (iso) => { const r = results[isos.indexOf(iso)]; return [h("div", { class: "tt-title" }, r.name), h("div", `${r.week >= 0 ? "+" : ""}${r.week.toFixed(1)}% over the first week`), h("div", { class: "tt-note" }, `80% interval ${r.lo.toFixed(1)}% to ${r.hi.toFixed(1)}%`)]; } });
    svg.querySelectorAll("path.country.on").forEach((path) => { path.setAttribute("fill", colors[path.dataset.iso3]); });
    svg.querySelectorAll("circle.tiny").forEach((dot) => { dot.setAttribute("fill", colors[dot.dataset.iso3]); });
    barList(barsBox, { items: others.slice(0, 10).map((r) => ({ label: r.name, value: r.week, lo: r.lo, hi: r.hi, color: style.getPropertyValue(r.week >= 0 ? "--fam-coercion" : "--fam-diplomacy").trim(),
      sub: "change, first week", onClick: () => { location.hash = `#/country/${r.iso3}`; } })), format: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%` });
    const palette = CATEGORICAL[dark ? "dark" : "light"];
    const series = [self, ...others.slice(0, 3)].map((r, k) => ({ label: r.name, values: r.path, color: palette[k] }));
    const days = Array.from({ length: sc.horizon + 1 }, (_, k) => String(k));
    lineChart(lineBox, { dates: days, xLabels: days.map((k) => `day ${k}`), height: 240, series, yFormat: (v) => `${Math.round(v)}%`, ariaLabel: "Response over days after the jump",
      tooltip: (i) => [h("div", { class: "tt-title" }, `Day ${i} after the jump`), ...series.map((sr) => ttRow(sr.color, sr.label, `${sr.values[i] >= 0 ? "+" : ""}${sr.values[i].toFixed(1)}%`))] });
    fill(lineLegend, legend(series.map((sr) => ({ kind: "ln", color: sr.color, label: sr.label }))),
      tableTwin("Ripple sizes", [{ label: "Country", value: (r) => r.name }, { label: "First-week change", value: (r) => `${r.week.toFixed(1)}%`, num: true },
        { label: "80% interval", value: (r) => `${r.lo.toFixed(1)}% to ${r.hi.toFixed(1)}%`, num: true }], [self, ...others]));
  }
  countrySelect.addEventListener("change", () => { j = +countrySelect.value; history.replaceState(null, "", `#/lab/${isos[j]}`); draw(); });
  sizeSelect.addEventListener("change", () => { size = +sizeSelect.value; draw(); });
  draw();
  window.addEventListener("relayout", draw, { once: true });
  window.addEventListener("themechange", draw, { once: true });

  // Connectedness
  const connBox = h("div", { class: "chart" });
  const netBox = h("div", { class: "chart" });
  page.append(h("section", h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Diebold–Yilmaz connectedness"), h("h2", "How intertwined is the world's conflict news?"),
      h("p", { class: "note", style: { maxWidth: "70ch" } }, "The share of each country's unexpected conflict-news swings that is shared with other countries (10-day forecast-error variance decomposition, rolling one-year windows)."))),
    h("div", { class: "split" }, h("div", { class: "card" }, h("div", { class: "big-number" }, `${sc.connectedness.total.toFixed(0)}%`), h("div", { class: "muted" }, "of conflict-news variation is shared across countries (whole period)"), connBox),
      h("div", { class: "card" }, h("h3", "Net transmitters and receivers"), h("p", { class: "note", style: { marginTop: "2px" } }, "Positive: a country's surprises spill into others' coverage more than the reverse."), netBox))));
  const drawConn = () => {
    const style = getComputedStyle(document.documentElement);
    lineChart(connBox, { dates: sc.rolling.map((r) => r.month + "-15"), height: 200, yFormat: (v) => `${Math.round(v)}%`,
      series: [{ label: "connectedness", values: sc.rolling.map((r) => r.total), color: style.getPropertyValue("--accent").trim(), area: true }], ariaLabel: "Connectedness over time" });
    const net = isos.map((iso, i) => ({ label: names[i], value: sc.connectedness.net[i] })).sort((a, b) => b.value - a.value);
    barList(netBox, { items: [...net.slice(0, 5), ...net.slice(-5)].map((d) => ({ ...d, color: style.getPropertyValue(d.value >= 0 ? "--fam-coercion" : "--fam-diplomacy").trim(), sub: "net (to − from)" })), format: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}` });
  };
  drawConn();
  window.addEventListener("themechange", drawConn, { once: true });
  page.append(h("section", h("div", { class: "card" }, h("h3", "Model details"), h("dl", { class: "kv", style: { marginTop: "10px" } },
    h("dt", "Variables"), h("dd", "log(1 + conflict events located in the country), 30 countries, daily"),
    h("dt", "Model"), h("dd", `VAR(7) with weekday effects and log world event volume; Minnesota-style ridge (own lags λ=${sc.lambda}, cross lags ×${sc.kappa}) chosen on held-out data`),
    h("dt", "Responses"), h("dd", "Generalized impulse responses (Pesaran & Shin, 1998), order-invariant"),
    h("dt", "Uncertainty"), h("dd", "80% intervals from 200 wild-bootstrap refits"),
    h("dt", "Skill check"), h("dd", `One-step forecasts after ${skill.split}: ${skill.mean_improvement_pct?.toFixed(2)}% average RMSE change vs. each country's own history (${skill.test_days} days)`),
    h("dt", "Data"), h("dd", `${fmt.int(sc.observations)} days, ${fmt.date(sc.fit_period[0])} to ${fmt.date(sc.fit_period[1])}`)))));
}
