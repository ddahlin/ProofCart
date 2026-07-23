#!/usr/bin/env node
/**
 * Deploy gate for the generated Playwright suite (e2e/tests/generated/).
 *
 * Why this exists, not a plain `playwright test` exit code:
 * ShopCheck carries deliberately-planted defects (D1-D4) that CLAUDE.md rule 2
 * forbids ever fixing. A generated spec that asserts CLEAN behavior on a defect
 * path is therefore an INTRINSIC red that will never go green. A strict gate
 * would block every deploy forever. So the gate blocks only on NEW reds -
 * failures not recorded in generated-baseline.json - which are real
 * regressions, while tolerating the pinned intrinsic set.
 *
 * The baseline starts empty, which is identical to a strict gate: with no
 * allowed failures, ANY red blocks the deploy. Once a real run surfaces the
 * intrinsic defect-driven reds, pin exactly those:  `node scripts/check-generated-gate.mjs --update`
 *
 * Reads Playwright's JSON reporter output (test-results/results.json). No deps.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, relative } from 'node:path';

const E2E_DIR = resolve(new URL('..', import.meta.url).pathname);
const RESULTS = resolve(E2E_DIR, 'test-results/results.json');
const BASELINE = resolve(E2E_DIR, 'generated-baseline.json');
const UPDATE = process.argv.includes('--update');

if (!existsSync(RESULTS)) {
  console.error(`::error::gate: ${relative(E2E_DIR, RESULTS)} not found - did the Playwright run produce a JSON report?`);
  process.exit(2);
}

// A stable, human-readable key per spec: "<area>/<file> :: <title>".
const key = (file, title) => `${file} :: ${title}`;

const report = JSON.parse(readFileSync(RESULTS, 'utf8'));
const failing = new Set();
let executed = 0;

const walk = (suite, file) => {
  const f = suite.file ?? file;
  for (const child of suite.suites ?? []) walk(child, f);
  for (const spec of suite.specs ?? []) {
    const statuses = (spec.tests ?? []).flatMap((t) => (t.results ?? []).map((r) => r.status));
    if (statuses.some((s) => s && s !== 'skipped')) executed += 1;
    if (spec.ok === false) failing.add(key(f, spec.title));
  }
};
for (const suite of report.suites ?? []) walk(suite, undefined);

// Guard against a false green: if nothing actually ran (app down, missing
// creds -> every test skipped), that is a broken gate, not a pass.
if (executed === 0) {
  console.error('::error::gate: 0 tests executed (all skipped). App not reachable or credentials unset? Refusing to pass.');
  process.exit(2);
}

const baseline = existsSync(BASELINE)
  ? JSON.parse(readFileSync(BASELINE, 'utf8'))
  : { allowedFailures: [] };
const allowed = new Set(baseline.allowedFailures ?? []);

const failingList = [...failing].sort();

if (UPDATE) {
  writeFileSync(BASELINE, JSON.stringify({ allowedFailures: failingList }, null, 2) + '\n');
  console.log(`gate: baseline updated - ${failingList.length} allowed failure(s) pinned.`);
  process.exit(0);
}

const newReds = failingList.filter((k) => !allowed.has(k));
const fixed = [...allowed].filter((k) => !failing.has(k)).sort();

console.log(`gate: ${executed} executed, ${failing.size} failing, ${allowed.size} allowed (baseline).`);
if (fixed.length) {
  console.log(`::warning::gate: ${fixed.length} baselined failure(s) now pass - prune generated-baseline.json:`);
  for (const k of fixed) console.log(`    (fixed) ${k}`);
}
if (newReds.length) {
  console.error(`::error::gate: ${newReds.length} NEW failure(s) not in baseline - blocking deploy:`);
  for (const k of newReds) console.error(`    (new)   ${k}`);
  process.exit(1);
}
console.log('gate: no new regressions - deploy may proceed.');
process.exit(0);
