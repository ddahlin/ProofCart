/**
 * AdminDashboardPage — locators derive from the UI model. The dashboard has
 * three sections (users / products / reports), each a table plus a create
 * form; the getters below group them the same way.
 */
import type { Locator, Page } from '@playwright/test';
import { pages } from '../locators.generated';
import { locate } from '../model/resolve';

export class AdminDashboardPage {
  readonly model = pages.AdminDashboardPage;

  constructor(readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(this.model.path);
  }

  get message(): Locator {
    return locate(this.page, this.model.elements.adminMessage);
  }

  // --- Users section ---
  get usersTable(): Locator {
    return locate(this.page, this.model.elements.adminUsersTable);
  }

  get newUsername(): Locator {
    return locate(this.page, this.model.elements.adminNewUsername);
  }

  get newPassword(): Locator {
    return locate(this.page, this.model.elements.adminNewPassword);
  }

  get newRole(): Locator {
    return locate(this.page, this.model.elements.adminNewRole);
  }

  get createUserButton(): Locator {
    return locate(this.page, this.model.elements.adminCreateUser);
  }

  // --- Products section ---
  get productsTable(): Locator {
    return locate(this.page, this.model.elements.adminProductsTable);
  }

  get productName(): Locator {
    return locate(this.page, this.model.elements.adminPName);
  }

  get productDescription(): Locator {
    return locate(this.page, this.model.elements.adminPDesc);
  }

  get productPrice(): Locator {
    return locate(this.page, this.model.elements.adminPPrice);
  }

  get productStock(): Locator {
    return locate(this.page, this.model.elements.adminPStock);
  }

  get createProductButton(): Locator {
    return locate(this.page, this.model.elements.adminCreateProduct);
  }

  // --- Reports section ---
  get reportsTable(): Locator {
    return locate(this.page, this.model.elements.adminReportsTable);
  }

  get reportTitle(): Locator {
    return locate(this.page, this.model.elements.adminRTitle);
  }

  get reportType(): Locator {
    return locate(this.page, this.model.elements.adminRType);
  }

  get reportFrom(): Locator {
    return locate(this.page, this.model.elements.adminRFrom);
  }

  get reportTo(): Locator {
    return locate(this.page, this.model.elements.adminRTo);
  }

  get createReportButton(): Locator {
    return locate(this.page, this.model.elements.adminCreateReport);
  }
}
