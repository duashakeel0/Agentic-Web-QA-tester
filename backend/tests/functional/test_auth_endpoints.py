def test_login_succeeds_with_correct_credentials(client):
    response = client.post("/api/auth/login", json={"username": "dua", "password": "testpass123"})
    assert response.status_code == 200
    assert response.json()["username"] == "dua"
    assert response.json()["token"]


def test_login_fails_with_wrong_password(client):
    response = client.post("/api/auth/login", json={"username": "dua", "password": "wrong"})
    assert response.status_code == 401


def test_protected_route_rejects_missing_token(client):
    response = client.get("/api/history")
    assert response.status_code == 401


def test_protected_route_rejects_garbage_token(client):
    response = client.get("/api/history", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


def test_protected_route_accepts_valid_token(client, auth_headers):
    response = client.get("/api/history", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_logout_invalidates_token(client, auth_headers, auth_token):
    client.post("/api/auth/logout", headers=auth_headers)
    response = client.get("/api/history", headers=auth_headers)
    assert response.status_code == 401


def test_me_endpoint_confirms_authentication(client, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_health_endpoint_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
