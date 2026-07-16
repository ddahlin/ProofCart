/**
 * Resolve UI-model locator specs into Playwright Locators.
 *
 * Policy: page objects always resolve the model's `preferred` tier
 * (getByRole / getByLabel where the model provides them); the `fallback`
 * tier (test ids) stays available in the data but is not the default.
 */
import type { Locator, Page } from '@playwright/test';
import type { ElementModel, LocatorSpec, TemplateModel } from './types';

type AriaRole = Parameters<Page['getByRole']>[0];

function fromSpec(page: Page, spec: LocatorSpec): Locator {
  switch (spec.by) {
    case 'getByRole': {
      const role = spec.role as AriaRole;
      return spec.name !== undefined
        ? page.getByRole(role, { name: spec.name })
        : page.getByRole(role);
    }
    case 'getByLabel':
      return page.getByLabel(spec.value as string);
    case 'getByTestId':
      return page.getByTestId(spec.value as string);
    default:
      throw new Error(`Unknown locator strategy: ${JSON.stringify(spec)}`);
  }
}

/** Resolve an element via the model's preferred locator tier. */
export function locate(page: Page, el: ElementModel): Locator {
  return fromSpec(page, el.preferred);
}

/** Resolve an element via its fallback tier (test id), if one exists. */
export function locateFallback(page: Page, el: ElementModel): Locator {
  return fromSpec(page, el.fallback ?? el.preferred);
}

/**
 * Resolve a per-item element template, substituting `{param}` with a value
 * from the seeded closed set. `closedSet` (when given) enforces that the id
 * is actually part of the deterministic seed, failing fast otherwise.
 */
export function locateTemplate(
  page: Page,
  tmpl: TemplateModel,
  value: number | string,
  closedSet?: readonly (number | string)[],
): Locator {
  if (closedSet && !closedSet.includes(value)) {
    throw new Error(
      `${tmpl.param}=${value} is not in the seeded closed set ` +
      `(${tmpl.paramSource}: ${closedSet.join(', ')}). ` +
      `Seeded ids come from POST /api/reset — re-check the test data.`,
    );
  }
  const fill = (s: string | undefined): string | undefined =>
    s === undefined ? undefined : s.replaceAll(`{${tmpl.param}}`, String(value));
  const spec: LocatorSpec = {
    ...tmpl.preferred,
    value: fill(tmpl.preferred.value),
    name: fill(tmpl.preferred.name),
  };
  return fromSpec(page, spec);
}
