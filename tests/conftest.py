import os
import tempfile
from contextlib import ExitStack

# Point the app at a throwaway database before it is imported.
os.environ["SHOPCHECK_DB"] = os.path.join(
    tempfile.mkdtemp(prefix="shopcheck-test-"), "shopcheck.db")

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app

PASSWORDS = {"admin": "Admin123"}
DEFAULT_PASSWORD = "Secret123"


@pytest.fixture()
def api():
    """Factory for API clients; state is reset once per test.

    api() -> anonymous client; api('admin') / api('standard_user') ->
    logged-in client for that seeded account.
    """
    with ExitStack() as stack:
        bootstrap = stack.enter_context(TestClient(app))
        assert bootstrap.post("/api/reset").status_code == 200
        auth.clear_all_sessions()

        def make(username=None, password=None):
            client = stack.enter_context(TestClient(app))
            if username is not None:
                pw = password or PASSWORDS.get(username, DEFAULT_PASSWORD)
                resp = client.post("/api/auth/login",
                                   json={"username": username,
                                         "password": pw})
                assert resp.status_code == 200, resp.text
            return client

        yield make


@pytest.fixture()
def admin(api):
    return api("admin")


@pytest.fixture()
def customer(api):
    return api("standard_user")
