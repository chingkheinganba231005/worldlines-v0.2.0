import { fill, fmt, h, tierBadge } from "../lib/dom.js";
import { load } from "../lib/data.js";
import { sparkline } from "../lib/charts.js";

export async function render(page) {
  const index = await load("countries.json");
  const countries = index.countries;
  const continents = [...new Set(countries.map((c) => c.continent).filter(Boolean))].sort();
  const search = h("input", { type: "search", placeholder: "Search a country…", "aria-label": "Search countries", style: { minWidth: "220px", flex: "1" } });
  const continent = h("select", { "aria-label": "Filter by continent" }, h("option", { value: "" }, "All continents"), continents.map((c) => h("option", { value: c }, c)));
  const sort = h("select", { "aria-label": "Sort countries" }, h("option", { value: "today" }, "Most unusual today"),
    h("option", { value: "year" }, "Most alarms in the past year"), h("option", { value: "name" }, "A–Z"), h("option", { value: "size" }, "Most news coverage"));
  const list = h("div", { class: "search-results" });
  const count = h("p", { class: "muted", style: { fontSize: "13.5px", margin: "12px 0 0" } });
  page.append(h("section", { style: { marginTop: "32px" } },
    h("p", { class: "eyebrow" }, `${countries.length} countries monitored`), h("h1", { style: { fontSize: "clamp(28px,3.6vw,42px)" } }, "Every country, compared with itself"),
    h("p", { class: "lead" }, "WORLDLINE monitors every country with enough daily news coverage to judge what is normal for it. The sparkline shows the last 90 days of unusualness; the dotted line marks a 1-in-100-days level."),
    h("div", { class: "controls", style: { marginTop: "22px" } }, search, continent, sort), count, list));
  function draw() {
    const q = search.value.trim().toLowerCase();
    let rows = countries.filter((c) => (!q || c.name.toLowerCase().includes(q) || c.iso3.toLowerCase() === q) && (!continent.value || c.continent === continent.value));
    const key = sort.value;
    rows = rows.slice().sort((a, b) => key === "name" ? a.name.localeCompare(b.name) : key === "year" ? b.alarms_365 - a.alarms_365 || (b.unusualness ?? 0) - (a.unusualness ?? 0)
      : key === "size" ? (b.events || 0) - (a.events || 0) : (b.unusualness ?? -1) - (a.unusualness ?? -1));
    count.textContent = `${rows.length} shown`;
    fill(list, rows.map((c) => h("a", { class: "card flat country-card", href: `#/country/${c.iso3}` },
      h("div", { class: "cc-top" }, h("span", { class: "flag", style: { fontSize: "24px" }, "aria-hidden": "true" }, c.flag),
        h("span", { class: "cc-name" }, c.name), h("span", { style: { marginLeft: "auto" } }, c.tier ? tierBadge(c.tier) : null)),
      h("div", { class: "muted", style: { fontSize: "13px" } }, `${c.continent} · ${c.alarms_365} alarm${c.alarms_365 === 1 ? "" : "s"} in the past year`),
      h("div", { class: "cc-bottom" }, sparkline(c.spark, { width: 150, height: 30, color: c.tier ? `var(--tier-${c.tier})` : "var(--accent)" }),
        h("span", { style: { fontSize: "13px", color: "var(--ink-2)", textAlign: "right" } }, "Today ", h("b", fmt.rp(c.unusualness === null ? null : Math.pow(10, c.unusualness))))))));
    if (!rows.length) fill(list, h("div", { class: "empty" }, "No country matches your search."));
  }
  search.addEventListener("input", draw);
  continent.addEventListener("change", draw);
  sort.addEventListener("change", draw);
  draw();
}
