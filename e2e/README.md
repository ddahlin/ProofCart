# ShopCheck Playwright harness (`e2e/`)

Human-authored test infrastructure for ShopCheck — one **unified Playwright
harness for UI and API** (Playwright's `APIRequestContext` shares the session
cookie with the browser context, so hybrid tests log in once and drive both
surfaces in a single spec, one runner, one report).

- **Human-authored** code lives everywhere under `e2e/` *except*
  `tests/generated/`, which is the write target for machine-generated
  `.spec.ts` files (subfoldered by functional area). Generated specs are never
  hand-edited; the harness is never machine-edited.
- Python's `pytest` owns the repo-root `tests/` directory; Playwright owns
  `e2e/`. The two toolchains do not interact.

## Fixture-vocabulary contract (frozen)

Generated specs carry `steps_structured.target` values that resolve to these
fixtures — names and semantics are a fixed contract:

| `target` string | Fixture | Semantics |
|---|---|---|
| `reset_state` | `resetState` | `POST /api/reset` → deterministic seed. **Auto: runs before every test**, so an explicit `reset_state` step is already satisfied by the harness. |
| `login_as:admin` | `await loginAs('admin')` | Authenticated session (API login; cookie shared by `page` + `api`). |
| `login_as:standard_user` | `await loginAs('standard_user')` | Same. |
| `login_as:problem_user` | `await loginAs('problem_user')` | Same — the harness treats this account like any other; the app defines its behavior. |

Anything else passed to `loginAs` **fails fast** with a descriptive error (and
is a compile error in TS). Import everything from `e2e/fixtures`:

```ts
import { test, expect, expectStatus, credentialsFor, ownerOfSeededOrder } from '../../fixtures';
```

## Persona tiers — three concepts, not five logins

| Tier | Personas | What the harness provides |
|---|---|---|
| 1 — Session | `admin`, `standard_user`, `problem_user` | `loginAs(persona)` → real session. |
| 2 — Credential-only | `locked_out_user` | `credentialsFor('locked_out_user')` + `attemptLogin('locked_out_user')` (returns the raw response — assert the 403 refusal). **No session fixture exists**; `loginAs` rejects it fast. |
| 3 — Data-target | `new_customer` | `resolveUserId('…')` → seeded user id for delete/update targeting. Never logs in; `loginAs` rejects it fast. |

Credentials come **only** from env keys (usernames use the UI model's
`test_data.yaml` `username_key`s; passwords use `<USERNAME_KEY>_PASSWORD`).
Copy `.env.example` → `.env` and fill in the seeded values (APP_SPEC §12 /
`POST /api/reset`).

### "The order's customer" (data-derived persona)

Seeded order ownership is deterministic (from the app seed): **orders 1–4 and
8 belong to `standard_user`; orders 5–7 belong to `problem_user`** — both
Tier-1 personas. So "authenticate as the order's customer" always resolves to
a concrete `login_as` target:

```ts
const owner = ownerOfSeededOrder(2);   // 'standard_user'
await loginAs(owner);
```

`seededOrdersOwnedBy('standard_user')` gives the inverse view.

## Determinism (do not parallelize)

ShopCheck runs on one shared SQLite database. The config pins `workers: 1`,
`fullyParallel: false`, `retries: 0` — parallel workers would stomp each
other's seed mid-test. **Reset is per-test-automatic**: the `resetState` auto
fixture posts `/api/reset` before every test, and `api`/`loginAs` depend on it
so ordering is guaranteed. Every test starts from the pinned seed regardless
of what ran before it.

## Locators live in the UI model — never hand-written

The exported UI model (`out/ui_model/shopcheck/*.yaml`, a `build_artifact`) is
the single source of truth for locators. A build step generates the typed
module the page objects import:

```bash
npm run generate:locators   # reads out/ui_model/shopcheck → locators.generated.ts
```

- Page objects (`pages/*.ts`) expose semantic methods and resolve the model's
  **preferred** locator tier (`getByRole` / `getByLabel`); test ids stay
  available as the fallback tier in the data. No page object contains a
  hand-written selector.
- Per-item elements (product cards, order rows) resolve through the model's
  element templates with ids from the seeded closed set (`seededProductIds`,
  `seededOrderIds`).
- `locators.generated.ts` **is committed** (the `out/` model is gitignored);
  regenerate it after every UI-model re-export so it never drifts.
- Adding a page object: re-run codegen, then mirror any `pages/*.ts` — they
  are thin wrappers over `pages.<PageObject>` from the generated module.

## Reporting — structured, never log-scraped

`playwright.config.ts` configures the `json` reporter to
`test-results/results.json` (plus `list` for humans). Pass/fail is consumed
from the process exit code + that JSON file. Nothing here parses log text or
`eval()`s anything.

## Running

```bash
# terminal 1 — the app (from the repo root)
pip install -r requirements.txt
uvicorn app.main:app                    # http://localhost:8000

# terminal 2 — the harness
cd e2e
npm install
npx playwright install chromium         # first time only
cp .env.example .env                     # fill in seeded values (APP_SPEC §12)
npx playwright test tests/smoke          # 3 hand-written smoke specs
npx playwright test --list               # compile/collect check
npx playwright test                      # smoke + generated suites
```

The smoke specs (`tests/smoke/`) are hand-written proofs of each pathway — UI
(page objects + model locators), API (`api` + auto reset), and the Tier-2
locked-account flow. They live outside `tests/generated/` so the generator
never overwrites them, and they double as reference examples for generated
specs.
