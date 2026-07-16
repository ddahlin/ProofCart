/**
 * CatalogPage — locators derive from the UI model. Per-product elements
 * resolve through the model's element templates (`{product_id}` filled from
 * the deterministic seed; `seededProductIds` in locators.generated.ts is the
 * seeded closed set).
 */
import type { Locator, Page } from '@playwright/test';
import { pages } from '../locators.generated';
import { locate, locateTemplate } from '../model/resolve';

export class CatalogPage {
  readonly model = pages.CatalogPage;

  constructor(readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(this.model.path);
  }

  /** Status message line (e.g. "Added to cart"). */
  get message(): Locator {
    return locate(this.page, this.model.elements.catalogMessage);
  }

  productCard(productId: number): Locator {
    return locateTemplate(this.page, this.model.templates.catalogProduct, productId);
  }

  qtyInput(productId: number): Locator {
    return locateTemplate(this.page, this.model.templates.catalogQty, productId);
  }

  addToCartButton(productId: number): Locator {
    return locateTemplate(this.page, this.model.templates.addToCart, productId);
  }

  async addToCart(productId: number, quantity?: number): Promise<void> {
    if (quantity !== undefined) {
      await this.qtyInput(productId).fill(String(quantity));
    }
    await this.addToCartButton(productId).click();
  }
}
