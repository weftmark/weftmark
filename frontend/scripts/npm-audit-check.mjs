#!/usr/bin/env node
/**
 * npm audit gate with a scoped, self-expiring allowlist.
 *
 * Behaves like `npm audit --audit-level=high` (fails on any high/critical
 * finding) EXCEPT for advisories listed in ALLOWLIST below — and even those
 * only stay silenced as long as npm itself reports no safe (non-major) fix
 * available. The moment upstream ships a real forward patch, npm's own
 * `fixAvailable.isSemVerMajor` flips to false and this script starts
 * failing again automatically, even with the ID still listed — so an
 * allowlist entry can't accidentally suppress a fixable vulnerability
 * forever. See #1089.
 *
 * Exception: npm sometimes reports `fixAvailable: true` when no fix can
 * actually be applied (e.g. a parent pins an old major and `npm audit fix`
 * changes nothing). An entry may set `ignoreFixAvailable: true` to keep it
 * suppressed in that case, but then MUST set `recheckBy: "YYYY-MM-DD"`.
 * After that date the entry expires regardless, so it still can't silence
 * an advisory forever — someone has to re-verify and move the date.
 */

import { execSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const ALLOWLIST = {
  "GHSA-qwww-vcr4-c8h2": {
    reason:
      "React Router RSC Mode CSRF Bypass. This app is a standard Vite SPA " +
      "with zero React Server Components usage anywhere in the codebase " +
      "(verified via grep for RSC-only APIs) — the vulnerable code path " +
      "isn't reachable. No non-breaking fix exists yet: npm's suggested " +
      "fix (react-router-dom@7.11.0) would reintroduce 14 other advisories " +
      "already patched in 7.12–7.18, including an unauthenticated RCE " +
      "(GHSA-49rj-9fvp-4h2h). Revisit once a >7.18.1 release fixes this " +
      "without regressing those.",
  },
  "GHSA-mrhx-c7xc-m3w5": {
    // npm reports fixAvailable: true here, but @codecov/bundler-plugin-core
    // 2.0.1 still requires zod ^3, no patched 3.x exists, and `npm audit fix`
    // leaves zod unchanged — the "fix" is not real. See #896.
    ignoreFixAvailable: true,
    recheckBy: "2027-02-15",
    reason:
      "Zod memory exhaustion on oversized constrained collections (fixed in " +
      "zod 4.6.6). zod is a dev-only transitive dependency here: it is " +
      "pulled in by @codecov/bundler-plugin-core, which pins zod ^3.22.4 " +
      "and only uses it to validate its own build-time plugin options. It " +
      "is not imported anywhere in src/ and is never shipped in the bundle, " +
      "so untrusted input can't reach it. No non-breaking fix exists: " +
      "forcing zod 4 would break the codecov plugin. Revisit once " +
      "@codecov/bundler-plugin-core supports zod >=4.6.6.",
  },
  "GHSA-fc5q-39xc-vjpf": {
    reason:
      "picomatch ReDoS via repeated extglobs. No patched release exists " +
      "(affects <=4.0.7, the latest). picomatch is dev-only here, pulled in " +
      "by vite and tinyglobby to match build-config glob patterns that we " +
      "author — no user input reaches it, and it is not in the shipped " +
      "bundle. npm's suggested fix (vite@6.2.7) is a two-major downgrade. " +
      "Expires automatically once a fixed picomatch is published.",
  },
};

const SEVERITY_GATE = ["high", "critical"];

function extractGhsaId(url) {
  const m = /advisories\/(GHSA-[a-z0-9-]+)/i.exec(url ?? "");
  return m ? m[1] : null;
}

export function fixIsSafe(fixAvailable) {
  // true (boolean) => a fix exists with no major-bump flag => safe.
  // object with isSemVerMajor === false => safe, non-breaking fix exists.
  // false, or object with isSemVerMajor === true => no safe fix yet.
  if (fixAvailable === true) return true;
  if (fixAvailable && typeof fixAvailable === "object") {
    return fixAvailable.isSemVerMajor === false;
  }
  return false;
}

/**
 * Decide whether an allowlisted advisory stays suppressed.
 * Returns { suppressed: boolean, reason: string }.
 */
export function evaluateAllowlistEntry(entry, fixAvailable, today = new Date()) {
  if (!entry) return { suppressed: false, reason: "not in allowlist" };
  if (entry.ignoreFixAvailable) {
    if (!entry.recheckBy || !/^\d{4}-\d{2}-\d{2}$/.test(entry.recheckBy)) {
      return { suppressed: false, reason: "ignoreFixAvailable requires a recheckBy date (YYYY-MM-DD)" };
    }
    const todayStr = today.toISOString().slice(0, 10);
    if (todayStr > entry.recheckBy) {
      return { suppressed: false, reason: `recheckBy ${entry.recheckBy} has passed — re-verify and update the entry` };
    }
    return { suppressed: true, reason: "allowlisted (npm fixAvailable ignored until recheckBy)" };
  }
  if (fixIsSafe(fixAvailable)) {
    return { suppressed: false, reason: "a safe fix is now available — allowlist entry expired" };
  }
  return { suppressed: true, reason: "allowlisted, no safe fix yet" };
}

function main() {
let raw;
try {
  raw = execSync("npm audit --json", { encoding: "utf8", maxBuffer: 10 * 1024 * 1024 });
} catch (err) {
  // npm audit exits non-zero when it finds anything — stdout still has the JSON.
  raw = err.stdout?.toString() ?? "";
}

let report;
try {
  report = JSON.parse(raw);
} catch {
  console.error("npm-audit-check: could not parse `npm audit --json` output:");
  console.error(raw);
  process.exit(1);
}

const vulnerabilities = report.vulnerabilities ?? {};
const unresolved = [];

for (const vuln of Object.values(vulnerabilities)) {
  const advisories = (vuln.via ?? []).filter((v) => typeof v === "object");
  for (const advisory of advisories) {
    if (!SEVERITY_GATE.includes(advisory.severity)) continue;

    const ghsaId = extractGhsaId(advisory.url);
    const verdict = evaluateAllowlistEntry(ghsaId ? ALLOWLIST[ghsaId] : undefined, vuln.fixAvailable);

    if (verdict.suppressed) continue;

    unresolved.push({
      package: vuln.name,
      severity: advisory.severity,
      title: advisory.title,
      url: advisory.url,
      ghsaId,
      reasonSkippedAllowlist: verdict.reason,
    });
  }
}

if (unresolved.length > 0) {
  console.error(`npm-audit-check: ${unresolved.length} unresolved high/critical finding(s):\n`);
  for (const f of unresolved) {
    console.error(`  [${f.severity}] ${f.package}: ${f.title}`);
    console.error(`    ${f.url}`);
    console.error(`    reason: ${f.reasonSkippedAllowlist}\n`);
  }
  process.exit(1);
}

const allowedCount = Object.keys(ALLOWLIST).length;
console.log(`npm-audit-check: no unresolved high/critical findings (${allowedCount} allowlisted advisory tracked, still unfixable).`);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main();
}
