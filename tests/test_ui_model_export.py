"""Tests for the UI-model instrumentation + exporter (tools/export_ui_model.py).

These test the *tooling and instrumentation*, not the app's business logic, and
must not disturb the existing suite. The exporter drives the same in-process app
(via TestClient) that conftest points at a throwaway DB.
"""
import re
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import auth, defects
from app.main import app
from tools import export_ui_model as X

ROUTES = yaml.safe_load(
    (Path(X.__file__).parent / "ui_model_routes.yaml").read_text(encoding="utf-8"))


def _authed(username, password):
    c = TestClient(app)
    assert c.post("/api/auth/login",
                  json={"username": username, "password": password}).status_code == 200
    return c


@pytest.fixture()
def seeded():
    with TestClient(app) as boot:
        assert boot.post("/api/reset").status_code == 200
        auth.clear_all_sessions()
        yield


# 1 — Instrumentation smoke: expected testids/roles/labels render per page.
def test_1_instrumentation_smoke(seeded):
    su = _authed("standard_user", "Secret123")
    ad = _authed("admin", "Admin123")

    login = TestClient(app).get("/login").text
    for t in ("login-username", "login-password", "login-submit", "login-error"):
        assert f'data-testid="{t}"' in login
    assert 'for="username"' in login and 'for="password"' in login

    catalog = su.get("/catalog").text
    for t in ("catalog-product-7", "catalog-qty-7", "add-to-cart-7", "catalog-message"):
        assert f'data-testid="{t}"' in catalog
    # Inactive product 11 is filtered out of the catalog.
    assert 'data-testid="add-to-cart-11"' not in catalog

    orders = su.get("/orders").text
    for t in ("order-row-1", "order-status-1", "order-cancel-1", "orders-message"):
        assert f'data-testid="{t}"' in orders

    cart = su.get("/cart").text
    for t in ("cart-table", "cart-total", "cart-checkout", "cart-message"):
        assert f'data-testid="{t}"' in cart

    admin = ad.get("/admin").text
    for t in ("admin-users-table", "admin-new-username", "admin-create-user",
              "admin-p-price", "admin-r-from", "admin-message"):
        assert f'data-testid="{t}"' in admin
    assert 'for="new-username"' in admin  # A2: real label association

    header = ad.get("/catalog").text  # shared nav rendered on every authed page
    for t in ("nav-catalog", "nav-cart", "nav-orders", "nav-admin", "nav-logout"):
        assert f'data-testid="{t}"' in header


# 2 — Login error banner is conditional and role-addressable (POST-bad-creds recipe).
def test_2_login_error_conditional_and_role_addressable(seeded):
    c = TestClient(app)
    assert c.post("/api/auth/login",
                  json={"username": "no_such_user", "password": "wrongpass9"}).status_code == 401
    html = c.get("/login").text
    assert 'role="alert"' in html
    assert 'data-testid="login-error"' in html

    # And the exported LoginPage marks it conditional.
    login_page = X.build_model(allow_dirty=True)[1]["LoginPage"]
    assert login_page["elements"]["login_error"]["conditional"] is True
    assert login_page["elements"]["login_error"]["preferred"] == {"by": "getByRole", "role": "alert"}


# 3 — Exporter produces schema-valid YAML with a non-empty source_sha + 12 products.
def test_3_exporter_produces_valid_yaml(seeded, tmp_path):
    summary = X.export(tmp_path / "out", allow_dirty=True)
    app_dir = tmp_path / "out" / "ui_model" / "shopcheck"

    manifest = yaml.safe_load((app_dir / "_manifest.yaml").read_text())
    assert manifest["source_type"] == "build_artifact"
    assert manifest["source_sha"]  # non-empty
    assert manifest["app_id"] == "shopcheck"

    # One page file per manifest page.
    page_files = {p.name for p in app_dir.glob("*_page.yaml")}
    assert len(page_files) == len(ROUTES["pages"]) == summary["pages"]
    for page in ROUTES["pages"]:
        expected = X._page_filename(page["page_object"])
        assert expected in page_files

    test_data = yaml.safe_load((app_dir / "test_data.yaml").read_text())
    assert len(test_data["products"]) == 12
    assert {p["id"] for p in test_data["products"]} == set(range(1, 13))
    # Personas neutral.
    for persona in test_data["users"].values():
        assert persona["behavior"] == "test account"


# 4 — Leak grep is enforced (hard fail, writes no output).
def test_4a_leak_scan_detects_terms():
    assert X.leak_scan("this mentions a DEFECT here")
    assert X.leak_scan("see APP_SPEC for ground truth")
    assert X.leak_scan("clean neutral description") == []


def test_4b_export_aborts_on_leak_and_writes_nothing(seeded, tmp_path, monkeypatch):
    real_build = X.build_model

    def leaking_build(allow_dirty):
        manifest, pages, td, ent, gaps = real_build(allow_dirty)
        # Inject a forbidden term as if a template leaked it.
        pages["LoginPage"]["description"] += " (references APP_SPEC internals)"
        return manifest, pages, td, ent, gaps

    monkeypatch.setattr(X, "build_model", leaking_build)
    out = tmp_path / "out"
    with pytest.raises(X.ExportError, match="LEAK GREP FAILED"):
        X.export(out, allow_dirty=True)
    # Nothing written.
    assert not (out / "ui_model" / "shopcheck").exists()


# 5 — DEFECT_MODE guard: refuse to run.
def test_5_defect_mode_guard(seeded, tmp_path, monkeypatch):
    monkeypatch.setenv("DEFECT_MODE", "1")
    with pytest.raises(X.ExportError, match="DEFECT_MODE"):
        X.export(tmp_path / "out", allow_dirty=True)
    assert not (tmp_path / "out").exists()


# 6 — standard_user/admin only, never problem_user.
def test_6a_no_recipe_uses_problem_user():
    for page in ROUTES["pages"]:
        auth_role = (page.get("recipe") or {}).get("auth")
        assert auth_role in (None, "anonymous", "standard_user", "admin")
        assert auth_role != "problem_user"


def test_6b_login_helper_refuses_problem_user():
    with pytest.raises(X.ExportError, match="problem_user"):
        X._login(TestClient(app), "problem_user")


# 7 — Closed `by:` enum only; no CSS/XPath ever emitted.
def test_7_closed_enum_only(seeded, tmp_path):
    X.export(tmp_path / "out", allow_dirty=True)
    app_dir = tmp_path / "out" / "ui_model" / "shopcheck"
    forbidden_by = re.compile(r"getBy(Css|XPath)|\blocator\b", re.IGNORECASE)

    def check(loc):
        assert loc["by"] in X.LOCATOR_METHODS, loc
        for v in loc.values():
            if isinstance(v, str):
                # No CSS/XPath syntax leaking into locator values.
                assert "//" not in v
                assert not re.search(r"[>~]|::|\[[^{]*=", v), v

    for pf in app_dir.glob("*_page.yaml"):
        text = pf.read_text()
        assert not forbidden_by.search(text), pf.name
        page = yaml.safe_load(text)
        for edef in (page.get("elements") or {}).values():
            check(edef["preferred"])
            if edef.get("fallback"):
                check(edef["fallback"])
        for tdef in (page.get("element_templates") or {}).values():
            check(tdef["preferred"])
            if tdef.get("fallback"):
                check(tdef["fallback"])


# 9 — Drift guard: the rendered model must match the committed reference snapshot.
def test_9_model_matches_committed_reference(seeded):
    assert X.REFERENCE_FILE.exists(), (
        "missing tools/ui_model_reference.yaml — generate it with "
        "`python tools/export_ui_model.py --write-reference`")
    manifest, pages, td, _ent, _gaps = X.build_model(allow_dirty=True)
    current = X.structural_view(manifest, pages, td)
    reference = yaml.safe_load(X.REFERENCE_FILE.read_text())
    assert current == reference, (
        "UI model drifted from the committed reference — a template/route change was "
        "not re-exported. If the change is intended, regenerate and commit:\n"
        "    python tools/export_ui_model.py --write-reference\n"
        "    python tools/export_ui_model.py --dest <qa_repo>/kb/product_knowledge/ui_model")


# 8 — Existing defect logic is untouched by instrumentation (D1–D4 intact).
def test_8_defects_untouched_by_instrumentation():
    assert defects.D1_PRODUCT_ID == 7
    assert defects.D1_WRONG_UNIT_PRICE == Decimal("19.99")
    assert defects.D4_WRONG_THRESHOLD == Decimal("99.00")
    # D3 still keys off problem_user only; instrumenting the button element
    # (data-testid) did not restore/remove the handler-omission switch.
    assert defects.omit_logout_handler("problem_user") is True
    assert defects.omit_logout_handler("standard_user") is False
