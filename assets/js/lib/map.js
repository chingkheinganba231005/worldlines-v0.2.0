// Choropleth of unusualness on the pre-projected Equal Earth map (data/map.json).
import { clear, fmt, h, s } from "./dom.js";
import { hideTooltip, showTooltip } from "./charts.js";

// Bins of unusualness u = -log10(p) <-> return period 10^u days.
export const BINS = [
  { min: -Infinity, color: "var(--land)", label: "typical" },
  { min: 1, color: "var(--seq-1)", label: "1 in 10" },
  { min: Math.log10(30), color: "var(--seq-2)", label: "1 in 30" },
  { min: 2, color: "var(--seq-3)", label: "1 in 100" },
  { min: Math.log10(365), color: "var(--seq-4)", label: "1 in 365" },
  { min: 3, color: "var(--seq-5)", label: "1 in 1,000" },
  { min: Math.log10(5000), color: "var(--seq-6)", label: "1 in 5,000+" },
];

export function colorFor(u) {
  if (u === null || u === undefined || !Number.isFinite(u)) return null;
  let color = BINS[0].color;
  for (const bin of BINS) if (u >= bin.min) color = bin.color;
  return color;
}

export function scaleLegend() {
  return h("div", { "aria-label": "Colour scale: how unusual a country's news record is today" },
    h("div", { class: "scale-block" }, h("div", { class: "scale-title" }, "How unusual for that country"),
      h("div", { class: "scale-bar" }, BINS.map((b) => h("span", { style: { background: b.color } }))),
      h("div", { class: "scale-labels" }, h("span", "typical"), h("span", "1 in 100 days"), h("span", "1 in 5,000+"))),
    h("div", { class: "scale", style: { marginTop: "8px" } }, h("span", { class: "legend-inline" }, h("span", { style: { width: "12px", height: "12px", borderRadius: "3px", background: "var(--land-off)", border: "1px solid var(--border)", display: "inline-block" } }), "Not monitored (too little coverage)"),
      h("span", { class: "legend-inline" }, h("span", { class: "dot", style: { width: "10px", height: "10px", borderRadius: "50%", background: "var(--tier-3)", boxShadow: "0 0 0 2px var(--surface)", display: "inline-block" } }), "Alarm")));
}

export function worldMap(container, mapData, opts = {}) {
  const { width, height, countries } = mapData;
  const values = opts.values || {};
  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "World map of unusualness" });
  const pins = s("g");
  const tiny = s("g");
  for (const [iso3, shape] of Object.entries(countries)) {
    const color = colorFor(values[iso3]);
    const monitored = iso3 in values;
    const path = s("path", { d: shape.d, class: `country ${monitored ? "on" : "off"}`, fill: monitored ? (color || "var(--land)") : null, "data-iso3": iso3 });
    if (opts.selected === iso3) path.classList.add("focus");
    svg.append(path);
    if (monitored && shape.a < 6) {
      tiny.append(s("circle", { class: "tiny", cx: shape.c[0], cy: shape.c[1], r: 3.2, fill: color || "var(--land)", "data-iso3": iso3 }));
    }
    const tier = opts.tiers?.[iso3];
    if (tier) {
      pins.append(s("circle", { cx: shape.c[0], cy: shape.c[1], r: 3 + tier * 1.4, fill: `var(--tier-${tier})`, stroke: "var(--surface)", "stroke-width": 2, "pointer-events": "none" }));
    }
  }
  svg.append(tiny, pins);
  const target = (event) => event.target.closest?.("[data-iso3]");
  svg.addEventListener("pointermove", (event) => {
    const node = target(event);
    if (!node || !(node.dataset.iso3 in values)) { hideTooltip(); return; }
    const content = opts.tooltip ? opts.tooltip(node.dataset.iso3) : [h("div", { class: "tt-title" }, node.dataset.iso3), h("div", fmt.rp(Math.pow(10, values[node.dataset.iso3])))];
    showTooltip(content, event.clientX, event.clientY);
  });
  svg.addEventListener("pointerleave", hideTooltip);
  svg.addEventListener("click", (event) => {
    const node = target(event);
    if (node && node.dataset.iso3 in values && opts.onClick) { hideTooltip(); opts.onClick(node.dataset.iso3); }
  });
  clear(container).append(svg);
  return svg;
}
