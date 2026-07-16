/**
 * Types for the UI-model-derived locator data (locators.generated.ts).
 *
 * The shapes mirror the exported UI model (out/ui_model/shopcheck/*.yaml),
 * which is the single source of truth for locators. Nothing in the harness
 * hand-writes a selector; page objects resolve these specs via model/resolve.ts.
 */

export type LocatorBy = 'getByRole' | 'getByLabel' | 'getByTestId';

export interface LocatorSpec {
  by: LocatorBy;
  /** Label text (getByLabel) or test id (getByTestId). Templates may contain `{param}` placeholders. */
  value?: string;
  /** ARIA role (getByRole). */
  role?: string;
  /** Accessible name (getByRole). */
  name?: string;
}

export interface ElementModel {
  preferred: LocatorSpec;
  fallback?: LocatorSpec;
  /** Element only present in certain states (e.g. the login error banner). */
  conditional?: boolean;
}

/** Per-item repeated element; `{param}` in the spec is filled from the seeded closed set. */
export interface TemplateModel extends ElementModel {
  param: string;
  paramSource: string;
}

export interface PageModel {
  pageObject: string;
  urlPathKey: string;
  /** Concrete route path (resolved at generation time from tools/ui_model_routes.yaml). */
  path: string;
  description: string;
  shared?: boolean;
  elements: Record<string, ElementModel>;
  templates: Record<string, TemplateModel>;
}

export interface TestDataUser {
  usernameKey: string;
  behavior: string;
}

export interface TestDataModel {
  users: Record<string, TestDataUser>;
  products: readonly { id: number; name: string; slug: string }[];
  orders: readonly { id: number; status: string }[];
}
