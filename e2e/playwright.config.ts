import { defineConfig } from '@playwright/test';
import * as dotenv from 'dotenv';
import * as path from 'path';

// Load e2e/.env (gitignored). See .env.example for the full key list.
dotenv.config({ path: path.resolve(__dirname, '.env') });

export default defineConfig({
  testDir: './tests',

  // DETERMINISM — DO NOT PARALLELIZE.
  // ShopCheck runs on a single shared SQLite database and every test starts
  // by calling POST /api/reset (the `resetState` auto-fixture). Parallel
  // workers would stomp each other's seed state mid-test and produce flaky
  // cross-contamination. workers:1 / fullyParallel:false is a hard
  // requirement of the shared-DB architecture, not an optimization target.
  fullyParallel: false,
  workers: 1,

  // Retries would mask nondeterminism; the suite is designed to be
  // deterministic from the seed, so a failure must surface as a failure.
  retries: 0,
  forbidOnly: !!process.env.CI,

  // Structured results: pass/fail is consumed programmatically from the exit
  // code + this JSON file — never from scraping log text.
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/results.json' }],
  ],

  use: {
    // Base URL comes from the environment, never a literal in test code.
    baseURL: process.env.SHOPCHECK_BASE_URL ?? 'http://localhost:8000',
    trace: 'on-first-retry',
    // Playwright's default testIdAttribute is `data-testid`, which is what
    // the ShopCheck templates and the exported UI model use.
    testIdAttribute: 'data-testid',
  },

  outputDir: 'test-results/artifacts',
});
