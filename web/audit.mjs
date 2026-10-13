// Vulnerability audit of web/package-lock.json, shared by CI and `make audit`.
//
// Every package here is build tooling, but js-yaml and the fonts are copied into
// the committed assets the image serves. So:
//   - a HIGH or CRITICAL advisory on a package that ships FAILS (exit 1);
//   - any other advisory is a warning, unless it is listed in audit-exceptions.json,
//     where each accepted advisory carries the reason it is accepted;
//   - an exception that npm no longer reports is flagged so it gets removed.
// A plain `npm audit --audit-level=high` would fail on advisories in the build
// toolchain that have no fix and never leave the build machine.
//
// npm audit sends the lockfile's package list to the registry and nothing is
// installed. Network errors are retried; anything else npm prints is a result.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const exceptions = JSON.parse(readFileSync(join(here, "audit-exceptions.json"), "utf8"));
const ships = (name) => name === "js-yaml" || name.startsWith("@fontsource-variable/");
const attempts = 3;

function audit() {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    // npm exits non-zero when it finds advisories, so the exit code says nothing here.
    const run = spawnSync("npm", ["audit", "--json"], { cwd: here, encoding: "utf8" });
    try {
      const report = JSON.parse(run.stdout);
      if (!report.error) return report;
      console.error(`npm audit: ${report.error.summary ?? report.error.code}`);
    } catch {
      console.error(`npm audit: no JSON in the output (${run.stderr.trim().slice(0, 200)})`);
    }
    if (attempt < attempts) {
      console.error(`retrying in ${attempt * 5}s (attempt ${attempt}/${attempts})`);
      spawnSync("sleep", [String(attempt * 5)]);
    }
  }
  console.error("::error::npm audit could not produce a report");
  process.exit(1);
}

const report = audit();
const vulnerabilities = Object.entries(report.vulnerabilities ?? {});

const blocking = vulnerabilities
  .filter(([name, v]) => ships(name) && ["high", "critical"].includes(v.severity))
  .map(([name]) => name);

// The advisories behind the report: entries in `via` that are objects (the rest
// are the names of other vulnerable packages that depend on one).
const advisories = new Map();
for (const [, v] of vulnerabilities) {
  for (const via of v.via) {
    if (typeof via === "object") {
      advisories.set(via.url.split("/").pop(), `${via.name}: ${via.title} (${via.severity})`);
    }
  }
}

for (const [id, summary] of advisories) {
  if (id in exceptions) {
    console.log(`accepted  ${id}  ${summary}\n          ${exceptions[id]}`);
  } else {
    console.log(`::warning::npm audit: new advisory ${id}, ${summary}`);
  }
}
for (const id of Object.keys(exceptions)) {
  if (!advisories.has(id)) {
    console.log(`::warning::${id} is no longer reported by npm audit; remove it from web/audit-exceptions.json`);
  }
}

if (blocking.length > 0) {
  console.log(`::error::HIGH/CRITICAL advisory in a package that ships in the web assets: ${blocking.join(" ")}`);
  spawnSync("npm", ["audit"], { cwd: here, stdio: "inherit" });
  process.exit(1);
}
console.log("✅ No HIGH/CRITICAL advisories in js-yaml or the fonts");
