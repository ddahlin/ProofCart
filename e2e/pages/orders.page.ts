/**
 * OrdersPage — locators derive from the UI model. Per-order elements resolve
 * through the model's element templates (`{order_id}` from the seed;
 * `seededOrderIds` in locators.generated.ts is the seeded closed set, and
 * fixtures/auth.ts maps each seeded order to its owning session persona).
 */
import type { Locator, Page } from '@playwright/test';
import { pages } from '../locators.generated';
import { locate, locateTemplate } from '../model/resolve';

export class OrdersPage {
  readonly model = pages.OrdersPage;

  constructor(readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(this.model.path);
  }

  get message(): Locator {
    return locate(this.page, this.model.elements.ordersMessage);
  }

  orderRow(orderId: number): Locator {
    return locateTemplate(this.page, this.model.templates.orderRow, orderId);
  }

  orderStatus(orderId: number): Locator {
    return locateTemplate(this.page, this.model.templates.orderStatus, orderId);
  }

  /** Cancel action — only rendered for orders in a cancellable state. */
  cancelButton(orderId: number): Locator {
    return locateTemplate(this.page, this.model.templates.orderCancel, orderId);
  }

  async cancelOrder(orderId: number): Promise<void> {
    await this.cancelButton(orderId).click();
  }
}
