// Hand-built SVG charts. Conventions (docs/design.md): 2px lines, hairline grid, markers with a
// 2px surface ring, a crosshair that snaps to the nearest date, tooltips that list every series,
// keyboard navigation (arrow keys), and a data-table twin for every chart.
import { clear, fill, fmt, h, s } from "./dom.js";

const tooltipNode = () => document.getElementById("tooltip");

export function showTooltip(content, x, y) {
  const node = tooltipNode();
  fill(node, ...(Array.isArray(content) ? content : [content]));
  node.hidden = false;
  const box = node.getBoundingClientRect();
  const left = Math.min(window.innerWidth - box.width - 12, x + 14);
  const top = y + box.height + 24 > window.innerHeight ? y - box.height - 14 : y + 14;
  node.style.left = Math.max(8, left) + "px";
  node.style.top = Math.max(8, top) + "px";
}

export function hideTooltip() {
  const node = tooltipNode();
  if (node) node.hidden = true;
}

export function ttRow(color, label, value) {
  return h("div", { class: "tt-row" }, color ? h("span", { class: "tt-key", style: { background: color } }) : null, h("b", value), " ", label);
}

function niceStep(raw) {
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const f of [1, 2, 2.5, 5, 10]) if (raw <= f * power) return f * power;
  return 10 * power;
}

function niceAxis(maxValue, minValue = 0, ticks = 4) {
  const span = Math.max(maxValue - minValue, 1e-9);
  const step = niceStep(span / ticks);
  return { min: Math.floor(minValue / step) * step, max: Math.ceil(maxValue / step) * step, step };
}

function dateTicks(dates, count) {
  const n = dates.length;
  if (n <= 1) return [0];
  const span = (new Date(dates[n - 1]) - new Date(dates[0])) / 864e5;
  let candidates = [];
  if (span > 500) {
    dates.forEach((d, i) => { if (i > 0 && d.slice(0, 4) !== dates[i - 1].slice(0, 4)) candidates.push(i); });
  } else if (span > 120) {
    dates.forEach((d, i) => { if (i > 0 && d.slice(0, 7) !== dates[i - 1].slice(0, 7)) candidates.push(i); });
  } else {
    const step = Math.max(1, Math.round(n / count));
    for (let i = 0; i < n; i += step) candidates.push(i);
  }
  if (!candidates.length) candidates = [0];
  const minGap = n / (count + 1);
  const kept = [];
  for (const t of candidates) if (!kept.length || t - kept[kept.length - 1] >= minGap) kept.push(t);
  return kept;
}

function tickLabel(dates, i) {
  const d = dates[i];
  const span = (new Date(dates[dates.length - 1]) - new Date(dates[0])) / 864e5;
  if (span > 500) return d.slice(0, 4);
  if (span > 120) return d.slice(5, 7) === "01" ? d.slice(0, 4) : fmt.date(d, { month: "short" });
  return fmt.date(d, { day: "numeric", month: "short" });
}

/**
 * Time-series line chart.
 * opts: { dates, series:[{label, values, color, area?, dashed?}], height, yMax, yFormat, markers:[{i, color, r, label}],
 *         ticks:[{i, color}], onSelect(i), selected, tooltip(i) -> nodes, caption }
 */
export function lineChart(container, opts) {
  const { dates, series, height = 240 } = opts;
  const width = Math.max(320, container.clientWidth || 800);
  const m = { top: 12, right: 14, bottom: 26, left: 44 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;
  const n = dates.length;
  const all = series.flatMap((sr) => sr.values.filter((v) => v !== null && Number.isFinite(v)));
  const axis = niceAxis(opts.yMax ?? Math.max(...all, 0) * 1.04, opts.yMin ?? 0);
  const yMax = opts.yMax ?? axis.max;
  const yMin = opts.yMin ?? 0;
  const tickStep = opts.yMax ? (yMax - yMin) / 4 : axis.step;
  const X = (i) => m.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const Y = (v) => m.top + (1 - (Math.min(Math.max(v, yMin), yMax) - yMin) / (yMax - yMin || 1)) * innerH;
  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "Time series chart" });
  for (let v = yMin; v <= yMax + tickStep / 1000; v += tickStep) {
    const y = Y(v);
    const k = v === yMin ? 0 : 1;
    svg.append(s("line", { class: k === 0 ? "base-line" : "grid-line", x1: m.left, x2: width - m.right, y1: y, y2: y }));
    svg.append(s("text", { x: m.left - 8, y: y + 4, "text-anchor": "end" }, (opts.yFormat || fmt.compact)(v)));
  }
  const xTicks = opts.xLabels
    ? Array.from({ length: Math.min(n, 7) }, (_, k) => Math.round((k * (n - 1)) / Math.max(1, Math.min(n, 7) - 1)))
    : dateTicks(dates, Math.max(3, Math.floor(innerW / 110)));
  for (const t of xTicks) {
    svg.append(s("text", { x: X(t), y: height - 6, "text-anchor": "middle" }, opts.xLabels ? opts.xLabels[t] : tickLabel(dates, t)));
  }
  if (opts.band) {
    const { lo, hi, color } = opts.band;
    let d = "";
    let open = false;
    const close = [];
    for (let i = 0; i < n; i++) {
      if (lo[i] === null || hi[i] === null) { if (open) { d += close.reverse().join("") + "Z"; close.length = 0; open = false; } continue; }
      d += `${open ? "L" : "M"}${X(i).toFixed(1)},${Y(hi[i]).toFixed(1)}`;
      close.push(`L${X(i).toFixed(1)},${Y(lo[i]).toFixed(1)}`);
      open = true;
    }
    if (open) d += close.reverse().join("") + "Z";
    svg.append(s("path", { d, fill: color, opacity: 0.12, stroke: "none" }));
  }
  for (const sr of series) {
    let d = "";
    let pen = false;
    sr.values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`;
      pen = true;
    });
    if (sr.area) {
      const first = sr.values.findIndex((v) => v !== null);
      let last = -1;
      sr.values.forEach((v, i) => { if (v !== null) last = i; });
      if (first >= 0) svg.append(s("path", { d: `${d}L${X(last)},${Y(yMin)}L${X(first)},${Y(yMin)}Z`, fill: sr.color, opacity: 0.1 }));
    }
    svg.append(s("path", { d, fill: "none", stroke: sr.color, "stroke-width": sr.width || 2, "stroke-linejoin": "round",
      "stroke-linecap": "round", "stroke-dasharray": sr.dashed ? "5 4" : null, opacity: sr.opacity || 1 }));
  }
  for (const tk of opts.ticks || []) {
    svg.append(s("line", { x1: X(tk.i), x2: X(tk.i), y1: m.top + innerH, y2: m.top + innerH - 5, stroke: tk.color, "stroke-width": 1.5, opacity: 0.55 }));
  }
  for (const mk of opts.markers || []) {
    svg.append(s("circle", { cx: X(mk.i), cy: Y(mk.v), r: mk.r || 4.5, fill: mk.color, stroke: "var(--surface)", "stroke-width": 2 }));
  }
  const cross = s("line", { class: "crosshair", x1: 0, x2: 0, y1: m.top, y2: m.top + innerH, visibility: "hidden" });
  const dot = s("g", { visibility: "hidden" });
  svg.append(cross, dot);
  const selectedLine = s("line", { x1: 0, x2: 0, y1: m.top, y2: m.top + innerH, stroke: "var(--ink-2)", "stroke-width": 1, "stroke-dasharray": "2 3", opacity: 0.6, visibility: "hidden" });
  svg.append(selectedLine);
  const setSelected = (i) => {
    if (i === null || i === undefined) { selectedLine.setAttribute("visibility", "hidden"); return; }
    selectedLine.setAttribute("x1", X(i)); selectedLine.setAttribute("x2", X(i)); selectedLine.setAttribute("visibility", "visible");
  };
  setSelected(opts.selected);
  let active = null;
  const show = (i, clientX, clientY) => {
    active = i;
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
    clear(dot);
    for (const sr of series) {
      const v = sr.values[i];
      if (v !== null && Number.isFinite(v)) dot.append(s("circle", { cx: X(i), cy: Y(v), r: 4, fill: sr.color, stroke: "var(--surface)", "stroke-width": 2 }));
    }
    dot.setAttribute("visibility", "visible");
    const content = opts.tooltip ? opts.tooltip(i) : [h("div", { class: "tt-title" }, fmt.date(dates[i])),
      ...series.map((sr) => ttRow(sr.color, sr.label, (opts.yFormat || fmt.compact)(sr.values[i])))];
    const rect = svg.getBoundingClientRect();
    showTooltip(content, clientX ?? rect.left + (X(i) / width) * rect.width, clientY ?? rect.top + 20);
  };
  const hide = () => { active = null; cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); hideTooltip(); };
  const indexAt = (event) => {
    const rect = svg.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * width;
    return Math.max(0, Math.min(n - 1, Math.round(((x - m.left) / innerW) * (n - 1))));
  };
  svg.addEventListener("pointermove", (e) => show(indexAt(e), e.clientX, e.clientY));
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("click", (e) => { const i = indexAt(e); if (opts.onSelect) { opts.onSelect(i); setSelected(i); } });
  svg.setAttribute("tabindex", "0");
  svg.addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Enter", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    let i = active ?? opts.selected ?? n - 1;
    if (e.key === "ArrowLeft") i = Math.max(0, i - 1);
    if (e.key === "ArrowRight") i = Math.min(n - 1, i + 1);
    if (e.key === "Home") i = 0;
    if (e.key === "End") i = n - 1;
    if (e.key === "Enter" && opts.onSelect) { opts.onSelect(i); setSelected(i); }
    show(i);
  });
  svg.addEventListener("blur", hide);
  clear(container).append(svg);
  return { setSelected };
}

export function sparkline(values, { width = 90, height = 26, color = "var(--accent)", max } = {}) {
  const finite = values.filter((v) => v !== null && Number.isFinite(v));
  const top = max ?? Math.max(2.5, ...finite);
  const n = values.length;
  const X = (i) => (n <= 1 ? width / 2 : (i / (n - 1)) * (width - 4) + 2);
  const Y = (v) => height - 3 - (Math.min(v, top) / top) * (height - 6);
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) { pen = false; return; }
    d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`;
    pen = true;
  });
  const last = values.length - 1;
  return s("svg", { class: "spark", viewBox: `0 0 ${width} ${height}`, "aria-hidden": "true" },
    s("line", { x1: 0, x2: width, y1: Y(2), y2: Y(2), stroke: "var(--grid)", "stroke-width": 1 }),
    s("path", { d, fill: "none", stroke: color, "stroke-width": 1.6, "stroke-linejoin": "round" }),
    values[last] !== null && Number.isFinite(values[last]) ? s("circle", { cx: X(last), cy: Y(values[last]), r: 2.6, fill: color }) : null);
}

/** 100% stacked horizontal bars, ordered along the cooperation -> conflict scale, with a 2px surface gap. */
/** White or near-black, whichever contrasts more with a #rrggbb fill (WCAG relative luminance). */
function inkOn(fill) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(fill).trim());
  if (!m) return "var(--ink)";
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const dark = 0.011;  // relative luminance of #1b1b1b
  return (1.05) / (luminance + 0.05) >= (luminance + 0.05) / (dark + 0.05) ? "#fff" : "#1b1b1b";
}

export function stackedBars(container, { rows, order, colors, labels }) {
  const width = Math.max(300, container.clientWidth || 700);
  const barH = 26;
  const gap = 18;
  const labelW = Math.min(110, width * 0.22);
  const height = rows.length * (barH + gap) + 4;
  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Share of reported events by type" });
  rows.forEach((row, r) => {
    const y = r * (barH + gap) + 2;
    svg.append(s("text", { x: 0, y: y + barH / 2 + 4, "font-size": 12.5, fill: "var(--ink-2)" }, row.label));
    let x = labelW;
    const full = width - labelW;
    order.forEach((id, k) => {
      const share = row.shares[id] || 0;
      const w = share * full;
      if (w <= 0) return;
      const segment = s("rect", { x: x + (k ? 1 : 0), y, width: Math.max(0, w - (k ? 2 : 1)), height: barH, rx: 3, fill: colors[id] });
      segment.addEventListener("pointermove", (e) => showTooltip([h("div", { class: "tt-title" }, labels[id]),
        ttRow(colors[id], row.label, fmt.pct(share, 1))], e.clientX, e.clientY));
      segment.addEventListener("pointerleave", hideTooltip);
      svg.append(segment);
      const text = fmt.pct(share, 0);
      if (w > text.length * 7.5 + 10) {
        svg.append(s("text", { x: x + w / 2, y: y + barH / 2 + 4, "text-anchor": "middle", "font-size": 11.5, "font-weight": 600,
          style: `fill:${inkOn(colors[id])}`, "pointer-events": "none" }, text));
      }
      x += w;
    });
  });
  clear(container).append(svg);
}

/** Horizontal bars with optional interval whiskers. items: [{label, value, lo, hi, color, sub, href}] */
export function barList(container, { items, max, format = (v) => v.toFixed(2), zero = 0, height = 26 }) {
  const width = Math.max(300, container.clientWidth || 600);
  const labelW = Math.min(230, Math.max(120, width * 0.36));
  const valueW = 64;
  const plotW = width - labelW - valueW - 8;
  const top = max ?? Math.max(...items.map((d) => Math.max(d.hi ?? d.value, d.value)), 1e-9);
  const bottom = Math.min(zero, ...items.map((d) => Math.min(d.lo ?? d.value, d.value)));
  const X = (v) => labelW + ((v - bottom) / (top - bottom || 1)) * plotW;
  const H = items.length * height + 6;
  const svg = s("svg", { viewBox: `0 0 ${width} ${H}`, role: "img", "aria-label": "Bar chart" });
  svg.append(s("line", { class: "base-line", x1: X(zero), x2: X(zero), y1: 0, y2: H }));
  items.forEach((d, i) => {
    const y = i * height + 4;
    const cy = y + height / 2 - 2;
    const maxChars = Math.floor(labelW / 7.2);
    const label = s("text", { x: 0, y: cy + 4, "font-size": 12.5, fill: "var(--ink)" }, d.label.length > maxChars ? d.label.slice(0, maxChars - 1) + "…" : d.label);
    svg.append(label);
    const x0 = X(Math.min(zero, d.value));
    const x1 = X(Math.max(zero, d.value));
    const bar = s("rect", { x: x0, y: cy - 7, width: Math.max(1, x1 - x0), height: 14, rx: 4, fill: d.color || "var(--accent)" });
    svg.append(bar);
    if (d.lo !== undefined && d.hi !== undefined && d.lo !== null) {
      svg.append(s("line", { x1: X(d.lo), x2: X(d.hi), y1: cy, y2: cy, stroke: "var(--ink)", "stroke-width": 1.4, opacity: 0.7 }));
      svg.append(s("line", { x1: X(d.lo), x2: X(d.lo), y1: cy - 5, y2: cy + 5, stroke: "var(--ink)", "stroke-width": 1.4, opacity: 0.7 }));
      svg.append(s("line", { x1: X(d.hi), x2: X(d.hi), y1: cy - 5, y2: cy + 5, stroke: "var(--ink)", "stroke-width": 1.4, opacity: 0.7 }));
    }
    svg.append(s("text", { x: width - 4, y: cy + 4, "text-anchor": "end", "font-size": 12.5, fill: "var(--ink-2)" }, format(d.value)));
    const hit = s("rect", { x: 0, y, width, height, fill: "transparent" });
    hit.addEventListener("pointermove", (e) => showTooltip([h("div", { class: "tt-title" }, d.label), ttRow(d.color, d.sub || "value", format(d.value)),
      d.lo !== undefined && d.lo !== null ? h("div", { class: "tt-note" }, `80% interval ${format(d.lo)} to ${format(d.hi)}`) : null], e.clientX, e.clientY));
    hit.addEventListener("pointerleave", hideTooltip);
    if (d.onClick) { hit.style.cursor = "pointer"; hit.addEventListener("click", d.onClick); }
    svg.append(hit);
  });
  clear(container).append(svg);
}

/** Accessible table twin inside a <details>. columns: [{label, value(row), num}] */
export function tableTwin(title, columns, rows) {
  return h("details", { class: "table-toggle" }, h("summary", `Show the data as a table (${rows.length} rows)`),
    h("div", { class: "table-scroll" }, h("table", { class: "data-table" },
      h("caption", { class: "sr-only" }, title),
      h("thead", h("tr", columns.map((c) => h("th", { class: c.num ? "num" : null, scope: "col" }, c.label)))),
      h("tbody", rows.map((r) => h("tr", columns.map((c) => h("td", { class: c.num ? "num" : null }, c.value(r)))))))));
}

export function legend(items) {
  return h("ul", { class: "legend" }, items.map((it) => h("li", h("span", { class: it.kind || "sw", style: { background: it.color } }), it.label)));
}

/** 100% stacked area over time. layers: [{id, label, values (shares), color}] in stacking order (bottom first). */
export function stackedArea(container, { dates, layers, height = 220, tooltip }) {
  const width = Math.max(320, container.clientWidth || 800);
  const m = { top: 8, right: 14, bottom: 26, left: 44 };
  const innerW = width - m.left - m.right;
  const innerH = height - m.top - m.bottom;
  const n = dates.length;
  const X = (i) => m.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const Y = (v) => m.top + (1 - v) * innerH;
  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Share of events by type over time" });
  const base = new Array(n).fill(0);
  for (const layer of layers) {
    let upper = "";
    let lower = "";
    for (let i = 0; i < n; i++) {
      const v = layer.values[i] ?? 0;
      upper += `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(base[i] + v).toFixed(1)}`;
    }
    for (let i = n - 1; i >= 0; i--) lower += `L${X(i).toFixed(1)},${Y(base[i]).toFixed(1)}`;
    svg.append(s("path", { d: upper + lower + "Z", fill: layer.color, stroke: "var(--surface)", "stroke-width": 1 }));
    for (let i = 0; i < n; i++) base[i] += layer.values[i] ?? 0;
  }
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    svg.append(s("text", { x: m.left - 8, y: Y(v) + 4, "text-anchor": "end" }, `${Math.round(v * 100)}%`));
  }
  for (const t of dateTicks(dates, Math.max(3, Math.floor(innerW / 110)))) svg.append(s("text", { x: X(t), y: height - 6, "text-anchor": "middle" }, tickLabel(dates, t)));
  const cross = s("line", { class: "crosshair", x1: 0, x2: 0, y1: m.top, y2: m.top + innerH, visibility: "hidden", stroke: "var(--ink)" });
  svg.append(cross);
  svg.addEventListener("pointermove", (e) => {
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * width;
    const i = Math.max(0, Math.min(n - 1, Math.round(((x - m.left) / innerW) * (n - 1))));
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
    showTooltip(tooltip ? tooltip(i) : [h("div", { class: "tt-title" }, dates[i]), ...layers.slice().reverse().map((l) => ttRow(l.color, l.label, fmt.pct(l.values[i], 1)))], e.clientX, e.clientY);
  });
  svg.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTooltip(); });
  clear(container).append(svg);
}

/**
 * Scatter with optional trails. points: [{id, x, y, label, color, r, emphasis, trail:[[x,y]|null]}]
 * Hit areas are 24px (transparent) so small dots are easy to hover and tap.
 */
export function scatter(container, { points, height = 460, tooltip, onClick, padding = 0.06, bounds }) {
  const width = Math.max(320, container.clientWidth || 800);
  const xs = bounds ? bounds.x : [Math.min(...points.map((p) => p.x)), Math.max(...points.map((p) => p.x))];
  const ys = bounds ? bounds.y : [Math.min(...points.map((p) => p.y)), Math.max(...points.map((p) => p.y))];
  const padX = (xs[1] - xs[0]) * padding || 1;
  const padY = (ys[1] - ys[0]) * padding || 1;
  const X = (v) => ((v - xs[0] + padX) / (xs[1] - xs[0] + 2 * padX)) * width;
  const Y = (v) => height - ((v - ys[0] + padY) / (ys[1] - ys[0] + 2 * padY)) * height;
  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Scatter plot" });
  const trails = s("g");
  const dots = s("g");
  const labelsLayer = s("g");
  const hits = s("g");
  const ordered = points.slice().sort((a, b) => (a.emphasis ? 1 : 0) - (b.emphasis ? 1 : 0));
  for (const p of ordered) {
    if (p.trail) {
      let d = "";
      let pen = false;
      for (const pt of p.trail) {
        if (!pt) { pen = false; continue; }
        d += `${pen ? "L" : "M"}${X(pt[0]).toFixed(1)},${Y(pt[1]).toFixed(1)}`;
        pen = true;
      }
      trails.append(s("path", { d, fill: "none", stroke: p.color, "stroke-width": 1.6, opacity: 0.55, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    }
    dots.append(s("circle", { cx: X(p.x), cy: Y(p.y), r: p.r || 4, fill: p.color, stroke: "var(--surface)", "stroke-width": 2 }));
    if (p.label) {
      labelsLayer.append(s("text", { x: X(p.x) + 8, y: Y(p.y) + 4, "font-size": 12, "font-weight": 600, style: "fill: var(--ink); paint-order: stroke; stroke: var(--surface); stroke-width: 3px; stroke-linejoin: round" }, p.label));
    }
    const hit = s("circle", { cx: X(p.x), cy: Y(p.y), r: 12, fill: "transparent", "data-id": p.id });
    hit.addEventListener("pointermove", (e) => showTooltip(tooltip ? tooltip(p) : [h("div", { class: "tt-title" }, p.label || p.id)], e.clientX, e.clientY));
    hit.addEventListener("pointerleave", hideTooltip);
    if (onClick) { hit.style.cursor = "pointer"; hit.addEventListener("click", () => onClick(p)); }
    hits.append(hit);
  }
  svg.append(trails, dots, labelsLayer, hits);
  clear(container).append(svg);
}
