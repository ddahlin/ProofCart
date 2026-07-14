"""/api/reset must restore the exact pinned seed state (APP_SPEC §12)."""

PINNED_USERS = [
    (1, "admin", "admin", False),
    (2, "standard_user", "customer", False),
    (3, "problem_user", "customer", False),
    (4, "locked_out_user", "customer", True),
    (5, "new_customer", "customer", False),
]

PINNED_PRODUCTS = {
    1: ("Penny Sticker", 0.01, 100, True),
    2: ("Flagship Workstation", 9999.99, 3, True),
    3: ("Wireless Mouse", 24.99, 50, True),
    4: ("Mechanical Keyboard", 89.99, 25, True),
    5: ("USB-C Hub", 49.99, 0, True),
    6: ("Monitor Stand", 34.99, 1, True),
    7: ("Desk Lamp", 29.99, 40, True),
    8: ("Laptop Sleeve", 10.00, 60, True),
    9: ("Gaming Headset", 99.99, 30, True),
    10: ("HD Webcam", 59.99, 15, True),
    11: ("Retro Gamepad", 19.99, 5, False),
    12: ("Pocket Notebook", 4.99, 200, True),
}

PINNED_ORDER_STATES = {1: "pending", 2: "paid", 3: "shipped", 4: "cancelled",
                       5: "pending", 6: "paid", 7: "shipped", 8: "paid"}


def test_reset_returns_status_body(api):
    resp = api().post("/api/reset")
    assert resp.status_code == 200
    assert resp.json() == {"status": "reset"}


def test_reset_restores_pinned_state_after_mutations(api, admin, customer):
    # mutate: new user, new product, new order, paid order, deleted report
    admin.post("/api/users", json={"username": "temp_user",
                                   "password": "Temp1234"})
    admin.post("/api/products", json={"name": "Temp", "price": 5.00,
                                      "stock": 5})
    order = customer.post("/api/orders", json={
        "items": [{"product_id": 3, "quantity": 5}]}).json()
    admin.patch(f"/api/orders/{order['id']}/status", json={"status": "paid"})
    admin.delete("/api/reports/1")

    assert api().post("/api/reset").status_code == 200

    users = admin.get("/api/users").json()
    assert [(u["id"], u["username"], u["role"], u["is_locked"])
            for u in users] == PINNED_USERS

    products = admin.get("/api/products?include_inactive=true").json()
    assert {p["id"]: (p["name"], p["price"], p["stock"], p["is_active"])
            for p in products} == PINNED_PRODUCTS

    orders = admin.get("/api/orders").json()
    assert {o["id"]: o["status"] for o in orders} == PINNED_ORDER_STATES

    reports = admin.get("/api/reports").json()
    assert [r["id"] for r in reports] == [1]
    assert reports[0]["type"] == "sales_summary"


def test_seeded_orders_cover_discount_boundary(admin):
    # order 2: subtotal exactly $100.00 -> discounted; order 6: $99.99 -> not
    order2 = admin.get("/api/orders/2").json()
    assert (order2["subtotal"], order2["discount"], order2["total"]) == \
        (100.00, 10.00, 90.00)
    order6 = admin.get("/api/orders/6").json()
    assert (order6["subtotal"], order6["discount"], order6["total"]) == \
        (99.99, 0.00, 99.99)


def test_reset_is_idempotent(api, admin):
    anon = api()
    assert anon.post("/api/reset").status_code == 200
    assert anon.post("/api/reset").status_code == 200
    assert len(admin.get("/api/orders").json()) == 8
