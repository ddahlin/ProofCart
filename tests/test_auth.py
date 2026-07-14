import time

from app import auth, rules


def test_login_success_sets_session(api):
    client = api()
    resp = client.post("/api/auth/login", json={"username": "standard_user",
                                                "password": "Secret123"})
    assert resp.status_code == 200
    assert resp.json() == {"id": 2, "username": "standard_user",
                           "role": "customer"}
    assert auth.COOKIE_NAME in client.cookies
    assert client.get("/api/users/me").status_code == 200


def test_login_wrong_password_401(api):
    client = api()
    resp = client.post("/api/auth/login", json={"username": "standard_user",
                                                "password": "WrongPass1"})
    assert resp.status_code == 401


def test_login_unknown_user_401(api):
    client = api()
    resp = client.post("/api/auth/login", json={"username": "nobody",
                                                "password": "Secret123"})
    assert resp.status_code == 401


def test_login_locked_account_403(api):
    client = api()
    resp = client.post("/api/auth/login", json={"username": "locked_out_user",
                                                "password": "Secret123"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Account locked"


def test_login_malformed_body_422(api):
    client = api()
    assert client.post("/api/auth/login",
                       json={"username": "admin"}).status_code == 422


def test_logout_ends_session(customer):
    assert customer.post("/api/auth/logout").status_code == 200
    assert customer.get("/api/users/me").status_code == 401


def test_logout_without_session_401(api):
    assert api().post("/api/auth/logout").status_code == 401


def test_me_returns_profile(customer):
    body = customer.get("/api/users/me").json()
    assert body["username"] == "standard_user"
    assert body["role"] == "customer"


def test_me_unauthenticated_401(api):
    assert api().get("/api/users/me").status_code == 401


def test_session_expires_after_inactivity_ttl(customer):
    assert rules.SESSION_TTL_SECONDS == 15 * 60
    for session in auth._sessions.values():
        session["last_activity"] = \
            time.time() - (rules.SESSION_TTL_SECONDS + 1)
    assert customer.get("/api/users/me").status_code == 401


def test_session_survives_activity_within_ttl(customer):
    for session in auth._sessions.values():
        session["last_activity"] = \
            time.time() - (rules.SESSION_TTL_SECONDS - 10)
    assert customer.get("/api/users/me").status_code == 200


def test_ui_pages_redirect_anonymous_to_login(api):
    client = api()
    for page in ("/catalog", "/cart", "/orders", "/admin"):
        resp = client.get(page, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"


def test_ui_pages_render_for_user(customer):
    for page in ("/catalog", "/cart", "/orders"):
        resp = customer.get(page)
        assert resp.status_code == 200
        assert "ShopCheck" in resp.text
