import { fill, fmt, h, icon } from "../lib/dom.js";
import { FAMILY_LABELS, FAMILY_ORDER, load } from "../lib/data.js";
import { legend, scatter, tableTwin } from "../lib/charts.js";

export async function render(page, route) {
  const [w, space] = await Promise.all([load("worldlines.json"), load("event_space.json")]);
  const names = Object.fromEntries(w.countries.map((c) => [c.iso3, c.name]));
  const months = w.months;
  let t = months.length - 1;
  let timer = null;
  const movers = Object.entries(w.repositioning).sort((a, b) => b[1] - a[1]);
  const focus = (route.query.get("focus") || "").toUpperCase();
  const measured = new Set(w.well_measured);
  const defaults = ["USA", "CHN", "RUS", "UKR", "ISR", "IRN", "IND"].filter((iso) => measured.has(iso));
  const selected = new Set(focus && names[focus] ? [focus] : defaults.slice(0, 5));
  let fullPath = false;
  const box = h("div", { class: "chart" });
  const monthLabel = h("div", { class: "big-number", style: { fontSize: "clamp(24px,3vw,34px)" }, "aria-live": "polite" });
  const slider = h("input", { type: "range", min: 0, max: months.length - 1, value: t, "aria-label": "Choose a month" });
  const play = h("button", { class: "btn primary", type: "button" }, icon("play"), "Play");
  const search = h("input", { type: "search", placeholder: "Add a country…", "aria-label": "Highlight a country", list: "worldline-countries" });
  const datalist = h("datalist", { id: "worldline-countries" }, w.countries.map((c) => h("option", { value: c.name })));
  const chips = h("div", { class: "chips" });
  const pathToggle = h("label", { class: "chip", style: { cursor: "pointer" } }, h("input", { type: "checkbox", style: { margin: 0 } }), "Full path since 2023");
  pathToggle.querySelector("input").addEventListener("change", (e) => { fullPath = e.target.checked; draw(); });
  const moverBox = h("div", { class: "rows" });

  page.append(h("section", { style: { marginTop: "32px" } },
    h("p", { class: "eyebrow" }, "Learned embeddings · relational space"), h("h1", { style: { fontSize: "clamp(28px,3.6vw,42px)" } }, "Worldlines: how countries move"),
    h("p", { class: "lead" }, "Every month, each country gets a position learned only from the news record of who it deals with and how — cooperation or conflict, with which partners. Countries with similar relationships end up close together. Their paths through this space are their worldlines."),
    h("div", { class: "split", style: { marginTop: "22px" } },
      h("div", { class: "card" }, h("div", { class: "card-head", style: { flexWrap: "wrap" } }, monthLabel, h("div", { class: "controls" }, play)), slider,
        h("div", { style: { marginTop: "10px" } }, box),
        h("div", { class: "controls", style: { marginTop: "10px" } }, search, datalist, chips, pathToggle),
        h("p", { class: "note" }, `Grey dots: the ${w.well_measured.length} countries with enough reported interactions for a stable position. Highlighted countries trail their path (smoothed over three months). The axes are the two strongest directions of difference in relations and have no fixed meaning — what matters is who is near whom, and who moves.`)),
      h("div", { class: "card" }, h("h3", "Biggest repositioning, past 12 months"),
        h("p", { class: "note", style: { marginTop: "2px" } }, "How far each country's relational position moved between a year ago and now (0 = same place, 2 = opposite). Click to highlight."), moverBox))));

  function renderChips() {
    fill(chips, [...selected].map((iso) => {
      const chip = h("button", { class: "chip", type: "button", "aria-label": `Remove ${names[iso]}` }, names[iso], " ×");
      chip.addEventListener("click", () => { selected.delete(iso); draw(); });
      return chip;
    }));
  }
  const allPoints = w.well_measured.flatMap((iso) => w.xy[iso]).filter(Boolean);
  const smooth = (path) => path.map((p, i) => {
    const win = path.slice(Math.max(0, i - 1), i + 2).filter(Boolean);
    return p && win.length ? [win.reduce((a, q) => a + q[0], 0) / win.length, win.reduce((a, q) => a + q[1], 0) / win.length] : null;
  });
  const bounds = { x: [Math.min(...allPoints.map((p) => p[0])), Math.max(...allPoints.map((p) => p[0]))], y: [Math.min(...allPoints.map((p) => p[1])), Math.max(...allPoints.map((p) => p[1]))] };
  function draw() {
    const style = getComputedStyle(document.documentElement);
    const accent = style.getPropertyValue("--accent").trim();
    const grey = style.getPropertyValue("--baseline").trim();
    const points = [];
    for (const c of w.countries) {
      const emphasis = selected.has(c.iso3);
      if (!measured.has(c.iso3) && !emphasis) continue;
      const path = smooth(w.xy[c.iso3]);
      const pos = path[t];
      if (!pos) continue;
      points.push({ id: c.iso3, x: pos[0], y: pos[1], color: emphasis ? accent : grey, r: emphasis ? 5.5 : 3.5, emphasis, label: emphasis ? c.name : null,
        trail: emphasis ? path.slice(fullPath ? 0 : Math.max(0, t - 12), t + 1) : null });
    }
    scatter(box, { points, bounds, height: Math.min(520, Math.max(340, box.clientWidth * 0.7)),
      tooltip: (p) => [h("div", { class: "tt-title" }, names[p.id]), h("div", { class: "tt-note" }, w.repositioning[p.id] !== undefined ? `Moved ${w.repositioning[p.id].toFixed(2)} in the past year` : "Movement: not enough data"), h("div", { class: "tt-note" }, "Click to highlight or remove")],
      onClick: (p) => { if (selected.has(p.id)) selected.delete(p.id); else selected.add(p.id); draw(); } });
    monthLabel.textContent = fmt.month(months[t]);
    slider.value = String(t);
    renderChips();
  }
  const top = movers.length ? movers[0][1] : 1;
  fill(moverBox, movers.slice(0, 10).map(([iso, distance]) => {
    const row = h("button", { class: "mover", type: "button", style: { border: 0, background: "none", width: "100%", textAlign: "left" } },
      h("div", { style: { minWidth: 0 } }, h("div", { class: "row-title" }, names[iso]),
        h("div", { style: { height: "4px", borderRadius: "2px", marginTop: "6px", background: "var(--accent)", opacity: 0.55, width: `${Math.max(4, (distance / top) * 100)}%` } })),
      h("span", { class: "tabular ink2", style: { fontSize: "13.5px" } }, distance.toFixed(2)));
    row.addEventListener("click", () => { selected.add(iso); draw(); });
    return row;
  }), h("p", { class: "note" }, "Big moves often follow wars, coups, elections or diplomatic realignments — open a country's page to see what happened."));
  slider.addEventListener("input", () => { stop(); t = +slider.value; draw(); });
  search.addEventListener("change", () => {
    const match = w.countries.find((c) => c.name.toLowerCase() === search.value.trim().toLowerCase());
    if (match) { selected.add(match.iso3); search.value = ""; draw(); }
  });
  const stop = () => { clearInterval(timer); timer = null; fill(play, icon("play"), "Play"); };
  play.addEventListener("click", () => {
    if (timer) { stop(); return; }
    if (t >= months.length - 1) t = 0;
    fill(play, icon("pause"), "Pause");
    timer = setInterval(() => { if (t >= months.length - 1 || !document.body.contains(page)) { stop(); return; } t += 1; draw(); }, 420);
  });
  window.addEventListener("hashchange", stop, { once: true });
  draw();
  window.addEventListener("relayout", draw, { once: true });
  window.addEventListener("themechange", draw, { once: true });

  // Event-type space
  const spaceBox = h("div", { class: "chart" });
  const chk = space.checks;
  page.append(h("section", h("div", { class: "section-head" }, h("div", h("p", { class: "eyebrow" }, "Learned embeddings · event types"), h("h2", "The geometry of what happens"),
      h("p", { class: "note", style: { maxWidth: "70ch" } }, `Each dot is one of ${space.codes.length} kinds of event in the CAMEO codebook. Positions were learned only from which kinds of events the same news articles report together (2023 data). Colour is CAMEO's own label — which the learning never saw.`))),
    h("div", { class: "split" }, h("div", { class: "card" }, spaceBox, legend([{ color: "var(--fam-cooperation)", label: "Material cooperation" }, { color: "var(--fam-diplomacy)", label: "Verbal cooperation" },
        { color: "var(--fam-protest)", label: "Verbal conflict" }, { color: "var(--fam-violence)", label: "Material conflict" }])),
      h("div", { class: "card" }, h("h3", "Did the learning find real meaning?"), h("div", { class: "prose", style: { fontSize: "14.5px", marginTop: "8px" } },
        h("p", h("strong", `${fmt.pct(chk.knn_quadclass_accuracy)}`), ` of event types have neighbours that mostly share their cooperation/conflict class (chance: ${fmt.pct(chk.label_permutation_mean)}; best possible guess without the map: ${fmt.pct(chk.majority_baseline)}).`),
        h("p", "A straight line through the space recovers the expert Goldstein conflict–cooperation scale with a rank correlation of ", h("strong", chk.goldstein_cv_spearman.toFixed(2)), " (cross-validated)."),
        h("p", "These learned distances also power WORLDLINE's learned-geometry optimal transport: how far the world's event mix has moved, where 'fighting' is closer to 'assault' than to 'praise'."),
        h("p", { class: "muted" }, "Honest note: a channel built on these embeddings did not improve alarm accuracy (see the track record)."))))));
  const quadColor = { 1: "--fam-diplomacy", 2: "--fam-cooperation", 3: "--fam-protest", 4: "--fam-violence" };
  const drawSpace = () => {
    const style = getComputedStyle(document.documentElement);
    scatter(spaceBox, { height: 420, points: space.codes.map((code) => ({ id: code.code, x: code.x, y: code.y, r: 3 + Math.min(4, Math.log10(Math.max(code.events_2023, 10)) - 2),
      color: style.getPropertyValue(quadColor[code.quad]).trim(), label: null })),
      tooltip: (p) => { const code = space.codes.find((c) => c.code === p.id); return [h("div", { class: "tt-title" }, code.label), h("div", { class: "tt-note" }, `CAMEO ${code.code} · ${FAMILY_LABELS[code.family]} · ${fmt.compact(code.events_2023)} events in 2023`)]; } });
  };
  drawSpace();
  window.addEventListener("themechange", drawSpace, { once: true });
  page.append(h("section", tableTwin("Repositioning over the past year", [{ label: "Country", value: (r) => names[r[0]] }, { label: "Moved (cosine distance)", value: (r) => r[1].toFixed(3), num: true }], movers)));
  void FAMILY_ORDER;
}
