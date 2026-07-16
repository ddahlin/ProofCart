/**
 * AppHeader — the shared top navigation rendered on every authenticated page.
 * Not a page (no route of its own); locators derive from the UI model.
 */
import type { Locator, Page } from '@playwright/test';
import { pages } from '../locators.generated';
import { locate } from '../model/resolve';

export class AppHeader {
  readonly model = pages.AppHeader;

  constructor(readonly page: Page) {}

  get navCatalog(): Locator {
    return locate(this.page, this.model.elements.navCatalog);
  }

  get navCart(): Locator {
    return locate(this.page, this.model.elements.navCart);
  }

  get navOrders(): Locator {
    return locate(this.page, this.model.elements.navOrders);
  }

  /** Admin-only nav link. */
  get navAdmin(): Locator {
    return locate(this.page, this.model.elements.navAdmin);
  }

  get logoutButton(): Locator {
    return locate(this.page, this.model.elements.navLogout);
  }

  async logout(): Promise<void> {
    await this.logoutButton.click();
  }
}
