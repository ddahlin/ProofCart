"""Each deliberate defect (D1-D4) is asserted both active under its trigger
and absent otherwise. If a "bug fix" turns one of these red, the fix is
wrong."""


# ---------------------------------------------------------------------------
# D1 — problem_user order totals use $19.99 for product 7 (true price $29.99)
# ---------------------------------------------------------------------------

def _order_product7(client, quantity):
    resp = client.post("/api/orders", json={
        "items": [{"product_id": 7, "quantity": quantity}]})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_d1_active_for_problem_user(api):
    order = _order_product7(api("problem_user"), 2)
    assert order["subtotal"] == 39.98          # 2 x 19.99 (defective)
    assert order["total"] == 39.98
    # snapshot stays correct
    assert order["items"][0]["unit_price"] == 29.99


def test_d1_affects_discount_computation(api):
    # 4 x 29.99 = 119.96 would earn a discount; 4 x 19.99 = 79.96 does not
    order = _order_product7(api("problem_user"), 4)
    assert order["subtotal"] == 79.96
    assert order["discount"] == 0.0
    assert order["total"] == 79.96


def test_d1_absent_for_standard_user(customer):
    order = _order_product7(customer, 2)
    assert order["subtotal"] == 59.98          # 2 x 29.99 (correct)
    assert order["items"][0]["unit_price"] == 29.99


def test_d1_stock_handling_stays_correct(api, admin):
    order = _order_product7(api("problem_user"), 2)
    resp = admin.patch(f"/api/orders/{order['id']}/status",
                       json={"status": "paid"})
    assert resp.status_code == 200
    assert admin.get("/api/products/7").json()["stock"] == 38


# ---------------------------------------------------------------------------
# D2 — DEFECT_MODE=1: product delete returns 204 but deletes nothing
# ---------------------------------------------------------------------------

def test_d2_active_silent_delete_failure(admin, monkeypatch):
    monkeypatch.setenv("DEFECT_MODE", "1")
    assert admin.delete("/api/products/11").status_code == 204
    assert admin.get("/api/products/11").status_code == 200  # still there


def test_d2_absent_delete_works(admin, monkeypatch):
    monkeypatch.delenv("DEFECT_MODE", raising=False)
    assert admin.delete("/api/products/11").status_code == 204
    assert admin.get("/api/products/11").status_code == 404


# ---------------------------------------------------------------------------
# D3 — problem_user's UI logout button has no handler; API logout still works
# ---------------------------------------------------------------------------

def test_d3_active_logout_handler_missing_for_problem_user(api):
    page = api("problem_user").get("/catalog").text
    assert 'id="logout-btn"' in page                 # button rendered
    assert "/api/auth/logout" not in page            # handler missing


def test_d3_absent_logout_handler_present_for_standard_user(customer):
    page = customer.get("/catalog").text
    assert 'id="logout-btn"' in page
    assert "/api/auth/logout" in page


def test_d3_api_logout_still_works_for_problem_user(api):
    client = api("problem_user")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/users/me").status_code == 401


# ---------------------------------------------------------------------------
# D4 — DEFECT_MODE=1: BR-1 threshold applied at >= $99.00 instead of $100.00
# ---------------------------------------------------------------------------

def _subtotal_9999(client):
    resp = client.post("/api/orders", json={
        "items": [{"product_id": 9, "quantity": 1}]})   # $99.99
    assert resp.status_code == 201
    return resp.json()


def test_d4_active_discount_below_100(customer, monkeypatch):
    monkeypatch.setenv("DEFECT_MODE", "1")
    order = _subtotal_9999(customer)
    assert order["discount"] == 10.00        # defective: 99.99 >= 99.00
    assert order["total"] == 89.99


def test_d4_active_still_no_discount_below_99(customer, monkeypatch):
    monkeypatch.setenv("DEFECT_MODE", "1")
    resp = customer.post("/api/orders", json={
        "items": [{"product_id": 4, "quantity": 1}]})   # $89.99
    assert resp.json()["discount"] == 0.0


def test_d4_absent_no_discount_at_9999(customer, monkeypatch):
    monkeypatch.delenv("DEFECT_MODE", raising=False)
    order = _subtotal_9999(customer)
    assert order["discount"] == 0.0
    assert order["total"] == 99.99
