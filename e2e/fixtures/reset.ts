/**
 * reset_state → the `resetState` fixture: POST /api/reset.
 *
 * Restores the deterministic seed (fixed user/product/order/report ids).
 * It is an AUTO fixture — every test starts from the pinned seed regardless
 * of ordering — and `api` / `loginAs` depend on it explicitly so the reset
 * always happens before any request or session in the same test.
 */
import type { APIRequestContext } from '@playwright/test';

export async function resetState(request: APIRequestContext): Promise<void> {
  const response = await request.post('/api/reset');
  if (!response.ok()) {
    throw new Error(
      `POST /api/reset failed (${response.status()}). Is ShopCheck running at ` +
      `SHOPCHECK_BASE_URL? Start it with: uvicorn app.main:app`,
    );
  }
}
