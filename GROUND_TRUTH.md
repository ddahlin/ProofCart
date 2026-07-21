# GROUND_TRUTH.md — Answer Key (human evaluator only)

> This file is the ground-truth registry for evaluating the QA artifact
> generator against ShopCheck. It must never appear in `docs/` and is excluded
> from the Docker image via `.dockerignore`.

---

## 1. BRD requirement inventory

**Final count: 26 functional requirements** (target band 22–28), in
`docs/BRD.md` §4, numbered FR-1 … FR-26:

| Area | IDs | Titles |
|---|---|---|
| Authentication & Sessions | FR-1 | Sign in |
| | FR-2 | Sign out |
| | FR-3 | Locked accounts |
| | FR-4 | Access control for anonymous visitors |
| | FR-5 | Role-based permissions |
| User Management | FR-6 | List users |
| | FR-7 | Create user |
| | FR-8 | View and update user |
| | FR-9 | Delete user |
| | FR-10 | Own profile |
| Product Catalog | FR-11 | Browse catalog |
| | FR-12 | Admin catalog view |
| | FR-13 | Product detail |
| | FR-14 | Create product |
| | FR-15 | Update product |
| | FR-16 | Delete product |
| Ordering & Order Lifecycle | FR-17 | Place order |
| | FR-18 | Order pricing |
| | FR-19 | View orders |
| | FR-20 | View order detail |
| | FR-21 | Order status lifecycle |
| | FR-22 | Payment and stock |
| | FR-23 | Cancellation and stock |
| Reports | FR-24 | Create report |
| | FR-25 | View reports |
| | FR-26 | Delete report |

Business rules BR-1 … BR-10 are in `docs/BRD.md` §5; NFR-1 … NFR-5 in §6.

## 2. Under-specified rule (BR-10)

- **Exact sentence:** "Loyal customers receive a loyalty discount on their
  orders."
- **Location:** `docs/BRD.md` §5 (Business Rules), item **BR-10 (loyalty)**.
- "Loyal" is never defined; no percentage is given; no interaction with BR-1
  is specified — anywhere in any Layer-2 document.
- **The application implements no loyalty discount whatsoever.** The only
  discount in the code is BR-1 (`app/rules.py`, `app/models.py::
  discount_cents_for`). This is the planted trigger for the
  `core_business_rule_missing` quality signal.
- **Quality differentiator (bonus signal):** `docs/BRD.md` FR-18 AC2
  references only BR-1 for discounts, quietly contradicting BR-10's
  existence. An agent that cites FR-18 as corroborating evidence when
  flagging BR-10 demonstrates deeper cross-referencing; credit as a
  quality differentiator, no penalty if the flag rests on BR-10 alone.

## 3. Cross-document conflict (session timeout)

| Location | Stated value |
|---|---|
| `docs/BRD.md` §6, **NFR-3** | sessions expire after **30 minutes** of inactivity |
| `docs/HLD.md` §5 (Authentication & Session Design) | server-side sessions with a **15-minute** inactivity TTL |

- **The code implements 15 minutes** (the HLD value):
  `app/rules.py::SESSION_TTL_SECONDS = 15 * 60`, enforced in
  `app/auth.py::get_session`.
- Neither document acknowledges the other; no reconciliation exists anywhere
  in `docs/`.
- Test coverage: `tests/test_auth.py::test_session_expires_after_inactivity_ttl`
  (asserts the constant is 15 min and that an idle session dies) and
  `test_session_survives_activity_within_ttl`.

## 4. Deliberate defects D1–D4

All switching logic is centralized in `app/defects.py`. Seed data is always
clean — defects act only on live requests.

### D1 — calculation defect (order totals for product 7)
- **Trigger:** requests made by a `problem_user` session.
- **Expected per spec/docs:** order totals use the true seeded unit price of
  product 7 (Desk Lamp), **$29.99**.
- **Actual defective behavior:** subtotal/discount/total are computed with
  **$19.99** (`app/defects.py::unit_price_for_totals`, called from
  `app/routers/orders.py::create_order`). The stored `unit_price` snapshot
  and all stock handling remain correct.
- **Tests:** `tests/test_defects.py::test_d1_active_for_problem_user`,
  `test_d1_affects_discount_computation` (defective);
  `test_d1_absent_for_standard_user`, `test_d1_stock_handling_stays_correct`
  (clean side).

### D2 — silent-failure defect (product delete)
- **Trigger:** environment variable `DEFECT_MODE=1`.
- **Expected:** `DELETE /api/products/{id}` returns 204 and removes the
  product.
- **Actual defective behavior:** returns **204 but does not delete**
  (`app/defects.py::suppress_product_delete`, used in
  `app/routers/products.py::delete_product`; the 401/403/404/409 guards
  still run first).
- **Tests:** `tests/test_defects.py::test_d2_active_silent_delete_failure`
  (defective); `test_d2_absent_delete_works` (clean).

### D3 — UI defect (dead logout button)
- **Trigger:** a `problem_user` session, UI pages only.
- **Expected:** the logout button posts to `/api/auth/logout` and ends the
  session.
- **Actual defective behavior:** the button is rendered but its JS handler
  is omitted (`app/defects.py::omit_logout_handler`, consumed in
  `app/templates/base.html`), so clicking it never sends a request and the
  session persists. API logout still works.
- **Tests:** `tests/test_defects.py::
  test_d3_active_logout_handler_missing_for_problem_user` (defective);
  `test_d3_absent_logout_handler_present_for_standard_user`,
  `test_d3_api_logout_still_works_for_problem_user` (clean side).

### D4 — boundary defect (discount threshold)
- **Trigger:** environment variable `DEFECT_MODE=1`.
- **Expected:** BR-1 discount applies at subtotal **≥ $100.00**.
- **Actual defective behavior:** discount applies at **≥ $99.00**
  (`app/defects.py::discount_threshold`, used in
  `app/routers/orders.py::create_order`), so a $99.99 order is wrongly
  discounted — the classic BVA catch.
- **Tests:** `tests/test_defects.py::test_d4_active_discount_below_100`,
  `test_d4_active_still_no_discount_below_99` (defective);
  `test_d4_absent_no_discount_at_9999` (clean); the clean boundary is also
  pinned by `tests/test_orders.py::test_br1_boundary_*`.

## 5. Incidental divergences and secondary findings

BRD and HLD were frozen after authoring and have not been modified since
implementation began. Beyond the deliberate plants (§2–§4), the following
are registered:

### 5.1 Known minor divergence — order_items.product_id FK (docs vs code)

- `docs/HLD.md` §3 (Data Model Summary) labels `product_id` in the
  **order_items** row as **(FK)**.
- The implementation deliberately omits this foreign-key constraint so that
  deleting a product (only possible when it is not referenced by any pending
  or paid order, per FR-16) preserves order history for shipped/cancelled
  orders, as required by FR-15 AC3 and FR-20.
- **Black-box impact: none.** All documented behavior holds; the divergence
  is visible only at the schema level. The QA agent sees only the documents,
  so this cannot affect document-level evaluation. Recorded for honesty of
  the answer key, not as a scoring item.

### 5.2 Known secondary ambiguity — anonymous catalog access (organic, unplanted)

- `docs/BRD.md` FR-4 AC1: an anonymous browser visiting the **catalog** is
  redirected to the sign-in page.
- `docs/BRD.md` FR-11: "**Visitors** of the catalog must see the list of
  active products"; FR-13 AC1: an active product's detail is visible to
  "**any viewer**".
- `docs/HLD.md` §4: `GET /api/products` is **public**.
- These reconcile only if the reader infers a UI-pages-vs-API split that the
  BRD never states. This ambiguity was not planted; it arose organically
  during authoring and the docs are frozen, so it stays.
- **Scoring rule:** if the QA agent flags this as an ambiguity, open
  question, or conflict, **credit it as a legitimate catch**; if it does not,
  **apply no penalty**. It is a bonus signal, not part of the planted
  ground truth (§2–§3).

### 5.3 Implementation choices consistent with the frozen docs (not divergences)

- Products 9–12 seeded as Gaming Headset $99.99/30, HD Webcam $59.99/15,
  Retro Gamepad $19.99/5 (the one inactive product), Pocket Notebook
  $4.99/200.
- `PUT /api/users/{id}` accepts only password/role/is_locked (usernames are
  immutable), keeping its documented status codes exact.

### 5.4 Login credential-vs-lock precedence (FR-3 / BR-8 collision)

- **The one collision BR-8 never explicitly ranked:** a sign-in attempt against
  a **locked account** that **also supplies an invalid password**. FR-3 and BR-8
  state "locked account → `403` (Account locked)" but do not rank `403`-locked
  against `401`-bad-credentials for this case.
- **Answer-key rule (narrow):** credentials are validated **first**, so
  `POST /api/auth/login` returns **`401` (invalid credentials)** whenever the
  password is wrong — *including* on a locked account. `403` "Account locked" is
  reached **only when the password is otherwise valid**. In one line: *401
  (bad credentials) takes precedence; `403`-locked applies only to an
  otherwise-valid login against a locked account.*
- **This is not a broadening to "locked → `401` everywhere."** A locked account
  with the **correct** password still returns `403`, exactly as BR-8 says.
- **Consistent with the app (docs corrected to match behavior, not vice versa):**
  `app/routers/auth.py::login` checks the password before the `is_locked` flag
  (`401` on credential failure, then `403` on lock). No defect, seed, or oracle
  behavior is involved or changed. `docs/openapi.json` (login description) and
  `APP_SPEC.md` (BR-8, §6, §7 endpoint table) encode the same precedence.
