import assert from "node:assert/strict";
import { test } from "node:test";

import { evaluateAllowlistEntry } from "./npm-audit-check.mjs";

const day = (s) => new Date(`${s}T12:00:00Z`);

test("not allowlisted -> not suppressed", () => {
  assert.equal(evaluateAllowlistEntry(undefined, false).suppressed, false);
});

test("plain entry: suppressed while no safe fix", () => {
  assert.equal(evaluateAllowlistEntry({ reason: "x" }, false).suppressed, true);
  assert.equal(evaluateAllowlistEntry({ reason: "x" }, { isSemVerMajor: true }).suppressed, true);
});

test("plain entry: expires once npm reports a safe fix", () => {
  assert.equal(evaluateAllowlistEntry({ reason: "x" }, true).suppressed, false);
  assert.equal(evaluateAllowlistEntry({ reason: "x" }, { isSemVerMajor: false }).suppressed, false);
});

test("ignoreFixAvailable: suppressed despite fixAvailable until recheckBy (inclusive)", () => {
  const e = { reason: "x", ignoreFixAvailable: true, recheckBy: "2027-02-15" };
  assert.equal(evaluateAllowlistEntry(e, true, day("2026-11-17")).suppressed, true);
  assert.equal(evaluateAllowlistEntry(e, true, day("2027-02-15")).suppressed, true);
});

test("ignoreFixAvailable: expires after recheckBy", () => {
  const e = { reason: "x", ignoreFixAvailable: true, recheckBy: "2027-02-15" };
  const v = evaluateAllowlistEntry(e, false, day("2027-02-16"));
  assert.equal(v.suppressed, false);
  assert.match(v.reason, /recheckBy 2027-02-15 has passed/);
});

test("ignoreFixAvailable without a valid recheckBy is rejected", () => {
  for (const recheckBy of [undefined, "", "Feb 2027", "2027-2-15"]) {
    const v = evaluateAllowlistEntry({ reason: "x", ignoreFixAvailable: true, recheckBy }, false, day("2026-11-17"));
    assert.equal(v.suppressed, false, String(recheckBy));
    assert.match(v.reason, /requires a recheckBy/);
  }
});
