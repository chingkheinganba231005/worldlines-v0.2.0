import { fill, fmt, h, icon, tierBadge } from "../lib/dom.js";
import { FAMILY_LABELS, FAMILY_ORDER, load } from "../lib/data.js";
import { barList, legend, lineChart, sparkline, stackedArea, tableTwin, ttRow } from "../lib/charts.js";
import { alarmCard, familyColors } from "./today.js";

function datesFrom(first, n) {
  const start = new Date(first + "T00:00:00Z").getTime();
  return Array.from({ length: n }, (_, i) => new Date(start + i * 864e5).toISOString().slice(0, 10));
}

const rpAxis = (v) => (v <= 0 ? "1" : v >= 4 ? "10K" : fmt.compact(Math.pow(10, v)));

export async function render(page, route) {
  const iso3 = (route.args[0] || "").toUpperCase();
  if (!/^[A-Z]{3}$/.test(iso3)) throw new Error("Unknown country code.");
  const [c, scenarios] = await Promise.all([load(`country/${iso3}.json`), load("scenarios.json").catch(() => null)]);
  const n = c.series.u.length;
  const dates = datesFrom(c.first_date, n);
  const css = () => getComputedStyle(document.documentElement);
  const today = c.today;
  let range = 365;

  const header = h("section", { style: { marginTop: "32px" } },
    h("p", { class: "eyebrow" }, h("a", { href: "#/countries", style: { textDecoration: "none" } }, "← All countries"), ` · ${c.continent}`),
    h("div", { style: { display: "flex", gap: "16px", alignItems: "center", flexWrap: "wrap" } },
      h("span", { style: { fontSize: "52px", lineHeight: "1" }, "aria-hidden": "true" }, c.flag),
      h("div", h("h1", { style: { fontSize: "clamp(30px,4vw,48px)" } }, c.name),
        h("div", { class: "muted", style: { marginTop: "4px" } }, [c.capital ? `Capital ${c.capital}` : null, c.population ? `${fmt.compact(c.population)} people` : null].filter(Boolean).join(" · ")))),
    h("div", { class: "grid two", style: { marginTop: "22px" } },
      h("div", { class: "card" }, h("div", { class: "card-head" }, h("div", h("p", { class: "eyebrow" }, `Latest day · ${fmt.date(today.date)}`),
        h("h2", fmt.rp(today.return_period) === "typical" ? "A typical day" : `A ${fmt.rp(today.return_period).replace("1 in ", "1-in-").replace(" days", "-day")} event`)), tierBadge(today.tier)),
        h("ul", { class: "drivers" }, (today.drivers || []).slice(0, 3).map((d) => h("li", icon(d.channel === "mix" ? "mix" : d.channel === "conflict" ? "conflict" : "attention"), h("span", d.text + ".")))),
        h("div", { class: "meta-row", style: { marginTop: "12px" } }, h("span", `${fmt.int(today.articles)} articles`), h("span", `${fmt.int(today.outlets)} outlets`), h("span", `${fmt.int(today.events)} coded events`))),
      h("div", { class: "card" }, h("p", { class: "eyebrow" }, "Past year"),
        h("div", { style: { display: "flex", gap: "28px", flexWrap: "wrap", alignItems: "flex-end" } },
          h("div", h("div", { class: "big-number" }, String(c.alarms.filter((a) => a.date > dates[Math.max(0, n - 365)]).length)), h("div", { class: "muted" }, "alarms in 365 days")),
          h("div", h("div", { class: "big-number" }, String(c.alarms.length)), h("div", { class: "muted" }, "alarms since 2023"))),
        h("p", { class: "note" }, "Expected by chance alone for any country: about 3–4 'unusual' days a year. Many more usually means real, recurring news events."))));
  page.append(header);

  const rangeSeg = h("div", { class: "seg", role: "group", "aria-label": "Time range" });
  for (const [value, text] of [[90, "3 months"], [365, "1 year"], [0, "Since 2023"]]) {
    const b = h("button", { type: "button", "aria-pressed": String(value === range) }, text);
    b.addEventListener("click", () => { range = value; rangeSeg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); draw(); });
    rangeSeg.append(b);
  }
  const uBox = h("div", { class: "chart" });
  const covBox = h("div", { class: "chart" });
  const conBox = h("div", { class: "chart" });
  const mixBox = h("div", { class: "chart" });
  const labelIndex = new Map();
  (c.labels || []).forEach((e) => { const i = dates.indexOf(e.date); if (i >= 0) labelIndex.set(i, (labelIndex.get(i) || []).concat(e)); });
  page.append(h("section", h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "History"), h("h2", `How unusual has ${c.name}'s news record been?`)), rangeSeg),
    h("div", { class: "card" }, uBox, legend([{ kind: "ln", color: "var(--accent)", label: "Unusualness (how rare the day was for this country)" },
      { kind: "dot", color: "var(--tier-3)", label: "Alarm day" }, { kind: "ln", color: "var(--muted)", label: "Tick: event listed by Wikipedia" }]),
      h("p", { class: "note" }, "The axis is in days: a value of 100 means a day this unusual comes about once every 100 days for this country.")),
    h("div", { class: "grid two", style: { marginTop: "16px" } },
      h("div", { class: "card" }, h("h3", "News coverage"), h("p", { class: "note", style: { marginTop: "2px" } }, "Articles per day with events located in the country."), covBox),
      h("div", { class: "card" }, h("h3", "Share of violence & coercion"), h("p", { class: "note", style: { marginTop: "2px" } }, "Observed share of events (solid) against the forecast made the day before (dashed)."), conBox)),
    h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", "What kind of news, over time"),
      h("p", { class: "note", style: { marginTop: "2px" } }, "Weekly mix of reported event types, from cooperation (blue) to conflict (red)."), mixBox,
      legend(FAMILY_ORDER.map((f) => ({ color: `var(--fam-${f})`, label: FAMILY_LABELS[f] }))))));

  function draw() {
    const start = range ? Math.max(0, n - range) : 0;
    const d = dates.slice(start);
    const style = css();
    const accent = style.getPropertyValue("--accent").trim();
    const muted = style.getPropertyValue("--muted").trim();
    const u = c.series.u.slice(start).map((v) => (v === null ? null : Math.min(v, 4)));
    const markers = [];
    const ticks = [];
    d.forEach((_, i) => {
      const tier = c.series.tier[start + i];
      if (tier) markers.push({ i, v: u[i] ?? 0, color: style.getPropertyValue(`--tier-${tier}`).trim(), r: 3 + tier });
      if (labelIndex.has(start + i)) ticks.push({ i, color: muted });
    });
    lineChart(uBox, { dates: d, height: 250, yMax: 4, yFormat: rpAxis, ariaLabel: `Unusualness of ${c.name}'s news record over time`,
      series: [{ label: "unusualness", values: u, color: accent, area: true }, { label: "1-in-100-days level", values: d.map(() => 2), color: muted, dashed: true, width: 1 }],
      markers, ticks,
      tooltip: (i) => {
        const index = start + i;
        const labels = labelIndex.get(index) || [];
        return [h("div", { class: "tt-title" }, fmt.date(dates[index], { weekday: "short", day: "numeric", month: "short", year: "numeric" })),
          ttRow(accent, "", fmt.rp(c.series.u[index] === null ? null : Math.pow(10, c.series.u[index]))),
          ttRow(null, "articles", fmt.int(c.series.articles[index])),
          c.series.tier[index] ? h("div", { class: "tt-note" }, `Alarm: ${["", "Unusual", "Rare", "Extreme"][c.series.tier[index]]}`) : null,
          labels.length ? h("div", { class: "tt-note" }, "Wikipedia: " + labels[0].text.slice(0, 120)) : null];
      } });
    lineChart(covBox, { dates: d, height: 190, series: [{ label: "articles", values: c.series.articles.slice(start), color: accent, area: true }], ariaLabel: "Articles per day" });
    lineChart(conBox, { dates: d, height: 190, yFormat: (v) => `${Math.round(v * 100)}%`,
      series: [{ label: "observed", values: c.series.conflict_obs.slice(start), color: style.getPropertyValue("--fam-coercion").trim(), width: 1.6 },
        { label: "forecast", values: c.series.conflict_exp.slice(start), color: muted, dashed: true, width: 1.4 }], ariaLabel: "Share of violence and coercion" });
    const fam = c.series.families_permille.slice(start);
    const step = d.length > 200 ? 7 : 1;
    const weekDates = [];
    const layers = FAMILY_ORDER.map((id) => ({ id, label: FAMILY_LABELS[id], color: style.getPropertyValue(`--fam-${id}`).trim(), values: [] }));
    const familyIds = ["statements", "diplomacy", "cooperation", "disputes", "protest", "coercion", "violence"];
    for (let i = 0; i < fam.length; i += step) {
      const chunk = fam.slice(i, i + step).filter((row) => row.reduce((a, b) => a + b, 0) > 0);
      if (!chunk.length) continue;
      weekDates.push(d[i]);
      layers.forEach((layer) => {
        const k = familyIds.indexOf(layer.id);
        layer.values.push(chunk.reduce((a, row) => a + row[k], 0) / chunk.length / 1000);
      });
    }
    stackedArea(mixBox, { dates: weekDates, layers, height: 220 });
  }
  draw();
  window.addEventListener("relayout", draw, { once: true });
  window.addEventListener("themechange", draw, { once: true });

  // Alarms
  const alarmsSection = h("section");
  const shown = c.alarms.slice(0, 6);
  alarmsSection.append(h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Alarm record"), h("h2", `${c.alarms.length} alarm${c.alarms.length === 1 ? "" : "s"} since 2023`),
    h("p", { class: "note", style: { maxWidth: "64ch" } }, `Of these, ${c.alarms.filter((a) => a.wikipedia && a.wikipedia.length).length} fall within days of an event Wikipedia lists for ${c.name}. Wikipedia's yearly lists are short, so many real events are missing from them.`))));
  if (shown.length) {
    const grid = h("div", { class: "alarm-list" }, shown.map((a) => alarmCard(a, { showDate: true })));
    alarmsSection.append(grid);
    if (c.alarms.length > shown.length) {
      const more = h("button", { class: "btn", type: "button", style: { marginTop: "14px" } }, `Show all ${c.alarms.length} alarms`);
      more.addEventListener("click", () => { fill(grid, c.alarms.map((a) => alarmCard(a, { showDate: true }))); more.remove(); });
      alarmsSection.append(more);
    }
  } else {
    alarmsSection.append(h("div", { class: "empty" }, `No alarms for ${c.name} since monitoring began.`));
  }
  page.append(alarmsSection);

  // Relations
  const partnerBox = h("div", { class: "chart" });
  const relations = h("section", h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Relations"), h("h2", "Who it interacts with"))),
    h("div", { class: "grid two" },
      h("div", { class: "card" }, h("h3", "Main partners, last 30 days"), h("p", { class: "note", style: { marginTop: "2px" } }, "Events between actors of the two countries; bar length is the number of events, colour shows the cooperative and conflictual share."), partnerBox,
        legend([{ color: "var(--fam-diplomacy)", label: "Cooperation" }, { color: "var(--fam-coercion)", label: "Conflict" }])),
      h("div", { class: "card" }, h("h3", "Closest in relational space (worldline)"),
        h("p", { class: "note", style: { marginTop: "2px" } }, "Countries whose pattern of relations — who they deal with, cooperatively or not — is most similar this month. Learned from the data alone."),
        c.worldline ? h("div", { class: "rows", style: { marginTop: "8px" } }, c.worldline.neighbors.map((nb) =>
          h("a", { class: "row-link", href: `#/country/${nb.iso3}` }, h("span", { class: "muted tabular" }, nb.similarity.toFixed(2)), h("div", { class: "row-title" }, nb.name), h("span", { class: "row-right" }, "→")))) : h("p", { class: "muted" }, "Not enough relational data."),
        c.worldline ? h("div", { style: { marginTop: "12px", display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" } },
          h("span", { class: "muted", style: { fontSize: "13px" } }, "Monthly movement through relational space:"), sparkline(c.worldline.drift, { width: 160, height: 30 }),
          h("a", { href: `#/worldlines?focus=${c.iso3}` }, "See its worldline →")) : null)));
  page.append(relations);
  const partners = c.partners || [];
  barList(partnerBox, { items: partners.map((p) => ({ label: p.name, value: p.events, color: p.conflict > p.cooperation ? "var(--fam-coercion)" : "var(--fam-diplomacy)",
    sub: `events (${fmt.pct(p.conflict / Math.max(p.events, 1))} conflictual)`, onClick: () => { location.hash = `#/country/${p.iso3}`; } })), format: (v) => fmt.compact(v) });

  if (scenarios && scenarios.countries.some((x) => x.iso3 === iso3)) {
    page.append(h("section", h("div", { class: "callout" }, h("strong", "What if? "), `${c.name} is one of the 30 countries in the What-if Lab. `,
      h("a", { href: `#/lab/${iso3}` }, `See how a jump in conflict reporting about ${c.name} has historically rippled to other countries →`))));
  }
  page.append(h("section", tableTwin(`${c.name} daily series`, [{ label: "Date", value: (r) => r }, { label: "Return period", value: (r) => fmt.rp(c.series.u[dates.indexOf(r)] === null ? null : Math.pow(10, c.series.u[dates.indexOf(r)])), num: true },
    { label: "Articles", value: (r) => fmt.int(c.series.articles[dates.indexOf(r)]), num: true }, { label: "Outlets", value: (r) => fmt.int(c.series.outlets[dates.indexOf(r)]), num: true }],
    dates.slice(-90).reverse()), h("p", { class: "note" }, h("a", { href: `data/country/${iso3}.json` }, `Download ${c.name}'s full data (JSON)`), " · open data, CC BY 4.0 for derived statistics; GDELT attribution applies.")));
}
