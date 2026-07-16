/**
 * ShopCheck unified Playwright fixtures (UI + API).
 *
 * FIXTURE-VOCABULARY CONTRACT (frozen — generated specs resolve against it):
 *
 *   steps_structured.target        →  fixture
 *   ─────────────────────────────────────────────────────────────────────
 *   reset_state                    →  `resetState` (auto, per-test:
 *                                     POST /api/reset before EVERY test)
 *   login_as:admin                 →  `loginAs('admin')`
 *   login_as:standard_user         →  `loginAs('standard_user')`
 *   login_as:problem_user          →  `loginAs('problem_user')`
 *
 * By design there is NO login_as for locked_out_user (Tier 2 — use
 * `attemptLogin` and assert the 403) or new_customer (Tier 3 — use
 * `resolveUserId`). Misuse fails fast with a descriptive error.
 *
 * `loginAs` authenticates via POST /api/auth/login on the browser context's
 * own request context, so the session cookie is shared between `page` and
 * `api` — a hybrid test logs in once and drives both surfaces.
 */
import { test as base, expect } from '@playwright/test';
import type { APIRequestContext, APIResponse } from '@playwright/test';
import {
  assertSessionPersona,
  credentialsFor,
  type CredentialPersona,
  type SessionPersona,
} from './auth';
import { resetState } from './reset';
import { AdminDashboardPage } from '../pages/admin.page';
import { AppHeader } from '../pages/app-header';
import { CartPage } from '../pages/cart.page';
import { CatalogPage } from '../pages/catalog.page';
import { LoginPage } from '../pages/login.page';
import { OrdersPage } from '../pages/orders.page';

/** Body of a successful POST /api/auth/login. */
export interface SessionUser {
  id: number;
  username: string;
  role: 'admin' | 'customer';
}

interface ShopCheckFixtures {
  /** reset_state — runs automatically before every test (deterministic seed). */
  resetState: void;
  /** APIRequestContext sharing cookies with `page` (baseURL from config). */
  api: APIRequestContext;
  /** login_as:<persona> — Tier-1 session personas ONLY. */
  loginAs: (persona: SessionPersona) => Promise<SessionUser>;
  /** Attempt a sign-in without asserting success — for Tier-2 refusal tests. */
  attemptLogin: (persona: CredentialPersona) => Promise<APIResponse>;
  /** Resolve a seeded user's id (Tier-3 data targets, e.g. new_customer). */
  resolveUserId: (username: string) => Promise<number>;
  // Page objects (locators derive from the UI model).
  loginPage: LoginPage;
  appHeader: AppHeader;
  catalogPage: CatalogPage;
  cartPage: CartPage;
  ordersPage: OrdersPage;
  adminPage: AdminDashboardPage;
}

export const test = base.extend<ShopCheckFixtures>({
  // Auto fixture: every test starts from the pinned seed. `api` and `loginAs`
  // depend on it explicitly so reset always precedes requests and sessions.
  resetState: [
    async ({ playwright, baseURL }, use) => {
      const ctx = await playwright.request.newContext({ baseURL });
      try {
        await resetState(ctx);
      } finally {
        await ctx.dispose();
      }
      await use(undefined);
    },
    { auto: true },
  ],

  api: async ({ context, resetState: _reset }, use) => {
    // context.request shares the session cookie with the browser context.
    await use(context.request);
  },

  loginAs: async ({ context, resetState: _reset }, use) => {
    await use(async (persona: SessionPersona): Promise<SessionUser> => {
      // Fail fast on Tier-2/Tier-3 misuse (clear error, no hang/timeout).
      assertSessionPersona(persona);
      const response = await context.request.post('/api/auth/login', {
        data: credentialsFor(persona),
      });
      if (response.status() !== 200) {
        const body = await response.text().catch(() => '');
        throw new Error(
          `login_as:${persona} failed with ${response.status()} — expected 200. ` +
          `Check the seeded credentials in e2e/.env. ${body}`,
        );
      }
      return (await response.json()) as SessionUser;
    });
  },

  attemptLogin: async ({ context, resetState: _reset }, use) => {
    await use(async (persona: CredentialPersona): Promise<APIResponse> =>
      context.request.post('/api/auth/login', { data: credentialsFor(persona) }),
    );
  },

  resolveUserId: async ({ playwright, baseURL, resetState: _reset }, use) => {
    await use(async (username: string): Promise<number> => {
      // Throwaway admin request context: resolving an id never disturbs the
      // test's own session.
      const ctx = await playwright.request.newContext({ baseURL });
      try {
        const login = await ctx.post('/api/auth/login', {
          data: credentialsFor('admin'),
        });
        if (login.status() !== 200) {
          throw new Error(
            `resolveUserId: admin login failed (${login.status()}) — check e2e/.env.`,
          );
        }
        const response = await ctx.get('/api/users');
        if (response.status() !== 200) {
          throw new Error(`resolveUserId: GET /api/users returned ${response.status()}.`);
        }
        const users = (await response.json()) as { id: number; username: string }[];
        const found = users.find((u) => u.username === username);
        if (!found) {
          throw new Error(
            `resolveUserId: no user '${username}' in the seeded data ` +
            `(have: ${users.map((u) => u.username).join(', ')}).`,
          );
        }
        return found.id;
      } finally {
        await ctx.dispose();
      }
    });
  },

  loginPage: async ({ page }, use) => use(new LoginPage(page)),
  appHeader: async ({ page }, use) => use(new AppHeader(page)),
  catalogPage: async ({ page }, use) => use(new CatalogPage(page)),
  cartPage: async ({ page }, use) => use(new CartPage(page)),
  ordersPage: async ({ page }, use) => use(new OrdersPage(page)),
  adminPage: async ({ page }, use) => use(new AdminDashboardPage(page)),
});

export { expect };
export { expectJson, expectStatus } from './api';
export {
  credentialsFor,
  ownerOfSeededOrder,
  seededOrdersOwnedBy,
  SEEDED_ORDER_OWNERS,
  SESSION_PERSONAS,
  CREDENTIAL_PERSONAS,
} from './auth';
export type { CredentialPersona, SessionPersona } from './auth';
export { seededOrderIds, seededProductIds, testData } from '../locators.generated';
