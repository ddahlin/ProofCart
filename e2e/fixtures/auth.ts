/**
 * Persona model — THREE structurally different tiers, not five logins.
 *
 * Tier 1 — session personas (have a `loginAs` fixture): admin, standard_user,
 *          problem_user. They authenticate successfully and establish a
 *          session. problem_user is a seeded test account; the harness treats
 *          it exactly like any other session persona — the app alone decides
 *          how it behaves.
 * Tier 2 — credential-only persona (NO login fixture): locked_out_user.
 *          A locked account cannot have a session — that is the point. Use
 *          the `attemptLogin` fixture and assert the refusal (403).
 * Tier 3 — data-target persona (NO login fixture): new_customer. Only ever
 *          the *object* of operations (e.g. DELETE /api/users/{id}); resolve
 *          its id with the `resolveUserId` fixture. It never logs in.
 *
 * Credentials come from env keys only (see .env.example) — never literals.
 * The username env keys mirror the UI model's test_data.yaml `username_key`s.
 */
import { testData } from '../locators.generated';

export const SESSION_PERSONAS = ['admin', 'standard_user', 'problem_user'] as const;
export type SessionPersona = (typeof SESSION_PERSONAS)[number];

export const CREDENTIAL_PERSONAS = [
  ...SESSION_PERSONAS,
  'locked_out_user',
  'new_customer',
] as const;
export type CredentialPersona = (typeof CREDENTIAL_PERSONAS)[number];

export interface Credentials {
  username: string;
  password: string;
}

/** Username env keys, straight from the UI model's test_data.yaml. */
const USERNAME_KEYS: Record<CredentialPersona, string> = Object.fromEntries(
  CREDENTIAL_PERSONAS.map((p) => [p, testData.users[p].usernameKey]),
) as Record<CredentialPersona, string>;

/** Password env keys mirror the username keys with a _PASSWORD suffix. */
const passwordKey = (persona: CredentialPersona): string =>
  `${USERNAME_KEYS[persona]}_PASSWORD`;

function requireEnv(key: string): string {
  const value = process.env[key];
  if (!value) {
    throw new Error(
      `Missing env var ${key}. Copy e2e/.env.example to e2e/.env and fill in ` +
      `the seeded values (see APP_SPEC §12 / POST /api/reset).`,
    );
  }
  return value;
}

/** Credentials for any persona — including Tier 2, for attempt-and-expect-failure tests. */
export function credentialsFor(persona: CredentialPersona): Credentials {
  return {
    username: requireEnv(USERNAME_KEYS[persona]),
    password: requireEnv(passwordKey(persona)),
  };
}

/** Fail-fast guard behind the `loginAs` fixture. */
export function assertSessionPersona(persona: string): asserts persona is SessionPersona {
  if ((SESSION_PERSONAS as readonly string[]).includes(persona)) return;
  if (persona === 'locked_out_user') {
    throw new Error(
      'login_as:locked_out_user is impossible — locked accounts cannot ' +
      'establish a session. Use the attemptLogin fixture and assert the ' +
      'refusal (403 "Account locked").',
    );
  }
  if (persona === 'new_customer') {
    throw new Error(
      'login_as:new_customer is not part of the fixture vocabulary — ' +
      'new_customer is a data-target persona (the object of operations, ' +
      'never a session). Resolve its id with the resolveUserId fixture.',
    );
  }
  throw new Error(
    `Unknown persona '${persona}'. Session personas: ${SESSION_PERSONAS.join(', ')}.`,
  );
}

/**
 * Seeded order ownership (deterministic, from the app's seed — app/seed.py
 * ORDERS: orders 1–4 and 8 belong to standard_user, 5–7 to problem_user).
 * Both owners are Tier-1 session personas, so the "authenticate as the
 * order's customer" precondition always resolves to a concrete `login_as`
 * target: login_as:ownerOfSeededOrder(id).
 */
export const SEEDED_ORDER_OWNERS: Record<number, SessionPersona> = {
  1: 'standard_user',
  2: 'standard_user',
  3: 'standard_user',
  4: 'standard_user',
  5: 'problem_user',
  6: 'problem_user',
  7: 'problem_user',
  8: 'standard_user',
};

/** The session persona that owns a seeded order — the "order's customer". */
export function ownerOfSeededOrder(orderId: number): SessionPersona {
  const owner = SEEDED_ORDER_OWNERS[orderId];
  if (!owner) {
    throw new Error(
      `Order ${orderId} is not part of the deterministic seed ` +
      `(seeded order ids: ${Object.keys(SEEDED_ORDER_OWNERS).join(', ')}).`,
    );
  }
  return owner;
}

/** All seeded order ids owned by a given session persona. */
export function seededOrdersOwnedBy(persona: SessionPersona): number[] {
  return Object.entries(SEEDED_ORDER_OWNERS)
    .filter(([, owner]) => owner === persona)
    .map(([id]) => Number(id));
}
