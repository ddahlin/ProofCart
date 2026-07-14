import pytest


def test_list_users_admin(admin):
    users = admin.get("/api/users").json()
    assert [u["username"] for u in users] == [
        "admin", "standard_user", "problem_user", "locked_out_user",
        "new_customer"]


def test_list_users_requires_auth(api):
    assert api().get("/api/users").status_code == 401


def test_list_users_forbidden_for_customer(customer):
    assert customer.get("/api/users").status_code == 403


def test_create_user_and_login(admin, api):
    resp = admin.post("/api/users", json={"username": "brand_new",
                                          "password": "Fresh123x",
                                          "role": "customer"})
    assert resp.status_code == 201
    assert resp.json()["username"] == "brand_new"
    assert api("brand_new", "Fresh123x") is not None


def test_create_user_duplicate_username_409(admin):
    resp = admin.post("/api/users", json={"username": "standard_user",
                                          "password": "Valid123x"})
    assert resp.status_code == 409


@pytest.mark.parametrize("username", ["ab", "a" * 21, "bad name", "bad-name",
                                      "bäd", ""])
def test_create_user_invalid_username_422(admin, username):
    resp = admin.post("/api/users", json={"username": username,
                                          "password": "Valid123x"})
    assert resp.status_code == 422


@pytest.mark.parametrize("password", ["Sh0rt", "lettersonly", "12345678", ""])
def test_create_user_invalid_password_422(admin, password):
    resp = admin.post("/api/users", json={"username": "valid_user",
                                          "password": password})
    assert resp.status_code == 422


def test_create_user_forbidden_for_customer(customer):
    resp = customer.post("/api/users", json={"username": "valid_user",
                                             "password": "Valid123x"})
    assert resp.status_code == 403


def test_get_user(admin):
    body = admin.get("/api/users/2").json()
    assert body["username"] == "standard_user"
    assert body["is_locked"] is False


def test_get_user_404(admin):
    assert admin.get("/api/users/999").status_code == 404


def test_get_user_non_integer_id_422(admin):
    assert admin.get("/api/users/abc").status_code == 422


def test_get_user_requires_admin(api, customer):
    assert api().get("/api/users/2").status_code == 401
    assert customer.get("/api/users/2").status_code == 403


def test_update_user_lock_takes_effect(admin, api):
    resp = admin.put("/api/users/2", json={"is_locked": True})
    assert resp.status_code == 200
    assert resp.json()["is_locked"] is True
    login = api().post("/api/auth/login", json={"username": "standard_user",
                                                "password": "Secret123"})
    assert login.status_code == 403


def test_update_user_password(admin, api):
    assert admin.put("/api/users/2",
                     json={"password": "NewPass99"}).status_code == 200
    assert api("standard_user", "NewPass99") is not None


def test_update_user_invalid_password_422(admin):
    resp = admin.put("/api/users/2", json={"password": "short"})
    assert resp.status_code == 422


def test_update_user_404(admin):
    assert admin.put("/api/users/999",
                     json={"is_locked": True}).status_code == 404


def test_update_user_requires_admin(api, customer):
    assert api().put("/api/users/2",
                     json={"is_locked": True}).status_code == 401
    assert customer.put("/api/users/2",
                        json={"is_locked": True}).status_code == 403


def test_delete_user_without_open_orders(admin):
    assert admin.delete("/api/users/5").status_code == 204
    assert admin.get("/api/users/5").status_code == 404


def test_delete_user_with_open_orders_409(admin):
    # standard_user has pending and paid seeded orders
    assert admin.delete("/api/users/2").status_code == 409
    assert admin.get("/api/users/2").status_code == 200


def test_delete_user_404(admin):
    assert admin.delete("/api/users/999").status_code == 404


def test_delete_user_requires_admin(api, customer):
    assert api().delete("/api/users/5").status_code == 401
    assert customer.delete("/api/users/5").status_code == 403
