import pytest

import app.main as main_module
from app.agents.schema import PipelineResult, TestPlan


@pytest.fixture(autouse=True)
def trello_connected(monkeypatch):
    # Every ticket run now requires Trello to be connected - these tests
    # are about the pipeline's own event streaming, not about that gate,
    # so it's satisfied here by default. test_trello_not_connected_* below
    # explicitly unsets it to test the gate itself.
    monkeypatch.setenv("TRELLO_API_KEY", "fake-key")
    monkeypatch.setenv("TRELLO_TOKEN", "fake-token")


def _fake_result(provider):
    return PipelineResult(
        ticket_id="T1", provider=provider,
        plan=TestPlan(ticket_id="T1", matched=True, domain="practice_software_testing", workflow="login", steps=["a"]),
        started_at=0.0, finished_at=0.05, total_duration_ms=50.0,
    )


async def _fake_run_pipeline(ticket_id, provider, on_event=None):
    if on_event:
        await on_event({"type": "stage_start", "provider": provider, "agent": "planner"})
        await on_event(
            {"type": "stage_end", "provider": provider, "agent": "planner", "duration_ms": 12.0, "message": "Matched."}
        )
    return _fake_result(provider)


def test_single_model_run_streams_events_then_result(client, auth_token, monkeypatch):
    monkeypatch.setattr(main_module, "run_pipeline", _fake_run_pipeline)

    with client.websocket_connect(f"/ws/pipeline?token={auth_token}") as ws:
        ws.send_json({"ticket_id": "T1", "model": "claude"})
        events = [ws.receive_json() for _ in range(3)]

    assert [e["type"] for e in events] == ["stage_start", "stage_end", "pipeline_done"]
    assert events[-1]["result"]["provider"] == "claude"
    assert events[-1]["history_id"] == 1


def test_connecting_without_token_is_rejected(client):
    try:
        with client.websocket_connect("/ws/pipeline") as ws:
            ws.send_json({"ticket_id": "T1", "model": "claude"})
            ws.receive_json()
        rejected = False
    except Exception:
        rejected = True
    assert rejected


def test_connecting_with_invalid_token_is_rejected(client):
    try:
        with client.websocket_connect("/ws/pipeline?token=garbage") as ws:
            ws.send_json({"ticket_id": "T1", "model": "claude"})
            ws.receive_json()
        rejected = False
    except Exception:
        rejected = True
    assert rejected


def test_missing_ticket_id_returns_error_event(client, auth_token):
    with client.websocket_connect(f"/ws/pipeline?token={auth_token}") as ws:
        ws.send_json({"model": "claude"})
        event = ws.receive_json()
    assert event["type"] == "error"
    assert "ticket_id" in event["message"]


def test_invalid_model_returns_error_event(client, auth_token):
    with client.websocket_connect(f"/ws/pipeline?token={auth_token}") as ws:
        ws.send_json({"ticket_id": "T1", "model": "gpt4"})
        event = ws.receive_json()
    assert event["type"] == "error"
    assert "gpt4" in event["message"]


def test_trello_not_connected_returns_error_event_and_never_starts_the_pipeline(client, auth_token, monkeypatch):
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)
    started = False

    async def fake_run_pipeline(ticket_id, provider, on_event=None):
        nonlocal started
        started = True
        return _fake_result(provider)

    monkeypatch.setattr(main_module, "run_pipeline", fake_run_pipeline)

    with client.websocket_connect(f"/ws/pipeline?token={auth_token}") as ws:
        ws.send_json({"ticket_id": "T1", "model": "claude"})
        event = ws.receive_json()

    assert event["type"] == "error"
    assert "Trello isn't connected" in event["message"]
    assert started is False


def test_pipeline_exception_becomes_error_event(client, auth_token, monkeypatch):
    async def raises(ticket_id, provider, on_event=None):
        raise RuntimeError("planner blew up")

    monkeypatch.setattr(main_module, "run_pipeline", raises)

    with client.websocket_connect(f"/ws/pipeline?token={auth_token}") as ws:
        ws.send_json({"ticket_id": "T1", "model": "ollama"})
        event = ws.receive_json()

    assert event["type"] == "error"
    assert "planner blew up" in event["message"]


def test_both_models_streams_two_results_and_a_comparison(client, auth_token, monkeypatch):
    async def fake_run_both(ticket_id, on_event=None):
        claude_result = await _fake_run_pipeline(ticket_id, "claude", on_event)
        ollama_result = await _fake_run_pipeline(ticket_id, "ollama", on_event)
        from app.agents.schema import ComparisonReport

        return claude_result, ollama_result, ComparisonReport(ticket_id=ticket_id, summary="done")

    monkeypatch.setattr(main_module, "run_both", fake_run_both)

    with client.websocket_connect(f"/ws/pipeline?token={auth_token}") as ws:
        ws.send_json({"ticket_id": "T1", "model": "both"})
        events = [ws.receive_json() for _ in range(7)]

    types = [e["type"] for e in events]
    assert types == [
        "stage_start", "stage_end", "stage_start", "stage_end",
        "pipeline_done", "pipeline_done", "comparison_done",
    ]
    done_providers = [e["provider"] for e in events if e["type"] == "pipeline_done"]
    assert done_providers == ["claude", "ollama"]
