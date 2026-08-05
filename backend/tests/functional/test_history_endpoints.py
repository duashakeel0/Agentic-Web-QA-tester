from app.agents.schema import PipelineResult, RunMetrics, TestPlan, VerifierResult


def _result(ticket_id, provider, verdict, cost=0.01):
    return PipelineResult(
        ticket_id=ticket_id, provider=provider,
        plan=TestPlan(ticket_id=ticket_id, matched=True, domain="sauce_demo", workflow="login", steps=["a"]),
        verification=VerifierResult(
            ticket_id=ticket_id, domain="sauce_demo", workflow="login", verdict=verdict,
            assertion_checked={}, initial_check_passed=(verdict == "pass"), retried=False,
        ),
        metrics=RunMetrics(
            steps_planned=1, steps_covered=1, coverage_ratio=1.0, actions_attempted=1, actions_succeeded=1,
            accuracy_ratio=1.0, llm_call_count=3, input_tokens=100, output_tokens=20, estimated_cost_usd=cost,
        ),
        started_at=0.0, finished_at=0.5, total_duration_ms=500.0,
    )


async def test_list_history_returns_seeded_runs(client, auth_headers, app_history):
    await app_history.record_run(_result("T1", "claude", "pass"))
    await app_history.record_run(_result("T2", "ollama", "fail"))

    response = client.get("/api/history", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["ticket_id"] == "T2"  # newest first


async def test_history_search_filters(client, auth_headers, app_history):
    await app_history.record_run(_result("ALPHA-1", "claude", "pass"))
    await app_history.record_run(_result("BETA-1", "claude", "pass"))

    response = client.get("/api/history?search=ALPHA", headers=auth_headers)

    assert [r["ticket_id"] for r in response.json()] == ["ALPHA-1"]


async def test_get_single_run_detail(client, auth_headers, app_history):
    run_id = await app_history.record_run(_result("T1", "claude", "pass"))

    response = client.get(f"/api/history/{run_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["result"]["ticket_id"] == "T1"


def test_get_missing_run_returns_404(client, auth_headers):
    response = client.get("/api/history/999", headers=auth_headers)
    assert response.status_code == 404


async def test_stats_endpoint(client, auth_headers, app_history):
    await app_history.record_run(_result("T1", "claude", "pass", cost=0.01))
    await app_history.record_run(_result("T2", "claude", "fail", cost=0.02))

    response = client.get("/api/history/stats", headers=auth_headers)

    body = response.json()
    assert body["total_runs"] == 2
    assert body["passed"] == 1
    assert body["failed"] == 1
    assert body["total_cost_usd"] == 0.03


async def test_provider_stats_endpoint(client, auth_headers, app_history):
    await app_history.record_run(_result("T1", "claude", "pass"))
    await app_history.record_run(_result("T2", "ollama", "fail"))

    response = client.get("/api/history/provider-stats", headers=auth_headers)

    providers = {p["provider"] for p in response.json()}
    assert providers == {"claude", "ollama"}


async def test_daily_endpoint(client, auth_headers, app_history):
    await app_history.record_run(_result("T1", "claude", "pass"))

    response = client.get("/api/history/daily?days=7", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()[0]["total"] == 1


async def test_comparison_endpoint(client, auth_headers, app_history):
    group = app_history.new_comparison_group()
    await app_history.record_run(_result("T1", "claude", "pass"), group)
    from app.agents.schema import ComparisonReport

    await app_history.record_comparison(
        ComparisonReport(ticket_id="T1", faster_provider="claude", summary="Claude won."), group
    )

    response = client.get(f"/api/history/comparisons/{group}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["comparison"]["faster_provider"] == "claude"


def test_comparison_endpoint_404_when_missing(client, auth_headers):
    response = client.get("/api/history/comparisons/nonexistent", headers=auth_headers)
    assert response.status_code == 404


def test_history_routes_require_auth(client):
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/history/stats").status_code == 401
    assert client.get("/api/history/provider-stats").status_code == 401
    assert client.get("/api/history/daily").status_code == 401
    assert client.get("/api/history/1").status_code == 401
