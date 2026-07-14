import itertools

import pytest

STATES = ("pending", "paid", "shipped", "cancelled")
LEGAL = {("pending", "paid"), ("pending", "cancelled"),
         ("paid", "shipped"), ("paid", "cancelled")}


def make_order(client, items):
    resp = client.post("/api/orders", json={"items": items})
    assert resp.status_code == 201, resp.text
    return resp.json()


def drive_to(admin, order_id, state):
    """Bring a pending order into the requested state via legal moves."""
    path = {"pending": [], "paid": ["paid"], "shipped": ["paid", "shipped"],
            "cancelled": ["cancelled"]}[state]
    for step in path:
        resp = admin.patch(f"/api/orders/{order_id}/status",
                           json={"status": step})
        assert resp.status_code == 200, resp.text


def stock_of(client, product_id):
    return client.get(f"/api/products/{product_id}").json()["stock"]


# ---------------------------------------------------------------------------
# Listing / detail
# ---------------------------------------------------------------------------

def test_customer_sees_only_own_orders(customer):
    orders = customer.get("/api/orders").json()
    assert [o["id"] for o in orders] == [1, 2, 3, 4, 8]
    assert all(o["user_id"] == 2 for o in orders)


def test_admin_sees_all_orders(admin):
    assert len(admin.get("/api/orders").json()) == 8


def test_customer_with_no_orders_sees_empty_list(api):
    assert api("new_customer").get("/api/orders").json() == []


def test_list_orders_requires_auth(api):
    assert api().get("/api/orders").status_code == 401


def test_get_order_owner_and_admin(customer, admin):
    assert customer.get("/api/orders/1").status_code == 200
    assert admin.get("/api/orders/1").status_code == 200


def test_get_order_not_owner_403(api):
    assert api("problem_user").get("/api/orders/1").status_code == 403


def test_get_order_404_and_401(admin, api):
    assert admin.get("/api/orders/999").status_code == 404
    assert api().get("/api/orders/1").status_code == 401


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def test_create_order_snapshots_price_and_computes_totals(customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 2},
                                  {"product_id": 12, "quantity": 1}])
    assert order["status"] == "pending"
    assert order["items"] == [
        {"product_id": 3, "quantity": 2, "unit_price": 24.99},
        {"product_id": 12, "quantity": 1, "unit_price": 4.99}]
    assert order["subtotal"] == 54.97
    assert order["discount"] == 0.0
    assert order["total"] == 54.97


def test_create_order_does_not_touch_stock(customer):
    before = stock_of(customer, 3)
    make_order(customer, [{"product_id": 3, "quantity": 2}])
    assert stock_of(customer, 3) == before


def test_br1_boundary_just_below_no_discount(customer):
    order = make_order(customer, [{"product_id": 9, "quantity": 1}])
    assert order["subtotal"] == 99.99
    assert order["discount"] == 0.0
    assert order["total"] == 99.99


def test_br1_boundary_at_threshold_10_percent(customer):
    order = make_order(customer, [{"product_id": 8, "quantity": 10}])
    assert order["subtotal"] == 100.00
    assert order["discount"] == 10.00
    assert order["total"] == 90.00


def test_br2_quantity_10_ok_11_rejected(customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 10}])
    assert order["items"][0]["quantity"] == 10
    resp = customer.post("/api/orders",
                         json={"items": [{"product_id": 3, "quantity": 11}]})
    assert resp.status_code == 422


def test_create_order_quantity_below_1_422(customer):
    resp = customer.post("/api/orders",
                         json={"items": [{"product_id": 3, "quantity": 0}]})
    assert resp.status_code == 422


def test_create_order_line_item_count_bounds_422(customer):
    resp = customer.post("/api/orders", json={"items": []})
    assert resp.status_code == 422
    too_many = [{"product_id": 3, "quantity": 1}] * 21
    resp = customer.post("/api/orders", json={"items": too_many})
    assert resp.status_code == 422
    order = make_order(customer, [{"product_id": 3, "quantity": 1}] * 20)
    assert len(order["items"]) == 20


def test_create_order_unknown_product_404(customer):
    resp = customer.post("/api/orders",
                         json={"items": [{"product_id": 999, "quantity": 1}]})
    assert resp.status_code == 404


def test_create_order_insufficient_stock_409(customer):
    # product 5 is seeded out of stock; product 6 has stock 1
    for items in ([{"product_id": 5, "quantity": 1}],
                  [{"product_id": 6, "quantity": 2}]):
        resp = customer.post("/api/orders", json={"items": items})
        assert resp.status_code == 409


def test_create_order_requires_auth(api):
    resp = api().post("/api/orders",
                      json={"items": [{"product_id": 3, "quantity": 1}]})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source,target",
                         list(itertools.product(STATES, STATES)))
def test_state_machine_every_pair(admin, customer, source, target):
    order = make_order(customer, [{"product_id": 3, "quantity": 1}])
    drive_to(admin, order["id"], source)
    resp = admin.patch(f"/api/orders/{order['id']}/status",
                       json={"status": target})
    if (source, target) in LEGAL:
        assert resp.status_code == 200
        assert resp.json()["status"] == target
    else:
        assert resp.status_code == 409
        assert resp.json()["detail"] == \
            f"Illegal transition {source} -> {target}"


def test_pay_decrements_stock(admin, customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 4}])
    before = stock_of(admin, 3)
    drive_to(admin, order["id"], "paid")
    assert stock_of(admin, 3) == before - 4


def test_cancel_paid_restores_stock(admin, customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 4}])
    before = stock_of(admin, 3)
    drive_to(admin, order["id"], "paid")
    resp = admin.patch(f"/api/orders/{order['id']}/status",
                       json={"status": "cancelled"})
    assert resp.status_code == 200
    assert stock_of(admin, 3) == before


def test_cancel_pending_changes_no_stock(admin, customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 4}])
    before = stock_of(admin, 3)
    resp = customer.patch(f"/api/orders/{order['id']}/status",
                          json={"status": "cancelled"})
    assert resp.status_code == 200
    assert stock_of(admin, 3) == before


def test_pay_with_insufficient_stock_409_stays_pending(admin, customer):
    # two pending orders for the single unit of product 6
    first = make_order(customer, [{"product_id": 6, "quantity": 1}])
    second = make_order(customer, [{"product_id": 6, "quantity": 1}])
    drive_to(admin, first["id"], "paid")
    assert stock_of(admin, 6) == 0
    resp = admin.patch(f"/api/orders/{second['id']}/status",
                       json={"status": "paid"})
    assert resp.status_code == 409
    assert stock_of(admin, 6) == 0
    assert admin.get(f"/api/orders/{second['id']}").json()["status"] == \
        "pending"


def test_partial_stock_failure_decrements_nothing(admin, customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 1},
                                  {"product_id": 6, "quantity": 1}])
    admin.put("/api/products/6", json={"name": "Monitor Stand",
                                       "description": "", "price": 34.99,
                                       "stock": 0, "is_active": True})
    resp = admin.patch(f"/api/orders/{order['id']}/status",
                       json={"status": "paid"})
    assert resp.status_code == 409
    assert stock_of(admin, 3) == 50  # untouched


def test_customer_can_cancel_own_order(customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 1}])
    resp = customer.patch(f"/api/orders/{order['id']}/status",
                          json={"status": "cancelled"})
    assert resp.status_code == 200


def test_customer_cannot_run_other_transitions_403(customer):
    order = make_order(customer, [{"product_id": 3, "quantity": 1}])
    resp = customer.patch(f"/api/orders/{order['id']}/status",
                          json={"status": "paid"})
    assert resp.status_code == 403


def test_customer_cannot_cancel_others_order_403(api):
    resp = api("problem_user").patch("/api/orders/1/status",
                                     json={"status": "cancelled"})
    assert resp.status_code == 403


def test_status_change_unknown_value_422(admin):
    resp = admin.patch("/api/orders/1/status", json={"status": "refunded"})
    assert resp.status_code == 422


def test_status_change_404_and_401(admin, api):
    assert admin.patch("/api/orders/999/status",
                       json={"status": "paid"}).status_code == 404
    assert api().patch("/api/orders/1/status",
                       json={"status": "paid"}).status_code == 401
