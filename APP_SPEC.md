# APP_SPEC.md — "ShopCheck" QA Test-Target Application (Meta-Specification)

> **Audience: Claude Code (the implementing agent).**
> This document is a BUILD INSTRUCTION SET, not a product spec for end users and
> NOT an input document for the QA agent. It defines what to build, in what order,
> and — critically — which imperfections to plant deliberately and preserve.

---

## 0. Purpose and context (read first)

This application is a **test oracle** for a separate project: a "Universal QA AI
Test Artifact Generator" — an LLM agent that reads requirements documents (BRD,
HLD, API specs) and generates requirements analyses, coverage strategies, test
cases, and traceability matrices.

The app you are building exists so that agent can be evaluated against **known
ground truth**. Therefore:

1. Some documents you author here will be **deliberately imperfect** (one vague
   business rule, one cross-document conflict, several planted runtime defects).
   These imperfections are the *point*. **Do not fix, resolve, normalize,
   footnote, or annotate them** in the agent-facing documents.
2. There are three document layers with different audiences. Never mix them:

| Layer | Files | Audience | May reference ground truth? |
|---|---|---|---|
| 1 — Build instructions | `APP_SPEC.md`, `CLAUDE.md` | Claude Code only | Yes |
| 2 — Agent-facing inputs | `docs/BRD.md`, `docs/HLD.md`, `docs/openapi.json`, `docs/product_overview.md` | The QA agent | **NEVER** — no meta-commentary, no hints that anything is intentional |
| 3 — Executable oracle | the app + tests | Generated test cases | n/a |
| Answer key | `GROUND_TRUTH.md` | Human evaluator only | Yes — this IS the ground truth registry |

---

## 1. Mandatory workflow order

Execute in exactly this sequence:

1. **Author `docs/BRD.md`** in stakeholder voice (see §9), satisfying every
   pinned value in this spec.
2. **Author `docs/HLD.md`** in architect voice (see §10).
3. **Freeze both documents.** From this point, if the implementation diverges
   from BRD/HLD, fix the code — never the docs — except where §8 declares a
   divergence to be a deliberate defect.
4. **Implement the application from `docs/BRD.md` + `docs/HLD.md`**, treating
   them as your requirements source, the way a real dev team would.
5. **Export `docs/openapi.json`** from the running FastAPI app
   (`GET /openapi.json`). Endpoint docstrings/response models must be rich
   enough that the exported spec documents all status codes and the positive /
   negative scenarios in §7.
6. **Author `docs/product_overview.md`** (see §11).
7. **Write the pytest suite** (see §12) and make it pass.
8. **Write `Dockerfile` + `.dockerignore`** (see §17).
9. **Author `GROUND_TRUTH.md` last** (see §13), recording exactly what was
   planted and where.

---

## 2. Stack (pinned — do not substitute)

- Python 3.11+, **FastAPI**, **SQLite** (file: `data/shopcheck.db`), SQLAlchemy or
  plain `sqlite3` (your choice), Uvicorn.
- Frontend: **server-rendered Jinja2 templates** + minimal vanilla JS. Single
  process — no separate frontend build, no Node toolchain.
- Auth: **cookie-based server-side sessions** (signed session cookie). No JWT.
- Tests: pytest + httpx/TestClient.
- **Do not** use json-server, Restful-Booker, or any prebuilt mock-API package.
  All endpoints are hand-implemented.

Repository layout:

```
shopcheck/
├── app/
│   ├── main.py            # FastAPI app, routers, session middleware
│   ├── models.py          # DB models
│   ├── auth.py            # session auth, role checks
│   ├── rules.py           # business rules (single source of truth for numbers)
│   ├── defects.py         # deliberate-defect switchboard (§8)
│   ├── seed.py            # deterministic seed data + /api/reset logic
│   ├── routers/           # users.py, products.py, orders.py, reports.py, auth.py
│   └── templates/         # Jinja2 pages
├── tests/
├── docs/                  # Layer-2 agent-facing documents ONLY
│   ├── BRD.md
│   ├── HLD.md
│   ├── openapi.json
│   └── product_overview.md
├── GROUND_TRUTH.md        # answer key — never inside docs/
├── CLAUDE.md
├── APP_SPEC.md
├── Dockerfile
├── .dockerignore
└── requirements.txt
```

---

## 3. Entities and data model (pinned)

### User
| Field | Type | Constraints |
|---|---|---|
| id | int PK | |
| username | str | 3–20 chars, `^[A-Za-z0-9_]+$`, unique |
| password_hash | str | password rule: ≥ 8 chars, at least 1 letter and 1 digit |
| role | enum | `admin` \| `customer` |
| is_locked | bool | locked users cannot log in |
| created_at | datetime | |

### Product
| Field | Type | Constraints |
|---|---|---|
| id | int PK | |
| name | str | 1–100 chars |
| description | str | 0–500 chars |
| price | decimal(2dp) | **$0.01 – $9,999.99** inclusive |
| stock | int | ≥ 0 (never negative) |
| is_active | bool | inactive products hidden from catalog, still readable by admin |

### Order
| Field | Type | Constraints |
|---|---|---|
| id | int PK | |
| user_id | FK → User | |
| status | enum | `pending` \| `paid` \| `shipped` \| `cancelled` |
| line_items | 1..20 items | each: product_id, quantity 1–10, unit_price snapshot |
| subtotal | decimal | sum(qty × unit_price) |
| discount | decimal | per BR-1 |
| total | decimal | subtotal − discount |
| created_at / updated_at | datetime | |

### Report (admin-only)
| Field | Type | Constraints |
|---|---|---|
| id | int PK | |
| title | str | 1–100 chars |
| type | enum | `sales_summary` \| `inventory` |
| date_from / date_to | date | date_from ≤ date_to |
| payload | JSON | computed at creation time from orders/products |
| created_by | FK → User | |
| created_at | datetime | |

---

## 4. Business rules (pinned numbers — copy verbatim into the BRD)

These exact values must appear in `docs/BRD.md` and be implemented in
`app/rules.py`. Do not invent different numbers.

- **BR-1 (order discount):** Orders with subtotal **≥ $100.00** receive a
  **10% discount** on the subtotal. Orders below $100.00 receive no discount.
- **BR-2 (line-item quantity):** Maximum quantity per line item is **10**.
  Violations → `422`.
- **BR-3 (stock protection):** Stock can never go negative. Creating/paying an
  order with insufficient stock → `409` and no partial decrement. Stock is
  decremented when an order transitions `pending → paid`; restored on
  `paid → cancelled`.
- **BR-4 (username):** 3–20 characters, letters/digits/underscore only.
  Violations → `422`.
- **BR-5 (password):** Minimum 8 characters, at least one letter and one digit.
  Violations → `422`.
- **BR-6 (price bounds):** Product price between **$0.01 and $9,999.99**
  inclusive. Violations → `422`.
- **BR-7 (cancellation window):** An order may be cancelled only from `pending`
  or `paid`. Cancelling a `paid` order restores stock.
- **BR-8 (locked accounts):** A locked account cannot log in → `403` with
  message "Account locked". **Credential-vs-lock precedence:** credentials are
  validated first, so `403` is returned **only when the supplied password is
  otherwise valid**; a locked account given an **invalid** password returns
  `401` (invalid credentials), which takes precedence over `403`.
- **BR-9 (reports access):** Reports are admin-only. Any `/api/reports*` access
  by a customer → `403`.
- **BR-10 — DELIBERATELY UNDER-SPECIFIED (BRD only, DO NOT IMPLEMENT):** the
  BRD must contain, verbatim in its Business Rules section:
  > "Loyal customers receive a loyalty discount on their orders."
  No definition of "loyal", no percentage, no interaction with BR-1 — anywhere.
  The application must **not** implement any loyalty discount. Do not add a
  TODO, footnote, or clarification. This vagueness is planted ground truth for
  the QA agent's `core_business_rule_missing` quality signal.

---

## 5. Order state machine (pinned)

Legal transitions — everything else is illegal and returns `409` with body
`{"detail": "Illegal transition <from> -> <to>"}`:

```
pending  → paid        (decrements stock; insufficient stock → 409, stays pending)
pending  → cancelled
paid     → shipped
paid     → cancelled   (restores stock)
shipped  → (terminal)
cancelled→ (terminal)
```

Transitions are performed via `PATCH /api/orders/{id}/status` with body
`{"status": "<target>"}`. Same-state "transitions" (e.g. paid → paid) are also
`409`.

---

## 6. Authentication, sessions, and roles

- `POST /api/auth/login` — body `{username, password}`. Success → `200`, sets
  session cookie. Bad credentials → `401` (takes precedence — an invalid
  password on a locked account still returns `401`). Locked account with an
  otherwise-valid password → `403` (BR-8).
- `POST /api/auth/logout` — `200`, clears session.
- **Session TTL: implement 15 minutes of inactivity** (this matches the HLD;
  see §14 — the BRD will deliberately say something different. Implement the
  HLD value. Do not reconcile the documents.)
- Roles:
  - `admin`: full CRUD on users, products, orders (any user's), reports.
  - `customer`: read active products; create/read/cancel **own** orders only;
    no access to `/api/users` (except `GET /api/users/me`), no reports.
  - Authenticated but wrong role → `403`. Unauthenticated → `401`.
- Protected UI pages (catalog, cart, orders, admin dashboard) redirect
  unauthenticated browsers to `/login`.

---

## 7. REST API surface (pinned) — endpoints, status codes, scenarios

Every endpoint's FastAPI route must declare its response models/`responses=` so
the exported `openapi.json` documents each code below, including at least one
**positive and one negative scenario description** per endpoint (write them
into docstrings — they become the spec text).

| Endpoint | Method | Success | Documented errors |
|---|---|---|---|
| `/api/auth/login` | POST | 200 | 401 bad creds (precedence over 403) · 403 locked (valid creds only) · 422 malformed body |
| `/api/auth/logout` | POST | 200 | 401 no session |
| `/api/users` | GET (admin) | 200 | 401 · 403 non-admin |
| `/api/users` | POST (admin) | 201 | 401 · 403 · 409 duplicate username · 422 BR-4/BR-5 |
| `/api/users/me` | GET | 200 | 401 |
| `/api/users/{id}` | GET/PUT (admin) | 200 | 401 · 403 · 404 · 422 |
| `/api/users/{id}` | DELETE (admin) | 204 | 401 · 403 · 404 · 409 if user has non-terminal orders |
| `/api/products` | GET | 200 | (public list = active only; admin sees all with `?include_inactive=true`) |
| `/api/products` | POST (admin) | 201 | 401 · 403 · 422 BR-6/name bounds |
| `/api/products/{id}` | GET | 200 | 404 (also 404 for inactive product requested by customer) |
| `/api/products/{id}` | PUT (admin) | 200 | 401 · 403 · 404 · 422 |
| `/api/products/{id}` | DELETE (admin) | 204 | 401 · 403 · 404 · 409 if referenced by non-terminal orders |
| `/api/orders` | GET | 200 (customer: own; admin: all) | 401 |
| `/api/orders` | POST | 201 | 401 · 404 unknown product · 409 out-of-stock product at creation · 422 BR-2 / >20 line items / qty < 1 |
| `/api/orders/{id}` | GET | 200 | 401 · 403 not-owner (customer) · 404 |
| `/api/orders/{id}/status` | PATCH | 200 | 401 · 403 (customer may only cancel own order; all other transitions admin-only) · 404 · 409 illegal transition or insufficient stock · 422 unknown status value |
| `/api/reports` | GET/POST (admin) | 200 / 201 | 401 · 403 (BR-9) · 422 bad date range (`date_from > date_to`) |
| `/api/reports/{id}` | GET/DELETE (admin) | 200 / 204 | 401 · 403 · 404 |
| `/api/reset` | POST | 200 `{"status":"reset"}` | — (documented as test-only; no auth required) |

Validation errors use FastAPI's standard `422` shape; business conflicts use
`409` with a human-readable `detail`.

---

## 8. Deliberate defects (pinned — implement exactly, preserve forever)

Defects activate **only** for the `problem_user` session (defects D1–D3) or the
`DEFECT_MODE=1` environment variable (D4). Centralize the switch in
`app/defects.py` so normal behavior is provably clean. **The pytest suite must
assert both the defective behavior (when active) and the correct behavior
(when inactive).** Never document these in any `docs/` file.

- **D1 (calculation defect):** For `problem_user`, order totals for
  **product id 7** use a unit price of **$19.99** instead of its true seeded
  price **$29.99** (subtotal/discount/total all affected; stock and stored
  unit_price snapshot remain correct).
- **D2 (silent-failure defect):** Under `problem_user`… n/a (customer can't
  delete). Instead: `DELETE /api/products/{id}` when `DEFECT_MODE=1` returns
  `204` but **does not delete** the product.
- **D3 (UI defect):** For `problem_user`, the logout button on every page is
  rendered but its request is never sent (JS handler missing) — the session
  persists. API logout still works.
- **D4 (boundary defect):** When `DEFECT_MODE=1`, the BR-1 discount threshold
  is applied at **≥ $99.00** instead of ≥ $100.00 (classic off-by-boundary for
  BVA-generated tests to catch).

---

## 9. `docs/BRD.md` authoring instructions (Layer 2 — agent-facing)

Write as a **business stakeholder** (product manager voice). Requirements are
numbered plain-language statements with acceptance criteria — not developer
notes. Mandatory structure:

1. **Program Overview** — 1–2 paragraphs: what ShopCheck is, who uses it.
2. **In Scope** — bullet summary of functional areas.
3. **Out of Scope** — an explicit section (the QA agent parses for this).
   Must include at least: real payment-gateway integration (payment is
   simulated by the `pending → paid` transition), user self-registration
   (accounts are admin-created), email notifications, shipping-carrier
   integration.
4. **Functional Requirements** — grouped by area (Authentication & Sessions,
   User Management, Product Catalog, Ordering & Order Lifecycle, Reports).
   Each requirement: unique number, statement, 2–4 acceptance criteria.
   Target **22–28 requirements total**; record the final exact count in
   `GROUND_TRUTH.md`.
5. **Business Rules** — BR-1 through BR-9 verbatim values from §4, **plus the
   vague BR-10 sentence exactly as pinned**.
6. **Non-Functional Requirements** — must include: cross-browser support
   (Chrome, Firefox, Edge — "must work correctly on"), page load under
   3 seconds on the catalog, and **"user sessions must expire after
   30 minutes of inactivity"** (yes, 30 — see §14).
7. **Assumptions & Constraints.**

Prohibited in this file: any mention of defects, DEFECT_MODE, problem_user's
special behavior (the account may be listed as a seeded test account by name
only), ground truth, the QA agent, or this spec.

## 10. `docs/HLD.md` authoring instructions (Layer 2 — agent-facing)

Write as a **solution architect**. Structure: system context, component
overview (FastAPI app, Jinja2 UI, SQLite), data model summary (§3 tables),
API design summary (§7 table condensed), authentication & session design —
stating **"server-side sessions with a 15-minute inactivity TTL"** (see §14) —
error-handling conventions (409 vs 422 semantics), and deployment notes
(single Uvicorn process). Same prohibitions as §9.

## 11. `docs/product_overview.md` authoring instructions (KB document)

This file seeds a RAG knowledge base (`kb/product_knowledge/`). Write it as
**durable, factual domain knowledge**, not a requirements doc:

- Self-contained sections of 3–8 sentences each (RAG-chunk friendly; assume any
  section may be retrieved alone): product summary, user roles and permissions,
  catalog & pricing concepts, order lifecycle narrative, reports, seeded test
  accounts (names + roles only, incl. `problem_user` and `locked_out_user`
  described neutrally as "test accounts"), environments & how to run,
  `/api/reset` behavior and seed-data summary.
- Do **not** duplicate the BRD's numbered requirement statements; describe the
  product, not the QA scope. No spoilers (same prohibitions as §9).

## 12. Seed data + `/api/reset` (pinned)

`POST /api/reset` drops and recreates all data to exactly this state
(idempotent, deterministic — fixed IDs):

**Users** (password for all non-admin: `Secret123`; admin: `Admin123`):
| id | username | role | is_locked |
|---|---|---|---|
| 1 | admin | admin | no |
| 2 | standard_user | customer | no |
| 3 | problem_user | customer | no |
| 4 | locked_out_user | customer | **yes** |
| 5 | new_customer | customer | no (zero orders) |

**Products** (12; include these pinned rows, fill the rest sensibly):
| id | name | price | stock | notes |
|---|---|---|---|---|
| 1 | Penny Sticker | **$0.01** | 100 | min-price boundary |
| 2 | Flagship Workstation | **$9,999.99** | 3 | max-price boundary |
| 3 | Wireless Mouse | $24.99 | 50 | |
| 4 | Mechanical Keyboard | $89.99 | 25 | |
| 5 | USB-C Hub | $49.99 | 0 | **out of stock** |
| 6 | Monitor Stand | $34.99 | 1 | stock = 1 |
| 7 | Desk Lamp | **$29.99** | 40 | D1 defect target |
| 8 | Laptop Sleeve | $10.00 | 60 | qty 10 → exactly $100.00 subtotal (BR-1 boundary) |
| 9–12 | (your choice) | varied | varied | one inactive product among them |

**Orders**: 8 orders spread across `standard_user` and `problem_user` covering
every state (≥1 pending, ≥2 paid, ≥2 shipped, ≥1 cancelled), at least one with
subtotal ≥ $100.00 (discount applied) and one just below.

**Reports**: 1 seeded `sales_summary` created by admin.

Pytest and the UI both rely on this reset for determinism.

## 13. `GROUND_TRUTH.md` authoring instructions (answer key — write LAST)

Must record, with file/section references:
1. Final BRD requirement count and the list of requirement IDs/titles.
2. The under-specified rule (BR-10): exact sentence and BRD location; note the
   app implements no loyalty discount.
3. The cross-document conflict (§14): both values, both locations, which one
   the code implements.
4. Every defect D1–D4: trigger condition, expected-per-spec behavior,
   actual defective behavior, and the test(s) covering both sides.
5. Any incidental divergences discovered during implementation (should be none).

## 14. The planted cross-document conflict (pinned)

- `docs/BRD.md` NFR section: sessions expire after **30 minutes** of inactivity.
- `docs/HLD.md` session design: **15-minute** inactivity TTL.
- The application implements **15 minutes**.
- Neither document acknowledges the other. No footnotes, no reconciliation.
  This is planted ground truth for the QA agent's conflict detection.

## 15. Pytest suite (minimum coverage)

- Full order state machine: every legal transition succeeds; a parametrized
  test proves **every** illegal pair returns 409.
- Every endpoint returns each documented status code at least once (401, 403,
  404, 409, 422 paths included).
- BR-1 boundary: subtotal $99.99 → no discount; $100.00 → 10%; BR-2 qty 10 ok /
  11 → 422; BR-3 stock protection incl. restore-on-cancel; BR-4/5/6 validation.
- Defects: each of D1–D4 asserted active under its trigger AND absent otherwise.
- `/api/reset` restores the exact pinned seed state.

## 16. Acceptance criteria (self-verify before finishing)

1. `uvicorn app.main:app` starts clean; UI usable end-to-end (login → catalog →
   cart → order → cancel; admin dashboard for users/products/reports).
2. `pytest -q` fully green.
3. `docs/openapi.json` exported and contains every §7 status code with
   scenario descriptions.
4. `docs/` contains no reference to defects, ground truth, the QA agent, or
   this spec (grep for: defect, DEFECT_MODE, ground truth, GROUND_TRUTH,
   deliberate, planted, APP_SPEC, QA agent).
5. `GROUND_TRUTH.md` complete per §13.
6. BRD/HLD unmodified after implementation began (workflow §1 step 3).
7. `docker build -t shopcheck .` succeeds and
   `docker run -p 8000:8000 shopcheck` serves the app; `POST /api/reset`
   returns 200 inside the container.

## 17. Containerization (pinned)

- `Dockerfile`: base image `python:3.11-slim`; copy code; install
  `requirements.txt`; run `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
  `EXPOSE 8000`. Support `DEFECT_MODE` as a pass-through env var
  (`docker run -e DEFECT_MODE=1 ...` must activate D2/D4).
- **The SQLite database is ephemeral by design** — do NOT declare a volume for
  `data/`. A fresh container plus `/api/reset` is the determinism model; state
  is meant to die with the container.
- `.dockerignore`: exclude `data/`, `__pycache__/`, `.git/`, `tests/`, and
  `GROUND_TRUTH.md` (the answer key must not ship inside the image).
- No docker-compose, no multi-stage build — keep it to the simplest single
  image that satisfies acceptance criterion 7.
