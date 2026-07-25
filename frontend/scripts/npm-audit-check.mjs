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
 */

import { execSync } from "node:child_process";

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
};

const SEVERITY_GATE = ["high", "critical"];

function extractGhsaId(url) {
  const m = /advisories\/(GHSA-[a-z0-9-]+)/i.exec(url ?? "");
  return m ? m[1] : null;
}

function fixIsSafe(fixAvailable) {
  // true (boolean) => a fix exists with no major-bump flag => safe.
  // object with isSemVerMajor === false => safe, non-breaking fix exists.
  // false, or object with isSemVerMajor === true => no safe fix yet.
  if (fixAvailable === true) return true;
  if (fixAvailable && typeof fixAvailable === "object") {
    return fixAvailable.isSemVerMajor === false;
  }
  return false;
}

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
    const allowed = ghsaId && ALLOWLIST[ghsaId];

    if (allowed && !fixIsSafe(vuln.fixAvailable)) {
      continue; // covered by the allowlist, and no safe fix exists yet
    }

    unresolved.push({
      package: vuln.name,
      severity: advisory.severity,
      title: advisory.title,
      url: advisory.url,
      ghsaId,
      reasonSkippedAllowlist: allowed ? "a safe fix is now available — allowlist entry expired" : "not in allowlist",
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
