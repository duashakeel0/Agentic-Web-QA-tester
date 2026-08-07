from app.domains import manifest
from app.domains.schema import ExpectedOutcome, Workflow


def _isolate_domains(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DATA_DIR", tmp_path)


def test_list_domains_returns_the_registered_manifest(client, auth_headers, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)
    manifest.save_workflow(
        "my_site", "https://example.com",
        Workflow(name="login", steps=["Log in"], expected_outcome=ExpectedOutcome(text_contains="Welcome")),
    )

    response = client.get("/api/domains", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "my_site"


def test_add_domain_knowledge_creates_a_new_domain(client, auth_headers, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)

    response = client.post(
        "/api/domains",
        headers=auth_headers,
        json={
            "domain": "My New Site",
            "base_url": "https://example.com",
            "workflow": {
                "name": "Check Something",
                "steps": ["Navigate to /x", "Click the button"],
                "text_contains": "Success",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "my_new_site"
    assert body["workflows"][0]["name"] == "check_something"
    assert body["workflows"][0]["expected_outcome"]["text_contains"] == "Success"

    # Immediately visible to a fresh load - no restart needed.
    domains = manifest.load_domains()
    assert domains[0].name == "my_new_site"


def test_add_domain_knowledge_appends_to_existing_domain(client, auth_headers, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)
    manifest.save_workflow(
        "my_site", "https://example.com",
        Workflow(name="login", steps=["Log in"], expected_outcome=ExpectedOutcome(text_contains="Welcome")),
    )

    response = client.post(
        "/api/domains",
        headers=auth_headers,
        json={"domain": "my_site", "workflow": {"name": "checkout", "steps": ["Check out"], "text_contains": "Order placed"}},
    )

    assert response.status_code == 200
    domains = manifest.load_domains()
    assert len(domains) == 1
    assert {w.name for w in domains[0].workflows} == {"login", "checkout"}


def test_add_domain_knowledge_rejects_missing_expected_outcome(client, auth_headers, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)

    response = client.post(
        "/api/domains",
        headers=auth_headers,
        json={
            "domain": "my_site", "base_url": "https://example.com",
            "workflow": {"name": "login", "steps": ["Log in"]},
        },
    )

    assert response.status_code == 400
    assert "url_contains" in response.json()["detail"] or "text_contains" in response.json()["detail"]


def test_add_domain_knowledge_rejects_empty_steps(client, auth_headers, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)

    response = client.post(
        "/api/domains",
        headers=auth_headers,
        json={
            "domain": "my_site", "base_url": "https://example.com",
            "workflow": {"name": "login", "steps": ["", "   "], "text_contains": "Welcome"},
        },
    )

    assert response.status_code == 400


def test_add_domain_knowledge_requires_base_url_for_a_new_domain(client, auth_headers, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)

    response = client.post(
        "/api/domains",
        headers=auth_headers,
        json={"domain": "brand_new_site", "workflow": {"name": "login", "steps": ["Log in"], "text_contains": "Welcome"}},
    )

    assert response.status_code == 400
    assert "base_url" in response.json()["detail"]


def test_add_domain_knowledge_requires_auth(client, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)

    response = client.post(
        "/api/domains",
        json={"domain": "my_site", "base_url": "https://example.com", "workflow": {"name": "login", "steps": ["Log in"], "text_contains": "Welcome"}},
    )

    assert response.status_code == 401
