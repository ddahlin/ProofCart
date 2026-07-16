/**
 * API smoke — proves the API pathway: the automatic reset_state fixture plus
 * plain request calls against openapi.json paths through the `api` helper.
 */
import { expect, expectJson, test, testData } from '../../fixtures';

interface Product {
  id: number;
  name: string;
  is_active: boolean;
}

test('after reset, GET /api/products returns the seeded active catalog', async ({
  api,
}) => {
  // resetState already ran (auto fixture) — the seed is pinned.
  const products = await expectJson<Product[]>(await api.get('/api/products'), 200);

  // The seed contains 12 products, one of which is inactive; the public
  // list shows active products only (APP_SPEC §12 seed via POST /api/reset).
  expect(testData.products).toHaveLength(12);
  expect(products).toHaveLength(11);
  expect(products.every((p) => p.is_active)).toBe(true);

  // Spot-check a seeded row by id from the model's closed set.
  const pennySticker = products.find((p) => p.id === testData.products[0].id);
  expect(pennySticker?.name).toBe(testData.products[0].name);
});
