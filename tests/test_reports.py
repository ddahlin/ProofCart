def test_list_reports_admin(admin):
    reports = admin.get("/api/reports").json()
    assert len(reports) == 1
    assert reports[0]["title"] == "January Sales Summary"


def test_reports_forbidden_for_customer(customer):
    assert customer.get("/api/reports").status_code == 403
    assert customer.get("/api/reports/1/detail").status_code == 403
    assert customer.delete("/api/reports/1").status_code == 403
    resp = customer.post("/api/reports", json={
        "title": "X", "type": "inventory",
        "date_from": "2026-01-01", "date_to": "2026-01-31"})
    assert resp.status_code == 403


def test_reports_require_auth(api):
    anon = api()
    assert anon.get("/api/reports").status_code == 401
    assert anon.get("/api/reports/1/detail").status_code == 401
    assert anon.delete("/api/reports/1").status_code == 401
    assert anon.post("/api/reports", json={}).status_code == 401


def test_create_sales_summary(admin):
    resp = admin.post("/api/reports", json={
        "title": "January again", "type": "sales_summary",
        "date_from": "2026-01-01", "date_to": "2026-01-31"})
    assert resp.status_code == 201
    payload = resp.json()["payload"]
    assert payload["orders_total"] == 8
    assert payload["orders_by_status"] == {"pending": 2, "paid": 3,
                                           "shipped": 2, "cancelled": 1}
    assert payload["gross_revenue"] == 320.04


def test_create_inventory_report(admin):
    resp = admin.post("/api/reports", json={
        "title": "Stock now", "type": "inventory",
        "date_from": "2026-02-01", "date_to": "2026-02-01"})
    assert resp.status_code == 201
    payload = resp.json()["payload"]
    assert payload["products_total"] == 12
    assert payload["active_products"] == 11
    assert payload["out_of_stock_product_ids"] == [5]


def test_report_payload_is_snapshot_not_live(admin):
    resp = admin.post("/api/reports", json={
        "title": "Snapshot", "type": "inventory",
        "date_from": "2026-02-01", "date_to": "2026-02-01"})
    report_id = resp.json()["id"]
    admin.put("/api/products/3", json={"name": "Wireless Mouse",
                                       "description": "", "price": 24.99,
                                       "stock": 0, "is_active": True})
    payload = admin.get(f"/api/reports/{report_id}/detail").json()["payload"]
    assert payload["out_of_stock_product_ids"] == [5]


def test_create_report_bad_date_range_422(admin):
    resp = admin.post("/api/reports", json={
        "title": "Backwards", "type": "inventory",
        "date_from": "2026-02-02", "date_to": "2026-02-01"})
    assert resp.status_code == 422


def test_create_report_unknown_type_422(admin):
    resp = admin.post("/api/reports", json={
        "title": "X", "type": "profits",
        "date_from": "2026-01-01", "date_to": "2026-01-31"})
    assert resp.status_code == 422


def test_get_and_delete_report(admin):
    assert admin.get("/api/reports/1/detail").status_code == 200
    assert admin.delete("/api/reports/1").status_code == 204
    assert admin.get("/api/reports/1/detail").status_code == 404
    assert admin.delete("/api/reports/1").status_code == 404
