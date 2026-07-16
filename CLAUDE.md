# CLAUDE.md — Working rules for the ShopCheck repository

ShopCheck is a deliberately imperfect e-commerce app that serves as a **test
oracle** for an external LLM-based QA artifact generator. `APP_SPEC.md` is the
authoritative build instruction set — read it fully before any change.

## Stack (do not substitute)
- Python 3.11+ · FastAPI · SQLite (`data/shopcheck.db`) · Jinja2 server-rendered
  UI · cookie-based server-side sessions · pytest.
- No json-server, no Restful-Booker, no JWT, no separate frontend build.

## Commands
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # run app  → http://localhost:8000
pytest -q                              # full suite must stay green
curl -X POST localhost:8000/api/reset  # restore deterministic seed data
```

## Non-negotiable rules

1. **Document layers are strictly separated.**
   - `APP_SPEC.md`, `CLAUDE.md`, `GROUND_TRUTH.md` → build/evaluation layer.
   - `docs/` (BRD.md, HLD.md, openapi.json, product_overview.md) → agent-facing
     layer. Nothing in `docs/` may ever mention: defects, DEFECT_MODE,
     ground truth, "deliberate", "planted", the QA agent, or APP_SPEC.
     Before committing, grep `docs/` for those terms.

2. **The imperfections are intentional — never fix them.**
   - The vague loyalty-discount sentence in the BRD (BR-10) stays vague and
     stays unimplemented.
   - The BRD-vs-HLD session-timeout conflict (30 min vs 15 min) stays
     unreconciled; the code implements 15 min.
   - Defects D1–D4 (see APP_SPEC §8, GROUND_TRUTH.md) stay in the code,
     switchable only via `problem_user` / `DEFECT_MODE=1`, centralized in
     `app/defects.py`. Tests assert both defective and clean behavior — if a
     "bug fix" turns one of these tests red, the fix is wrong, revert it.

3. **BRD/HLD are frozen after authoring.** If implementation and docs diverge,
   fix the code, not the docs — unless GROUND_TRUTH.md declares the divergence
   a deliberate defect. Any unavoidable doc change requires updating
   GROUND_TRUTH.md (requirement counts, locations) in the same commit.

4. **Business-rule numbers live in one place** — `app/rules.py`. Routes and
   templates import from it; never inline `100.00`, `10`, `0.01`, `9999.99`,
   `15 * 60`, etc. elsewhere. (Exception: `app/defects.py` may override values
   under its trigger conditions — that's its job.)

5. **Determinism.** `/api/reset` must always restore the exact seed state
   pinned in APP_SPEC §12 (fixed IDs, prices, stock, order states). Seed data
   changes are breaking changes: update APP_SPEC §12, GROUND_TRUTH.md, and the
   tests together.

6. **Status-code semantics:** `422` = validation/shape/bounds failures (FastAPI
   default shape); `409` = business conflicts (illegal state transition,
   insufficient stock, duplicate username, delete-blocked-by-references).
   Keep every documented code reachable and covered by a test.

7. **`docs/openapi.json` is exported, never hand-edited.** Regenerate it from
   the running app after any route/docstring change.

8. **The UI-model exporter output is agent-facing.** `tools/export_ui_model.py`
   renders the app and emits a structured UI model (`out/ui_model/shopcheck/*.yaml`)
   that a separate QA pipeline consumes to ground Playwright generation.
   - The **tool** lives in the build/eval layer (`tools/`, alongside APP_SPEC) —
     not agent-facing. Only its **output YAML** is agent-facing and is subject to
     the same rule-1 / APP_SPEC §16.4 leak grep as `docs/`
     (`defect`, `DEFECT_MODE`, `ground truth`, `planted`, `deliberate`, `APP_SPEC`,
     `QA agent`). The exporter builds this grep in as a **hard failure** that
     aborts the export and writes nothing on a hit (the last gate before content
     becomes agent-facing).
   - Always export the **clean state**: `DEFECT_MODE=0`, authenticated only as
     `standard_user`/`admin`, **never `problem_user`** (guarded in code). D1–D4
     never touch the exported structure; exporting clean means no planted
     imperfection is ever encoded. `problem_user`/`locked_out_user` appear in
     `test_data.yaml` by name only, behavior `"test account"` (APP_SPEC §11).
   - It is a **build_artifact**: `_manifest.yaml` is stamped `source_type:
     build_artifact` with the repo's short git `source_sha`; a dirty tree is
     refused (or stamped `-dirty` under `--allow-dirty`). Regenerate on any
     template/route change — the model must not silently drift from the app.
   - `tools/ui_model_routes.yaml` is the one hand-maintained seam (page → route →
     auth/state recipe → conditional-element recipes). The exporter self-validates
     against an embedded copy of the frozen schema; the cross-repo
     `kb_manager.py ui-model validate shopcheck` is the final acceptance check.

## Playwright harness (`e2e/`) — human-authored vs generated boundary

9. **`e2e/` is the human-authored Playwright harness (UI + API); `pytest`
   owns `tests/`, Playwright owns `e2e/` — they never interact.**
   - Machine-generated specs go **only** in `e2e/tests/generated/<area>/` and
     are never hand-edited; everything else under `e2e/` (config, fixtures,
     page objects, smoke specs) is human-authored infrastructure and is never
     machine-edited.
   - The fixture vocabulary (`reset_state`, `login_as:<admin|standard_user|
     problem_user>`) and the three persona tiers documented in `e2e/README.md`
     are a frozen contract with the spec generator — do not rename fixtures or
     add a session fixture for `locked_out_user`/`new_customer`.
   - Locators derive from the UI-model export: never hand-write selectors in
     `e2e/pages/`; after a template/route change re-export the model, then run
     `npm run generate:locators` (commits `e2e/locators.generated.ts`).
   - `workers: 1` / `fullyParallel: false` in `e2e/playwright.config.ts` is a
     hard requirement of the shared SQLite DB + per-test `/api/reset` — never
     parallelize it.
   - Harness changes must keep `pytest -q` fully green and follow rule 4
     (no business-rule literals in fixtures; credentials only via env keys).

## `data-testid` naming convention (for exporter-stable locators)

kebab-case, semantic, page-scoped. Interactive/asserted elements carry a
`data-testid`; the exporter prefers `getByRole`/`getByLabel` (so keep real
`<label for>`/roles/accessible names) and uses the testid as the fallback tier.
Per-item repeated elements embed a **stable seeded id** (APP_SPEC §12) so each
instance is addressable and resolvable against the closed set:

- Singletons, page-scoped: `login-username`, `login-submit`, `login-error`,
  `cart-checkout`, `orders-message`, `admin-create-user`, `nav-logout`.
- Per-item (id from the seed): `add-to-cart-{product_id}`,
  `catalog-qty-{product_id}`, `catalog-product-{product_id}`,
  `order-row-{order_id}`, `order-status-{order_id}`, `order-cancel-{order_id}`.

Adding these attributes must never alter defect behavior (D3: instrument the
logout **button element**; never restore the handler in `base.html` /
`app/defects.py::omit_logout_handler`). After any template edit, `pytest -q`
must stay green and the `docs/` grep must stay clean.
