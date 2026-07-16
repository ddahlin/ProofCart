/**
 * CartPage — locators derive from the UI model.
 */
import type { Locator, Page } from '@playwright/test';
import { pages } from '../locators.generated';
import { locate } from '../model/resolve';

export class CartPage {
  readonly model = pages.CartPage;

  constructor(readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(this.model.path);
  }

  get table(): Locator {
    return locate(this.page, this.model.elements.cartTable);
  }

  get emptyNotice(): Locator {
    return locate(this.page, this.model.elements.cartEmpty);
  }

  get total(): Locator {
    return locate(this.page, this.model.elements.cartTotal);
  }

  get checkoutButton(): Locator {
    return locate(this.page, this.model.elements.cartCheckout);
  }

  get message(): Locator {
    return locate(this.page, this.model.elements.cartMessage);
  }

  async placeOrder(): Promise<void> {
    await this.checkoutButton.click();
  }
}
