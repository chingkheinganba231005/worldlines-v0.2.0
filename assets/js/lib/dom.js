// Tiny, safe DOM helpers. Strings are always inserted as text (never parsed as HTML).
const SVG_NS = "http://www.w3.org/2000/svg";

function append(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function setAttrs(node, attrs, svg = false) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.setAttribute("class", value);
    else if (key === "style" && typeof value === "object") Object.assign(node.style, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(svg ? key : key, value === true ? "" : String(value));
  }
  return node;
}

export function h(tag, attrs, ...children) {
  if (attrs instanceof Node || typeof attrs !== "object" || Array.isArray(attrs) || attrs === null) {
    children.unshift(attrs);
    attrs = {};
  }
  return append(setAttrs(document.createElement(tag), attrs), children);
}

export function s(tag, attrs, ...children) {
  return append(setAttrs(document.createElementNS(SVG_NS, tag), attrs, true), children);
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

// Replace a node's children; null/undefined/false children are skipped (native append would print "null").
export function fill(node, ...children) {
  return append(clear(node), children);
}

export function safeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function extLink(url, ...children) {
  const href = safeUrl(url);
  if (!href) return h("span", ...children);
  return h("a", { href, target: "_blank", rel: "noopener noreferrer nofollow" }, ...children);
}

const ICONS = {
  attention: "M3 12h3l3-8 4 16 3-8h5",
  mix: "M4 6h16M4 12h10M4 18h6",
  conflict: "M12 3l9 16H3z M12 10v4 M12 17h.01",
  check: "M5 12l4 4 10-10",
  alert: "M12 3l9 16H3z M12 10v4 M12 17h.01",
  info: "M12 8h.01 M11 12h1v5h1 M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  play: "M7 5v14l11-7z",
  pause: "M8 5v14 M16 5v14",
  prev: "M15 6l-6 6 6 6",
  next: "M9 6l6 6-6 6",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  sun: "M12 4V2 M12 22v-2 M4 12H2 M22 12h-2 M5.6 5.6 4.2 4.2 M19.8 19.8l-1.4-1.4 M5.6 18.4l-1.4 1.4 M19.8 4.2l-1.4 1.4 M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  wiki: "M4 6l4 12 4-9 4 9 4-12",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18",
  download: "M12 4v12 M6 10l6 6 6-6 M5 20h14",
};

export function icon(name, extra = {}) {
  return s("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 1.8, "stroke-linecap": "round",
    "stroke-linejoin": "round", "aria-hidden": "true", ...extra }, s("path", { d: ICONS[name] || ICONS.info }));
}

// ------------------------------------------------------------------ formatting
export const fmt = {
  int: (v) => (v === null || v === undefined || !Number.isFinite(+v)) ? "—" : Math.round(+v).toLocaleString("en-US"),
  compact: (v) => {
    if (v === null || v === undefined || !Number.isFinite(+v)) return "—";
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1).replace(/\.0$/, "") + "K";
    return String(Math.round(v));
  },
  pct: (v, digits = 0) => (v === null || v === undefined || !Number.isFinite(+v)) ? "—" : (100 * v).toFixed(digits) + "%",
  ratio: (v) => (v === null || v === undefined || !Number.isFinite(+v)) ? "—" : (v >= 10 ? v.toFixed(0) : v.toFixed(1)) + "×",
  date: (iso, opts = { day: "numeric", month: "short", year: "numeric" }) => {
    if (!iso) return "—";
    const d = new Date(iso + "T12:00:00Z");
    return d.toLocaleDateString("en-GB", { ...opts, timeZone: "UTC" });
  },
  longDate: (iso) => fmt.date(iso, { weekday: "long", day: "numeric", month: "long", year: "numeric" }),
  month: (ym) => new Date(ym + "-15T12:00:00Z").toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }),
  rp: (period) => {
    if (period === null || period === undefined || !Number.isFinite(+period)) return "—";
    if (period < 10) return "typical";
    if (period >= 5000) return "1 in 5,000+ days";
    return "1 in " + Math.round(period).toLocaleString("en-US") + " days";
  },
  ago: (isoTime) => {
    const minutes = Math.max(0, Math.round((Date.now() - new Date(isoTime).getTime()) / 60000));
    if (minutes < 2) return "just now";
    if (minutes < 90) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 48) return `${hours} h ago`;
    return `${Math.round(hours / 24)} days ago`;
  },
};

export const TIERS = { 1: "Unusual", 2: "Rare", 3: "Extreme" };

export function tierBadge(tier) {
  if (!tier) return h("span", { class: "pill" }, "Below alarm level");
  return h("span", { class: `tier-badge tier-${tier}` }, h("i"), TIERS[tier]);
}

export function periodFromU(u) {
  return u === null || u === undefined ? null : Math.pow(10, u);
}
