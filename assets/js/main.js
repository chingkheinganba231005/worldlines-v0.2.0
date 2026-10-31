import { clear, fmt, h } from "./lib/dom.js";
import { load } from "./lib/data.js";
import { hideTooltip } from "./lib/charts.js";

const routes = {
  today: () => import("./pages/today.js"),
  map: () => import("./pages/map.js"),
  countries: () => import("./pages/countries.js"),
  country: () => import("./pages/country.js"),
  worldlines: () => import("./pages/worldlines.js"),
  lab: () => import("./pages/lab.js"),
  record: () => import("./pages/record.js"),
  method: () => import("./pages/method.js"),
};

function parse() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  const name = parts[0] && routes[parts[0]] ? parts[0] : "today";
  return { name, args: parts.slice(1), query: new URLSearchParams(query) };
}

let renderToken = 0;

async function render() {
  const route = parse();
  const token = ++renderToken;
  hideTooltip();
  document.querySelectorAll(".nav a").forEach((a) => {
    const current = a.dataset.route === route.name || (route.name === "country" && a.dataset.route === "countries");
    if (current) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const main = document.getElementById("main");
  try {
    const module = await routes[route.name]();
    if (token !== renderToken) return;
    const page = h("div", { class: "page" });
    clear(main).append(page);
    await module.render(page, route);
    if (token !== renderToken) return;
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  } catch (error) {
    if (token !== renderToken) return;
    console.error(error);
    clear(main).append(h("div", { class: "empty", style: { marginTop: "40px" } },
      h("h2", "Something went wrong loading this page."), h("p", String(error.message || error)),
      h("p", h("a", { href: "#/" }, "Back to today"))));
  }
}

function setupTheme() {
  const button = document.getElementById("theme-toggle");
  const current = () => document.documentElement.dataset.theme ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  button.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("worldline-theme", next); } catch (e) { /* storage may be unavailable */ }
    window.dispatchEvent(new Event("themechange"));
  });
}

async function setupLive() {
  const pill = document.getElementById("live-pill");
  const text = pill.querySelector(".live-text");
  try {
    const meta = await load("meta.json");
    const age = (Date.now() - new Date(meta.generated_at).getTime()) / 36e5;
    text.textContent = age < 3 ? `Live · updated ${fmt.ago(meta.generated_at)}` : `Updated ${fmt.ago(meta.generated_at)}`;
    pill.classList.toggle("stale", age >= 3);
    pill.title = `Data through ${fmt.longDate(meta.data_as_of)} (UTC). Built ${new Date(meta.generated_at).toUTCString()}.`;
    const info = document.getElementById("build-info");
    if (info && meta.build && meta.build.commit) info.textContent = `Build ${String(meta.build.commit).slice(0, 7)} · data to ${meta.data_as_of}`;
    else if (info) info.textContent = `Data to ${meta.data_as_of}`;
  } catch {
    text.textContent = "Offline";
    pill.classList.add("stale");
  }
}

window.addEventListener("hashchange", render);
let resizeTimer = null;
let lastWidth = window.innerWidth;
window.addEventListener("resize", () => {
  if (Math.abs(window.innerWidth - lastWidth) < 40) return;
  lastWidth = window.innerWidth;
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => window.dispatchEvent(new Event("relayout")), 250);
});
setupTheme();
setupLive();
render();
