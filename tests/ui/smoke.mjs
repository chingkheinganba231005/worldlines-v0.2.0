// Headless smoke test of the built site: every page renders, without errors, unreadable values or sideways scrolling.
//   node tests/ui/smoke.mjs _site [--shots dir]
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, normalize, resolve } from "node:path";
import { createRequire } from "node:module";

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch {
    return createRequire(import.meta.url)(process.env.PLAYWRIGHT_PATH || "playwright");
  }
}

const site = resolve(process.argv[2] || "_site");
const shotsAt = process.argv.indexOf("--shots");
const shots = shotsAt > 0 ? resolve(process.argv[shotsAt + 1]) : null;
if (shots) mkdirSync(shots, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".xml": "application/xml", ".gz": "application/gzip", ".png": "image/png" };

const server = createServer((req, res) => {
  const path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^([/\\])+/, "");
  let file = join(site, path);
  if (!file.startsWith(site)) { res.writeHead(403).end(); return; }
  if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
  if (!existsSync(file)) { res.writeHead(404).end(); return; }
  res.writeHead(200, { "content-type": types[extname(file)] || "application/octet-stream" }).end(readFileSync(file));
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const base = `http://127.0.0.1:${server.address().port}/`;

const latest = JSON.parse(readFileSync(join(site, "data/latest.json"), "utf8"));
const country = (latest.alarms[0] || latest.watchlist[0]).iso3;
const routes = ["", "map", "countries", `country/${country}`, "worldlines", "lab", "record", "method"];
const viewports = [{ width: 390, height: 844, scheme: "light" }, { width: 1280, height: 900, scheme: "dark" }];
const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const problems = [];

for (const vp of viewports) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, colorScheme: vp.scheme });
  for (const route of routes) {
    const page = await context.newPage();
    const errors = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("requestfailed", (r) => errors.push(`requestfailed: ${r.url()}`));
    await page.goto(`${base}#/${route}`, { waitUntil: "networkidle" });
    await page.waitForSelector("#main .page h1", { timeout: 15000 }).catch(() => errors.push("no page heading rendered"));
    const check = await page.evaluate(() => {
      const text = document.querySelector("main")?.innerText || document.body.innerText;
      return {
        failed: text.includes("Something went wrong"),
        bad: (text.match(/\b(NaN|undefined|null|Infinity)\b/g) || []).slice(0, 5),
        overflow: document.documentElement.scrollWidth - window.innerWidth,
        charts: document.querySelectorAll("svg").length,
        words: text.split(/\s+/).length,
      };
    });
    const label = `${route || "today"} @${vp.width} ${vp.scheme}`;
    if (errors.length) problems.push(`${label}: ${errors.join(" | ")}`);
    if (check.failed) problems.push(`${label}: the page shows its error message`);
    if (check.bad.length) problems.push(`${label}: unreadable values on page: ${check.bad.join(", ")}`);
    if (check.overflow > 1) problems.push(`${label}: page scrolls sideways by ${check.overflow}px`);
    if (check.words < 40) problems.push(`${label}: page looks empty (${check.words} words)`);
    if (shots) await page.screenshot({ path: join(shots, `${(route || "today").replace("/", "_")}_${vp.width}_${vp.scheme}.png`), fullPage: true });
    const ok = !errors.length && !check.failed && !check.bad.length && check.overflow <= 1 && check.words >= 40;
    console.log(`${ok ? "✓" : "✗"} ${label}  (${check.charts} svg, ${check.words} words)`);
    await page.close();
  }
  await context.close();
}
await browser.close();
server.close();
if (problems.length) {
  console.error(`\n${problems.length} problem(s):\n- ${problems.join("\n- ")}`);
  process.exit(1);
}
console.log("\nAll pages render cleanly.");
