/**
 * Hybrid + persona-tier smoke — proves Tier 2 works exactly as designed:
 * locked_out_user's credentials are usable for an attempt-and-expect-failure
 * test, while a session fixture for it does not exist and misuse fails fast.
 */
import { expect, test } from '../../fixtures';

test('locked_out_user cannot establish a session (Tier-2 persona)', async ({
  attemptLogin,
  loginAs,
}) => {
  // Attempt sign-in with the locked account's real credentials → refusal.
  const response = await attemptLogin('locked_out_user');
  expect(response.status()).toBe(403);
  const body = (await response.json()) as { detail: string };
  expect(body.detail).toBe('Account locked');

  // Tier enforcement: `login_as:locked_out_user` is not part of the fixture
  // vocabulary. The compiler already rejects it (SessionPersona excludes it);
  // the `as never` cast simulates a generator mistake, which must fail fast
  // with a descriptive error — not a hang or timeout.
  await expect(loginAs('locked_out_user' as never)).rejects.toThrow(
    /locked accounts cannot establish a session/,
  );
});
