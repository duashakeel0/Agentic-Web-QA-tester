import app.trello_settings as trello_settings


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(trello_settings, "SETTINGS_PATH", tmp_path / "trello_settings.json")
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)


def test_trello_status_requires_auth(client):
    response = client.get("/api/trello/status")
    assert response.status_code == 401


def test_trello_status_reports_not_connected_by_default(client, auth_headers, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    response = client.get("/api/trello/status", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"connected": False, "source": "none"}


def test_trello_status_reports_env_source_when_only_env_vars_are_set(client, auth_headers, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("TRELLO_API_KEY", "env-key")
    monkeypatch.setenv("TRELLO_TOKEN", "env-token")

    response = client.get("/api/trello/status", headers=auth_headers)

    assert response.json() == {"connected": True, "source": "env"}


def test_save_trello_credentials_requires_auth(client):
    response = client.post("/api/trello/settings", json={"api_key": "k", "token": "t"})
    assert response.status_code == 401


def test_save_trello_credentials_rejects_empty_fields(client, auth_headers, tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    response = client.post("/api/trello/settings", json={"api_key": "  ", "token": "t"}, headers=auth_headers)

    assert response.status_code == 400


def test_save_trello_credentials_then_status_reports_connected_via_settings(
    client, auth_headers, tmp_path, monkeypatch, httpx_mock
):
    _isolate(tmp_path, monkeypatch)
    httpx_mock.add_response(json={"id": "member-1"})

    save_response = client.post(
        "/api/trello/settings", json={"api_key": "real-key", "token": "real-token"}, headers=auth_headers
    )
    status_response = client.get("/api/trello/status", headers=auth_headers)

    assert save_response.status_code == 200
    assert save_response.json() == {"connected": True, "source": "settings"}
    assert status_response.json() == {"connected": True, "source": "settings"}


def test_save_trello_credentials_rejects_credentials_trello_itself_rejects(
    client, auth_headers, tmp_path, monkeypatch, httpx_mock
):
    # Nothing gets saved at all when Trello's own API says these
    # credentials don't work - a typo or a placeholder value must never
    # be accepted and shown as "connected".
    _isolate(tmp_path, monkeypatch)
    httpx_mock.add_response(status_code=401)

    save_response = client.post(
        "/api/trello/settings", json={"api_key": "admin", "token": "admin123"}, headers=auth_headers
    )
    status_response = client.get("/api/trello/status", headers=auth_headers)

    assert save_response.status_code == 400
    assert "rejected" in save_response.json()["detail"]
    assert status_response.json() == {"connected": False, "source": "none"}


def test_save_trello_credentials_response_never_echoes_the_secret_back(
    client, auth_headers, tmp_path, monkeypatch, httpx_mock
):
    # The whole point of not returning the key/token in the response body
    # is that a saved secret should never round-trip back down to the
    # browser/network tab after being submitted.
    _isolate(tmp_path, monkeypatch)
    httpx_mock.add_response(json={"id": "member-1"})

    response = client.post(
        "/api/trello/settings", json={"api_key": "super-secret-key", "token": "super-secret-token"},
        headers=auth_headers,
    )

    assert "super-secret-key" not in response.text
    assert "super-secret-token" not in response.text


def test_disconnect_trello_requires_auth(client):
    response = client.delete("/api/trello/settings")
    assert response.status_code == 401


def test_disconnect_trello_clears_the_connection(client, auth_headers, tmp_path, monkeypatch, httpx_mock):
    _isolate(tmp_path, monkeypatch)
    httpx_mock.add_response(json={"id": "member-1"})
    client.post("/api/trello/settings", json={"api_key": "k", "token": "t"}, headers=auth_headers)

    disconnect_response = client.delete("/api/trello/settings", headers=auth_headers)
    status_response = client.get("/api/trello/status", headers=auth_headers)

    assert disconnect_response.json() == {"connected": False, "source": "none"}
    assert status_response.json() == {"connected": False, "source": "none"}


def test_settings_source_takes_precedence_over_env_when_both_are_present(
    client, auth_headers, tmp_path, monkeypatch, httpx_mock
):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("TRELLO_API_KEY", "env-key")
    monkeypatch.setenv("TRELLO_TOKEN", "env-token")
    httpx_mock.add_response(json={"id": "member-1"})
    client.post("/api/trello/settings", json={"api_key": "settings-key", "token": "settings-token"}, headers=auth_headers)

    response = client.get("/api/trello/status", headers=auth_headers)

    assert response.json() == {"connected": True, "source": "settings"}


def test_disconnect_falls_back_to_env_source_if_env_vars_are_still_set(
    client, auth_headers, tmp_path, monkeypatch, httpx_mock
):
    # Disconnecting removes the dashboard-saved connection specifically -
    # if TRELLO_API_KEY/TRELLO_TOKEN are still set as env vars underneath
    # it, the app falls back to those, same as if the dashboard had never
    # been used at all.
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("TRELLO_API_KEY", "env-key")
    monkeypatch.setenv("TRELLO_TOKEN", "env-token")
    httpx_mock.add_response(json={"id": "member-1"})
    client.post("/api/trello/settings", json={"api_key": "settings-key", "token": "settings-token"}, headers=auth_headers)

    response = client.delete("/api/trello/settings", headers=auth_headers)

    assert response.json() == {"connected": True, "source": "env"}
