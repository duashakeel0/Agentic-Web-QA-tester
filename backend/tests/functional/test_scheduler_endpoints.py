import app.main as main_module
import app.scheduler as scheduler_module
from app.domains import manifest
from app.domains.schema import ExpectedOutcome, Workflow


def _isolate_domains(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DATA_DIR", tmp_path)
    monkeypatch.setattr(scheduler_module, "load_domains", manifest.load_domains)


def test_scheduler_status_requires_auth(client):
    response = client.get("/api/scheduler/status")
    assert response.status_code == 401


def test_scheduler_status_lists_only_smoke_flagged_workflows(client, auth_headers, tmp_path, monkeypatch):
    _isolate_domains(tmp_path, monkeypatch)
    manifest.save_workflow(
        "my_site", "https://example.com",
        Workflow(name="login", steps=["Log in"], expected_outcome=ExpectedOutcome(text_contains="Welcome"), smoke=True),
    )
    manifest.save_workflow(
        "my_site", "https://example.com",
        Workflow(name="checkout", steps=["Check out"], expected_outcome=ExpectedOutcome(text_contains="Order placed")),
    )

    response = client.get("/api/scheduler/status", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["smoke_workflows"] == [{"domain": "my_site", "workflow": "login"}]
    assert isinstance(body["interval_minutes"], int)
    assert body["last_cycle"] is None


def test_scheduler_run_now_requires_auth(client):
    response = client.post("/api/scheduler/run-now")
    assert response.status_code == 401


def test_scheduler_run_now_triggers_a_cycle_and_updates_status(client, auth_headers, app_history, tmp_path, monkeypatch):
    # A functional/API-level test shouldn't launch a real Playwright
    # browser - that's what tests/e2e/test_scheduler_real_browser.py is
    # for. Here only run_plan is faked, same as the scheduler unit tests,
    # to prove the endpoint itself is wired correctly end to end.
    #
    # smoke_scheduler is a module-level singleton constructed once with
    # the app's *original* history store, so the app_history fixture
    # rebinding main_module.history to a fresh per-test DB doesn't reach
    # it on its own - point it at the same isolated store the rest of
    # this test (and the /api/history assertion below) uses.
    monkeypatch.setattr(main_module.smoke_scheduler, "_history", app_history)
    _isolate_domains(tmp_path, monkeypatch)
    manifest.save_workflow(
        "my_site", "https://example.com",
        Workflow(name="login", steps=["Log in"], expected_outcome=ExpectedOutcome(text_contains="Welcome"), smoke=True),
    )

    from app.agents.schema import PipelineResult, VerifierResult

    async def fake_run_plan(plan, provider, on_event=None):
        return PipelineResult(
            ticket_id=plan.ticket_id, provider=provider, plan=plan,
            verification=VerifierResult(
                ticket_id=plan.ticket_id, domain=plan.domain, workflow=plan.workflow, verdict="pass",
                assertion_checked=plan.expected_outcome or {}, initial_check_passed=True, retried=False,
            ),
            started_at=0.0, finished_at=1.0, total_duration_ms=1000.0,
        )

    monkeypatch.setattr(scheduler_module, "run_plan", fake_run_plan)

    response = client.post("/api/scheduler/run-now", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["triggered_by"] == "on_demand"
    assert body["pass_count"] == 1
    assert body["fail_count"] == 0
    assert len(body["run_ids"]) == 1

    status = client.get("/api/scheduler/status", headers=auth_headers).json()
    assert status["last_cycle"]["triggered_by"] == "on_demand"
    assert status["last_cycle"]["pass_count"] == 1

    # Recorded into the app's real history store, same as any other run.
    history_response = client.get(f"/api/history/{body['run_ids'][0]}", headers=auth_headers)
    assert history_response.status_code == 200
    assert history_response.json()["verdict"] == "pass"
