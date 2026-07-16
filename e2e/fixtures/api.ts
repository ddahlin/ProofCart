/**
 * Thin API helpers over Playwright's request contexts.
 *
 * The `api` fixture (see fixtures/index.ts) IS the browser context's own
 * APIRequestContext (`context.request`): it shares the session cookie with
 * the page, so a hybrid test can log in once (API or UI) and then act/assert
 * through either surface. baseURL comes from SHOPCHECK_BASE_URL via
 * playwright.config.ts, so endpoint calls are plain relative paths from
 * docs/openapi.json (e.g. `api.get('/api/products')`).
 *
 * This is intentionally NOT an endpoint-per-method SDK — generated tests call
 * request.get/post/... directly; these helpers only centralize the
 * ergonomics that repeat everywhere.
 */
import type { APIResponse } from '@playwright/test';

/**
 * Assert a response status with a diagnostic message that includes the
 * response body — cleaner failures than expect(resp.status()).toBe(...).
 */
export async function expectStatus(
  response: APIResponse,
  expected: number,
): Promise<APIResponse> {
  if (response.status() !== expected) {
    const body = await response.text().catch(() => '<unreadable body>');
    throw new Error(
      `Expected ${expected} but got ${response.status()} for ${response.url()}\n${body}`,
    );
  }
  return response;
}

/** expectStatus + parsed JSON body in one call. */
export async function expectJson<T = unknown>(
  response: APIResponse,
  expected: number,
): Promise<T> {
  await expectStatus(response, expected);
  return (await response.json()) as T;
}
