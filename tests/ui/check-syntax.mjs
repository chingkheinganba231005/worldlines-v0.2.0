// Parse every browser module as an ES module (node --check treats bare .js as CommonJS, which hides syntax errors).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const root = process.argv[2] || "web/assets/js";
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (name.endsWith(".js")) files.push(path);
  }
})(root);

let failed = 0;
for (const file of files) {
  const result = spawnSync(process.execPath, ["--input-type=module", "--check"], { input: readFileSync(file) });
  if (result.status !== 0) {
    failed++;
    console.error(`✗ ${file}\n${result.stderr.toString().trim()}\n`);
  }
}
console.log(`${files.length - failed}/${files.length} modules parse`);
process.exit(failed ? 1 : 0);
