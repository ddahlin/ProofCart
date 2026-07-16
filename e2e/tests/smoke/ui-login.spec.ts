/**
 * UI smoke — proves the page-object pathway end-to-end:
 * model-derived locators, the real sign-in flow, and landing assertions.
 * (reset_state runs automatically before the test.)
 */
import { credentialsFor, expect, test } from '../../fixtures';

test('standard_user signs in through the UI and lands on the catalog', async ({
  page,
  loginPage,
  appHeader,
  catalogPage,
}) => {
  const { username, password } = credentialsFor('standard_user');

  await loginPage.goto();
  await loginPage.signIn(username, password);

  // Landing: the catalog page with the shared header nav.
  await expect(page).toHaveURL(/\/catalog$/);
  await expect(appHeader.navOrders).toBeVisible();
  await expect(appHeader.logoutButton).toBeVisible();
  // Product id 1 is part of the deterministic seed (seededProductIds).
  await expect(catalogPage.productCard(1)).toBeVisible();
});
