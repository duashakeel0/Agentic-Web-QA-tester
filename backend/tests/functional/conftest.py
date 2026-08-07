import os

import pytest
from fastapi.testclient import TestClient

os.environ["AUTH_USERNAME"] = "dua"
os.environ["AUTH_PASSWORD"] = "testpass123"

import app.main as main_module  # noqa: E402 - env vars must be set first
from app.history.store import HistoryStore  # noqa: E402


@pytest.fixture
def app_history(tmp_path):
    """Points the app's module-level history store at a fresh temp DB for
    each test, so tests never see another test's rows."""
    store = HistoryStore(db_path=str(tmp_path / "history.db"))
    main_module.history = store
    return store


@pytest.fixture
def client(app_history):
    return TestClient(main_module.app)


@pytest.fixture
def auth_token(client):
    response = client.post("/api/auth/login", json={"username": "dua", "password": "testpass123"})
    assert response.status_code == 200
    return response.json()["token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}
