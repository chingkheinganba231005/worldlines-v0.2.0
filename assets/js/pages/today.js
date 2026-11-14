import { extLink, fill, fmt, h, icon, tierBadge } from "../lib/dom.js";
import { FAMILY_LABELS, FAMILY_ORDER, load } from "../lib/data.js";
import { legend, lineChart, stackedBars, tableTwin, ttRow } from "../lib/charts.js";
import { scaleLegend, worldMap } from "../lib/map.js";

const HEADLINES = {
  Calm: "A calm day in the world's news.",
  Typical: "A typical day in the world's news.",
  Busy: "A busy day in the world's news.",
  Turbulent: "A turbulent day in the world's news.",
  Exceptional: "An exceptional day in the world's news.",
};
const DRIVER_ICON = { attention: "attention", mix: "mix", conflict: "conflict" };

export function familyColors() {
  const css = getComputedStyle(document.documentElement);
  return Object.fromEntries(FAMILY_ORDER.map((id) => [id, css.getPropertyValue(`--fam-${id}`).trim()]));
}

export function alarmCard(a, { showDate = false } = {}) {
  const card = h("article", { class: "card alarm" },
    h("div", { class: "alarm-top" },
      h("span", { class: "flag", "aria-hidden": "true" }, a.flag || "🏳️"),
      h("div", { style: { minWidth: 0 } },
        h("a", { class: "alarm-name", href: `#/country/${a.iso3}` }, a.name),
        h("div", { class: "alarm-rp" }, showDate ? `${fmt.date(a.date)} · ` : "", `A ${a.return_period_text.replace("1-in-", "1-in-")} event`)),
      h("div", { style: { marginLeft: "auto" } }, tierBadge(a.tier))),
    a.drivers && a.drivers.length ? h("ul", { class: "drivers" }, a.drivers.slice(0, 3).map((d) =>
      h("li", icon(DRIVER_ICON[d.channel] || "info"), h("span", d.text + ".")))) : null,
    h("div", { class: "meta-row" }, h("span", `${fmt.int(a.articles)} articles`), h("span", `${fmt.int(a.outlets)} outlets`),
      h("span", `${fmt.int(a.events)} coded events`)),
    a.top_codes && a.top_codes.length ? h("div", { class: "codes", "aria-label": "Most frequent event types" },
      a.top_codes.slice(0, 3).map((c) => h("span", { class: "code-chip" }, h("i", { style: { background: `var(--fam-${c.family})` } }), c.label))) : null,
    a.wikipedia && a.wikipedia.length ? h("div", { class: "wiki-match" }, h("b", "Wikipedia lists: "), a.wikipedia[0].text) : null,
    a.evidence && a.evidence.length ? h("ul", { class: "evidence", "aria-label": "Example coverage" },
      a.evidence.map((e) => h("li", extLink(e.url, h("span", { class: "domain" }, e.domain), h("span", e.url.replace(/^https?:\/\/(www\.)?/, "")))))) : null);
  return card;
}

function watchRow(w) {
  return h("a", { class: "row-link", href: `#/country/${w.iso3}` },
    h("span", { class: "flag", "aria-hidden": "true" }, w.flag),
    h("div", { style: { minWidth: 0 } }, h("div", { class: "row-title" }, w.name),
      h("div", { class: "row-sub" }, w.drivers && w.drivers[0] ? w.drivers[0].text : "")),
    h("div", { class: "row-right" }, fmt.rp(w.return_period), w.tier ? h("div", tierBadge(w.tier)) : null));
}

function tiles(latest) {
  const p = latest.pulse;
  const tiers = { 1: 0, 2: 0, 3: 0 };
  latest.alarms.forEach((a) => { tiers[a.tier] += 1; });
  const mixPeriod = p.global_mix_return_period;
  return h("div", { class: "tiles" },
    h("div", { class: "tile" }, h("div", { class: "tile-label" }, "Unusual countries"),
      h("div", { class: "tile-value" }, fmt.int(p.turbulence)), h("div", { class: "tile-sub" }, `chance alone: ~${Math.round(p.expected)}`)),
    h("div", { class: "tile" }, h("div", { class: "tile-label" }, "Alarms"),
      h("div", { class: "tile-value" }, fmt.int(latest.alarms.length)),
      h("div", { class: "tile-sub" }, latest.alarms.length ? `${tiers[3]} extreme · ${tiers[2]} rare · ${tiers[1]} unusual` : "none today")),
    h("div", { class: "tile" }, h("div", { class: "tile-label" }, "Global event mix"),
      h("div", { class: "tile-value" }, mixPeriod && mixPeriod >= 10 ? fmt.rp(mixPeriod).replace(" days", "") : "Typical"),
      h("div", { class: "tile-sub" }, mixPeriod && mixPeriod >= 10 ? "days — how rare today's mix is" : "compared with its forecast")),
    h("div", { class: "tile" }, h("div", { class: "tile-label" }, "News analysed"),
      h("div", { class: "tile-value" }, fmt.compact(latest.instrument.articles)),
      h("div", { class: "tile-sub" }, `articles · ${fmt.compact(latest.instrument.outlets)} outlets`)));
}

function instrumentStatus(inst) {
  const ok = !inst.degraded;
  return h("span", { class: "status", title: "Data quality check: coverage volume and publisher mix compared with recent weeks" },
    icon(ok ? "check" : "alert", { style: { color: ok ? "var(--good-ink)" : "var(--critical)" } }),
    ok ? "Data quality normal" : "Data quality degraded — alarms paused");
}

async function seismograph(section, latest) {
  const [timeline, labelsDoc] = await Promise.all([load("timeline.json"), load("labels.json")]);
  const labelById = new Map(labelsDoc.events.map((e) => [e.id, e]));
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim();
  const muted = css.getPropertyValue("--muted").trim();
  const tier3 = css.getPropertyValue("--tier-3").trim();
  let range = 365;
  const chartBox = h("div", { class: "chart" });
  const dayPanel = h("div", { class: "day-panel", "aria-live": "polite" });
  const seg = h("div", { class: "seg", role: "group", "aria-label": "Time range" });
  const ranges = [[90, "3 months"], [365, "1 year"], [0, "Since 2023"]];
  for (const [value, text] of ranges) {
    const b = h("button", { type: "button", "aria-pressed": String(value === range) }, text);
    b.addEventListener("click", () => { range = value; seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); draw(); });
    seg.append(b);
  }
  const showDay = (index) => {
    const date = timeline.dates[index];
    const top = timeline.top[index] || [];
    const labels = (timeline.labels[index] || []).map((id) => labelById.get(id)).filter(Boolean);
    fill(dayPanel,
      h("div", { class: "card-head", style: { marginBottom: "8px" } },
        h("div", h("h3", fmt.longDate(date)), h("div", { class: "muted", style: { fontSize: "13.5px" } },
          timeline.degraded[index] ? "Data quality degraded on this day — alarms were not issued." :
            `${fmt.int(timeline.turbulence[index])} countries unusual (chance alone: ~${Math.round(timeline.expected[index] || 0)}) · ${fmt.compact(timeline.events[index])} coded events`)),
        h("a", { class: "btn", href: `#/map?date=${date}` }, icon("globe"), "See this day on the map")),
      top.length ? h("div", { class: "chips", style: { marginBottom: "10px" } }, h("span", { class: "muted", style: { fontSize: "13.5px", alignSelf: "center" } }, "Alarms:"),
        top.map((iso) => h("a", { class: "chip", href: `#/country/${iso}` }, iso))) : h("p", { class: "muted", style: { margin: "0 0 8px" } }, "No alarms on this day."),
      labels.length ? h("div", h("div", { class: "eyebrow", style: { marginTop: "6px" } }, "Wikipedia lists for this date"),
        h("ul", { style: { margin: "4px 0 0", paddingLeft: "18px", color: "var(--ink-2)", fontSize: "14px" } }, labels.slice(0, 5).map((e) => h("li", e.text)))) : null);
  };
  function draw() {
    const n = timeline.dates.length;
    const start = range ? Math.max(0, n - range) : 0;
    const dates = timeline.dates.slice(start);
    const turbulence = timeline.turbulence.slice(start);
    const expected = timeline.expected.slice(start);
    const smooth = turbulence.map((_, i) => {
      const win = timeline.turbulence.slice(Math.max(0, start + i - 6), start + i + 1).filter((v) => v !== null);
      return win.length >= 4 ? win.reduce((a, b) => a + b, 0) / win.length : null;
    });
    const markers = [];
    const ticks = [];
    const sorted = turbulence.filter((v) => v !== null).sort((a, b) => a - b);
    const busy = sorted.length ? sorted[Math.floor(sorted.length * 0.97)] : Infinity;
    dates.forEach((d, i) => {
      if (turbulence[i] !== null && turbulence[i] >= busy) markers.push({ i, v: turbulence[i], color: tier3, r: 4 });
      if ((timeline.labels[start + i] || []).length) ticks.push({ i, color: muted });
    });
    lineChart(chartBox, {
      dates, height: 260, ariaLabel: "Number of countries behaving unusually each day",
      series: [{ label: "countries unusual (daily)", values: turbulence, color: accent, width: 1, opacity: 0.4 },
        { label: "7-day average", values: smooth, color: accent, area: true },
        { label: "expected by chance", values: expected, color: muted, dashed: true, width: 1.5 }],
      markers, ticks, selected: dates.length - 1, yFormat: (v) => String(Math.round(v)),
      onSelect: (i) => showDay(start + i),
      tooltip: (i) => {
        const index = start + i;
        const labels = (timeline.labels[index] || []).map((id) => labelById.get(id)).filter(Boolean);
        return [h("div", { class: "tt-title" }, fmt.date(timeline.dates[index], { weekday: "short", day: "numeric", month: "short", year: "numeric" })),
          ttRow(accent, "countries unusual", fmt.int(timeline.turbulence[index])), ttRow(accent, "7-day average", smooth[i] === null ? "—" : smooth[i].toFixed(1)),
          ttRow(muted, "expected by chance", fmt.int(timeline.expected[index])),
          (timeline.top[index] || []).length ? h("div", { class: "tt-note" }, "Alarms: " + timeline.top[index].join(", ")) : null,
          labels.length ? h("div", { class: "tt-note" }, "Wikipedia: " + labels[0].text.slice(0, 110) + (labels[0].text.length > 110 ? "…" : "")) : null,
          h("div", { class: "tt-note" }, "Click to open this day")];
      },
    });
  }
  section.append(
    h("div", { class: "section-head" },
      h("div", h("p", { class: "eyebrow" }, "The world's seismograph"), h("h2", "How unusual has each day been?"),
        h("p", { class: "note", style: { maxWidth: "62ch" } }, "Each day we count how many countries' news records look unusual (a 1-in-20-days surprise for that country). On a quiet day chance alone gives about 8 of 156. Spikes mark days when the world moved.")),
      seg),
    h("div", { class: "card" }, chartBox,
      legend([{ kind: "ln", color: accent, label: "Countries behaving unusually (7-day average; daily in light)" }, { kind: "ln", color: muted, label: "Expected by chance (dashed)" },
        { kind: "dot", color: tier3, label: "Busiest days in view (top 3%)" }, { kind: "ln", color: muted, label: "Tick: an event listed by Wikipedia that day" }]),
      dayPanel,
      tableTwin("Countries unusual per day", [{ label: "Date", value: (r) => r.d }, { label: "Countries unusual", value: (r) => fmt.int(r.t), num: true },
        { label: "Expected", value: (r) => fmt.int(r.e), num: true }, { label: "Alarms", value: (r) => r.a, num: true }],
        timeline.dates.map((d, i) => ({ d, t: timeline.turbulence[i], e: timeline.expected[i], a: timeline.alarms.unusual[i] + timeline.alarms.rare[i] + timeline.alarms.extreme[i] })).slice(-120).reverse())));
  draw();
  showDay(timeline.dates.length - 1);
  window.addEventListener("relayout", draw, { once: true });
  window.addEventListener("themechange", () => draw(), { once: true });
}

function mixSection(section, latest) {
  const colors = familyColors();
  const box = h("div", { class: "chart" });
  const today = Object.fromEntries(latest.mix.families.map((f, i) => [f, latest.mix.today[i]]));
  const typical = Object.fromEntries(latest.mix.families.map((f, i) => [f, latest.mix.typical[i]]));
  const changes = FAMILY_ORDER.map((f) => ({ f, today: today[f], typical: typical[f], diff: today[f] - typical[f] }))
    .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff)).slice(0, 3);
  section.append(h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "What kind of news?"),
      h("h2", "Today's mix of reported events, worldwide"),
      h("p", { class: "note", style: { maxWidth: "64ch" } }, "Every event GDELT extracts from the news falls on a scale from cooperation (blue) to conflict (red). Here is today's mix next to the 2023 average."))),
    h("div", { class: "card" }, box,
      legend(FAMILY_ORDER.map((f) => ({ color: colors[f], label: FAMILY_LABELS[f] }))),
      h("p", { class: "note" }, "Biggest differences from 2023: ", changes.map((c, i) => [i ? " · " : "", `${FAMILY_LABELS[c.f]} ${c.diff >= 0 ? "+" : "−"}${(Math.abs(c.diff) * 100).toFixed(1)} points`])),
      tableTwin("Event mix", [{ label: "Type", value: (r) => FAMILY_LABELS[r] }, { label: "Today", value: (r) => fmt.pct(today[r], 1), num: true },
        { label: "2023 average", value: (r) => fmt.pct(typical[r], 1), num: true }], FAMILY_ORDER)));
  const draw = () => stackedBars(box, { rows: [{ label: "Today", shares: today }, { label: "2023 average", shares: typical }], order: FAMILY_ORDER, colors: familyColors(), labels: FAMILY_LABELS });
  draw();
  window.addEventListener("relayout", draw, { once: true });
  window.addEventListener("themechange", draw, { once: true });
}

function nowcastSection(section, nowcast) {
  if (!nowcast || !nowcast.countries || !nowcast.countries.length) return;
  section.append(h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Live · last 24 hours · provisional"),
      h("h2", "Rising right now"),
      h("p", { class: "note", style: { maxWidth: "64ch" } }, `From the ${nowcast.slots} most recent 15-minute GDELT updates (through ${nowcast.through} UTC). Provisional: these numbers firm up when the full day is in.`))),
    h("div", { class: "card" }, h("div", { class: "rows" }, nowcast.countries.slice(0, 8).map((c) =>
      h("a", { class: "row-link", href: `#/country/${c.iso3}` }, h("span", { class: "flag", "aria-hidden": "true" }, c.flag),
        h("div", { style: { minWidth: 0 } }, h("div", { class: "row-title" }, c.name), h("div", { class: "row-sub" }, `${fmt.int(c.articles)} articles in 24 h · ${fmt.ratio(c.ratio)} its usual share of coverage`)),
        h("div", { class: "row-right" }, fmt.rp(c.return_period)))))));
}

export async function render(page) {
  const [latest, mapData, index] = await Promise.all([load("latest.json"), load("map.json"), load("countries.json")]);
  const values = Object.fromEntries(index.countries.map((c) => [c.iso3, c.unusualness]));
  const tiersMap = Object.fromEntries(index.countries.filter((c) => c.tier).map((c) => [c.iso3, c.tier]));
  const byIso = Object.fromEntries(index.countries.map((c) => [c.iso3, c]));
  const p = latest.pulse;
  const mapBox = h("div", { class: "map" });
  const hero = h("div", { class: "hero" },
    h("div",
      h("div", { class: "hero-date" }, h("span", `Data for ${fmt.longDate(latest.date)} (UTC)`), instrumentStatus(latest.instrument)),
      h("h1", HEADLINES[p.label] || "Today in the world's news."),
      h("p", { class: "lead" }, latest.brief[0]),
      tiles(latest)),
    h("div", { class: "hero-map" }, mapBox, h("div", { style: { padding: "6px 6px 2px", display: "flex", justifyContent: "space-between", gap: "10px", flexWrap: "wrap", alignItems: "center" } },
      h("span", { class: "muted", style: { fontSize: "13px" } }, "Darker = more unusual for that country. Click a country."),
      h("a", { class: "btn", href: "#/map" }, icon("globe"), "Open the map"))));
  page.append(hero);
  const drawMap = () => worldMap(mapBox, mapData, { values, tiers: tiersMap, onClick: (iso) => { location.hash = `#/country/${iso}`; },
    tooltip: (iso) => [h("div", { class: "tt-title" }, `${byIso[iso].flag} ${byIso[iso].name}`), h("div", fmt.rp(Math.pow(10, byIso[iso].unusualness ?? 0)) + " today"),
      byIso[iso].tier ? h("div", { class: "tt-note" }, `Alarm: ${["", "Unusual", "Rare", "Extreme"][byIso[iso].tier]}`) : null] });
  drawMap();
  window.addEventListener("themechange", drawMap, { once: true });

  const stand = h("section", { "aria-labelledby": "stand-title" });
  stand.append(h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Alarms"), h("h2", { id: "stand-title" }, "What stands out today"),
    h("p", { class: "note", style: { maxWidth: "66ch" } }, "An alarm means a country's news record did something it does less than once in 100 days, seen by at least 20 news outlets. It is a prompt to look closer — not proof that anything happened."))));
  if (latest.alarms.length) {
    stand.append(h("div", { class: "alarm-list" }, latest.alarms.slice(0, 9).map((a) => alarmCard(a))));
  } else {
    stand.append(h("div", { class: "split" },
      h("div", { class: "card" }, h("h3", "No alarms today"), h("p", { class: "ink2", style: { margin: "6px 0 14px" } }, "No country's news record crossed the 1-in-100-days threshold with broad coverage. Quiet days are the norm — that is what makes alarms meaningful."),
        h("div", { class: "eyebrow" }, "Recent alarms"),
        h("div", { class: "rows" }, latest.recent.slice().reverse().filter((d) => d.alarms.length).slice(0, 6).map((d) =>
          h("div", { style: { display: "flex", gap: "10px", alignItems: "baseline", padding: "6px 0", borderBottom: "1px solid var(--border)", flexWrap: "wrap" } },
            h("span", { class: "muted tabular", style: { fontSize: "13px", minWidth: "84px" } }, fmt.date(d.date, { day: "numeric", month: "short" })),
            h("span", { class: "chips" }, d.alarms.slice(0, 4).map((a) => h("a", { class: "chip", href: `#/country/${a.iso3}` }, h("span", { class: `tier-badge tier-${a.tier}`, style: { padding: "0", background: "none" } }, h("i")), a.name)))))),
        latest.recent.every((d) => !d.alarms.length) ? h("p", { class: "muted" }, "None in the past two weeks.") : null),
      h("div", { class: "card" }, h("h3", "Closest to the threshold"), h("p", { class: "note", style: { marginTop: "2px" } }, "The most unusual records today, below alarm level."),
        h("div", { class: "rows", style: { marginTop: "8px" } }, latest.watchlist.slice(0, 6).map(watchRow)))));
  }
  if (latest.alarms.length) {
    stand.append(h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", "Also unusual, below alarm level"),
      h("div", { class: "rows", style: { marginTop: "8px" } }, latest.watchlist.filter((w) => !w.tier).slice(0, 6).map(watchRow))));
  }
  page.append(stand);
  const nowcast = h("section");
  nowcastSection(nowcast, latest.nowcast);
  if (nowcast.childNodes.length) page.append(nowcast);
  const seis = h("section");
  page.append(seis);
  await seismograph(seis, latest);
  const mix = h("section");
  page.append(mix);
  mixSection(mix, latest);
  page.append(h("section", h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "In 30 seconds"), h("h2", "How WORLDLINE works"))),
    h("div", { class: "steps" },
      h("div", { class: "card step" }, h("h3", "Read the world's news, as data"), h("p", { class: "ink2", style: { margin: "6px 0 0" } }, "Every 15 minutes GDELT turns news from around the world into coded events: who did what to whom, where. WORLDLINE reads only that metadata — about 100,000 events a day.")),
      h("div", { class: "card step" }, h("h3", "Compare each country with itself"), h("p", { class: "ink2", style: { margin: "6px 0 0" } }, "For 156 countries we forecast tomorrow's coverage and event mix from their own past, then ask how surprising the real day was — a 1-in-N-days event.")),
      h("div", { class: "card step" }, h("h3", "Check ourselves in public"), h("p", { class: "ink2", style: { margin: "6px 0 0" } }, "We test every alarm against events Wikipedia's editors independently listed as notable, with a protocol fixed in advance. ", h("a", { href: "#/record" }, "See the track record"), ".")))));
}
