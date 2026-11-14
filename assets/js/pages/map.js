import { fill, fmt, h, icon, tierBadge, TIERS } from "../lib/dom.js";
import { load } from "../lib/data.js";
import { tableTwin } from "../lib/charts.js";
import { scaleLegend, worldMap } from "../lib/map.js";

export async function render(page, route) {
  const [grid, mapData, index, timeline] = await Promise.all([load("grid.json"), load("map.json"), load("countries.json"), load("timeline.json")]);
  const byIso = Object.fromEntries(index.countries.map((c) => [c.iso3, c]));
  const dates = grid.dates;
  const requested = route.query.get("date");
  let t = requested && dates.includes(requested) ? dates.indexOf(requested) : dates.length - 1;
  let timer = null;

  const title = h("h1", { style: { fontSize: "clamp(28px,3.6vw,42px)" } }, "Where is the news unusual?");
  const dateLabel = h("div", { class: "big-number", style: { fontSize: "clamp(24px,3vw,34px)" }, "aria-live": "polite" });
  const subLabel = h("div", { class: "muted", style: { fontSize: "14px", marginTop: "4px" } });
  const slider = h("input", { type: "range", min: 0, max: dates.length - 1, value: t, "aria-label": "Choose a day" });
  const play = h("button", { class: "btn primary", type: "button" }, icon("play"), "Play");
  const prev = h("button", { class: "icon-btn", type: "button", "aria-label": "Previous day" }, icon("prev"));
  const next = h("button", { class: "icon-btn", type: "button", "aria-label": "Next day" }, icon("next"));
  const latestBtn = h("button", { class: "btn", type: "button" }, "Latest day");
  const mapBox = h("div", { class: "map" });
  const listBox = h("div");
  const tableBox = h("div");

  page.append(
    h("section", { style: { marginTop: "32px" } },
      h("p", { class: "eyebrow" }, "Time machine · every day since 2023"), title,
      h("p", { class: "lead" }, "Each country is compared with its own history. Darker violet means a rarer day for that country. Drag the slider or press play to watch the world's news move."),
      h("div", { class: "card", style: { marginTop: "22px" } },
        h("div", { class: "card-head", style: { flexWrap: "wrap" } }, h("div", dateLabel, subLabel),
          h("div", { class: "controls" }, prev, play, next, latestBtn)),
        slider,
        h("div", { style: { marginTop: "16px" } }, mapBox),
        h("div", { style: { marginTop: "12px" } }, scaleLegend()))),
    h("section", h("div", { class: "split" }, h("div", { class: "card" }, listBox), h("div", { class: "card" },
      h("h3", "Reading the map"),
      h("div", { class: "prose", style: { marginTop: "8px", fontSize: "14.5px" } },
        h("p", "Colour shows how rare a day's news record is ", h("strong", "for that country"), " — a 1-in-100-days day in a quiet country can be a routine day in a busy one."),
        h("p", "Dots mark alarms: rare days seen by at least 20 news outlets, on days when the data itself looked healthy."),
        h("p", "Grey countries were either typical that day or have too little coverage to monitor reliably."),
        h("p", h("a", { href: "#/method" }, "How unusualness is computed →")))))),
    h("section", tableBox));

  function draw() {
    const values = {};
    const tiers = {};
    grid.countries.forEach((iso, m) => {
      const v = grid.u10[t][m];
      if (v >= 0) values[iso] = v / 10;
      if (grid.tier[t][m]) tiers[iso] = grid.tier[t][m];
    });
    worldMap(mapBox, mapData, { values, tiers, onClick: (iso) => { location.hash = `#/country/${iso}`; },
      tooltip: (iso) => [h("div", { class: "tt-title" }, `${byIso[iso]?.flag || ""} ${byIso[iso]?.name || iso}`),
        h("div", values[iso] !== undefined ? fmt.rp(Math.pow(10, values[iso])) : "no score"),
        tiers[iso] ? h("div", { class: "tt-note" }, `Alarm: ${TIERS[tiers[iso]]}`) : null, h("div", { class: "tt-note" }, "Click for the full story")] });
    const date = dates[t];
    dateLabel.textContent = fmt.date(date, { weekday: "short", day: "numeric", month: "long", year: "numeric" });
    const degraded = timeline.degraded[t];
    subLabel.textContent = degraded ? "Data quality degraded this day — alarms paused." :
      `${fmt.int(timeline.turbulence[t])} countries unusual (chance alone ~${Math.round(timeline.expected[t] || 0)}) · ${Object.keys(tiers).length} alarms`;
    slider.value = String(t);
    slider.setAttribute("aria-valuetext", date);
    history.replaceState(null, "", `#/map?date=${date}`);
    const ranked = Object.entries(values).sort((a, b) => b[1] - a[1]);
    fill(listBox, h("h3", `Most unusual on ${fmt.date(date)}`),
      h("div", { class: "rows", style: { marginTop: "10px" } }, ranked.slice(0, 10).map(([iso, u]) =>
        h("a", { class: "row-link", href: `#/country/${iso}` }, h("span", { class: "flag", "aria-hidden": "true" }, byIso[iso]?.flag || ""),
          h("div", { style: { minWidth: 0 } }, h("div", { class: "row-title" }, byIso[iso]?.name || iso), h("div", { class: "row-sub" }, byIso[iso]?.continent || "")),
          h("div", { class: "row-right" }, fmt.rp(Math.pow(10, u)), tiers[iso] ? h("div", tierBadge(tiers[iso])) : null)))));
    fill(tableBox, tableTwin(`Unusualness on ${date}`, [{ label: "Country", value: (r) => byIso[r[0]]?.name || r[0] },
      { label: "Return period", value: (r) => fmt.rp(Math.pow(10, r[1])), num: true }, { label: "Alarm", value: (r) => (tiers[r[0]] ? TIERS[tiers[r[0]]] : "") }], ranked));
  }
  const go = (value) => { t = Math.max(0, Math.min(dates.length - 1, value)); draw(); };
  const stop = () => { clearInterval(timer); timer = null; fill(play, icon("play"), "Play"); };
  slider.addEventListener("input", () => { stop(); go(+slider.value); });
  prev.addEventListener("click", () => { stop(); go(t - 1); });
  next.addEventListener("click", () => { stop(); go(t + 1); });
  latestBtn.addEventListener("click", () => { stop(); go(dates.length - 1); });
  play.addEventListener("click", () => {
    if (timer) { stop(); return; }
    if (t >= dates.length - 1) t = Math.max(0, dates.length - 120);
    fill(play, icon("pause"), "Pause");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    timer = setInterval(() => { if (t >= dates.length - 1 || !document.body.contains(page)) { stop(); return; } go(t + 1); }, reduced ? 900 : 160);
  });
  page.addEventListener("keydown", (e) => {
    if (e.target === slider) return;
    if (e.key === "ArrowLeft") { stop(); go(t - 1); }
    if (e.key === "ArrowRight") { stop(); go(t + 1); }
  });
  window.addEventListener("hashchange", stop, { once: true });
  draw();
  window.addEventListener("themechange", draw, { once: true });
}
