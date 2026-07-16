/**
 * LoginPage — locators derive from the UI model (locators.generated.ts),
 * never hand-written selectors. Semantic methods only.
 */
import type { Locator, Page } from '@playwright/test';
import { pages } from '../locators.generated';
import { locate } from '../model/resolve';

export class LoginPage {
  readonly model = pages.LoginPage;

  constructor(readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(this.model.path);
  }

  get username(): Locator {
    return locate(this.page, this.model.elements.loginUsername);
  }

  get password(): Locator {
    return locate(this.page, this.model.elements.loginPassword);
  }

  get submit(): Locator {
    return locate(this.page, this.model.elements.loginSubmit);
  }

  /** Inline error banner — conditional: only populated after a failed attempt. */
  get error(): Locator {
    return locate(this.page, this.model.elements.loginError);
  }

  async fillUsername(value: string): Promise<void> {
    await this.username.fill(value);
  }

  async fillPassword(value: string): Promise<void> {
    await this.password.fill(value);
  }

  /** Drive the real UI sign-in flow (fill both fields, click Sign in). */
  async signIn(username: string, password: string): Promise<void> {
    await this.fillUsername(username);
    await this.fillPassword(password);
    await this.submit.click();
  }
}
