import pytest


def test_public_list_shows_only_active(api):
    products = api().get("/api/products").json()
    assert len(products) == 11
    assert all(p["is_active"] for p in products)
    assert 11 not in [p["id"] for p in products]


def test_admin_can_include_inactive(admin):
    products = admin.get("/api/products?include_inactive=true").json()
    assert len(products) == 12
    assert any(not p["is_active"] for p in products)


def test_include_inactive_ignored_for_customer(customer):
    products = customer.get("/api/products?include_inactive=true").json()
    assert len(products) == 11


def test_get_product(api):
    body = api().get("/api/products/7").json()
    assert body == {"id": 7, "name": "Desk Lamp",
                    "description": "LED desk lamp with dimmer.",
                    "price": 29.99, "stock": 40, "is_active": True}


def test_get_product_404(api):
    assert api().get("/api/products/999").status_code == 404


def test_inactive_product_404_for_customer_visible_to_admin(customer, admin):
    assert customer.get("/api/products/11").status_code == 404
    assert admin.get("/api/products/11").status_code == 200


def test_create_product(admin, api):
    resp = admin.post("/api/products", json={
        "name": "Cable Organizer", "description": "Desk cable organizer.",
        "price": 12.50, "stock": 10})
    assert resp.status_code == 201
    pid = resp.json()["id"]
    assert api().get(f"/api/products/{pid}").json()["price"] == 12.50


@pytest.mark.parametrize("price", [0.00, 0.001, 10000.00, -5, 9999.999])
def test_create_product_price_out_of_bounds_422(admin, price):
    resp = admin.post("/api/products", json={"name": "X", "price": price,
                                             "stock": 1})
    assert resp.status_code == 422


@pytest.mark.parametrize("price", [0.01, 9999.99])
def test_create_product_price_boundaries_ok(admin, price):
    resp = admin.post("/api/products", json={"name": "Boundary", "price": price,
                                             "stock": 1})
    assert resp.status_code == 201
    assert resp.json()["price"] == price


def test_create_product_name_bounds_422(admin):
    for name in ("", "x" * 101):
        resp = admin.post("/api/products", json={"name": name, "price": 1.00,
                                                 "stock": 1})
        assert resp.status_code == 422


def test_create_product_negative_stock_422(admin):
    resp = admin.post("/api/products", json={"name": "X", "price": 1.00,
                                             "stock": -1})
    assert resp.status_code == 422


def test_create_product_requires_admin(api, customer):
    payload = {"name": "X", "price": 1.00, "stock": 1}
    assert api().post("/api/products", json=payload).status_code == 401
    assert customer.post("/api/products", json=payload).status_code == 403


def test_update_product(admin, api):
    resp = admin.put("/api/products/3", json={
        "name": "Wireless Mouse", "description": "Updated.", "price": 19.99,
        "stock": 45, "is_active": True})
    assert resp.status_code == 200
    assert api().get("/api/products/3").json()["price"] == 19.99


def test_update_product_does_not_change_existing_orders(admin):
    admin.put("/api/products/8", json={
        "name": "Laptop Sleeve", "description": "", "price": 99.99,
        "stock": 60, "is_active": True})
    order = admin.get("/api/orders/2").json()
    assert order["items"][0]["unit_price"] == 10.00
    assert order["subtotal"] == 100.00


def test_update_product_422_and_404(admin):
    good = {"name": "X", "description": "", "price": 1.0, "stock": 1,
            "is_active": True}
    assert admin.put("/api/products/3",
                     json={**good, "price": 10000.00}).status_code == 422
    assert admin.put("/api/products/999", json=good).status_code == 404


def test_update_product_requires_admin(api, customer):
    good = {"name": "X", "description": "", "price": 1.0, "stock": 1,
            "is_active": True}
    assert api().put("/api/products/3", json=good).status_code == 401
    assert customer.put("/api/products/3", json=good).status_code == 403


def test_delete_product_unreferenced(admin):
    assert admin.delete("/api/products/11").status_code == 204
    assert admin.get("/api/products/11").status_code == 404


def test_delete_product_referenced_by_open_order_409(admin):
    # product 3 is on seeded pending order 1
    assert admin.delete("/api/products/3").status_code == 409
    assert admin.get("/api/products/3").status_code == 200


def test_delete_product_404(admin):
    assert admin.delete("/api/products/999").status_code == 404


def test_delete_product_requires_admin(api, customer):
    assert api().delete("/api/products/11").status_code == 401
    assert customer.delete("/api/products/11").status_code == 403
