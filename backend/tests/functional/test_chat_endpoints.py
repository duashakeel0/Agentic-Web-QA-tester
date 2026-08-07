from unittest.mock import AsyncMock

import app.main as main_module
from app.agents.llm_client import LLMError, LLMResponse
from app.agents.schema import PipelineResult, TestPlan


class _FakeLLMClient:
    def __init__(self, text=None, error=None):
        self._text = text
        self._error = error

    async def complete(self, prompt, *, max_tokens=300, timeout=None):
        if self._error:
            raise self._error
        return LLMResponse(
            text=self._text, provider="claude", model="claude-fake",
            started_at=0.0, finished_at=0.01, duration_ms=10.0,
        )


def test_chat_requires_auth(client):
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_returns_reply(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module, "ClaudeLLMClient", lambda: _FakeLLMClient(text="Hi there!"))

    response = client.post("/api/chat", json={"message": "hello", "history": []}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["reply"] == "Hi there!"


def test_chat_returns_503_when_no_api_key(client, auth_headers, monkeypatch):
    def raises():
        raise LLMError("ANTHROPIC_API_KEY must be set to use the Claude client.")

    monkeypatch.setattr(main_module, "ClaudeLLMClient", raises)

    response = client.post("/api/chat", json={"message": "hello"}, headers=auth_headers)

    assert response.status_code == 503


def test_chat_returns_502_when_llm_call_fails(client, auth_headers, monkeypatch):
    monkeypatch.setattr(main_module, "ClaudeLLMClient", lambda: _FakeLLMClient(error=LLMError("timed out")))

    response = client.post("/api/chat", json={"message": "hello"}, headers=auth_headers)

    assert response.status_code == 502


def test_chat_starts_a_run_when_the_model_detects_that_intent(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "ClaudeLLMClient",
        lambda: _FakeLLMClient(
            text='{"intent": "run_ticket", "ticket_id": "ABC123", "model": "claude", '
            '"reply": "Starting a Claude run for ticket ABC123 now."}'
        ),
    )

    response = client.post("/api/chat", json={"message": "run ticket ABC123", "history": []}, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "run_ticket"
    assert body["ticket_id"] == "ABC123"
    assert body["model"] == "claude"
    assert body["reply"] == "Starting a Claude run for ticket ABC123 now."


def test_chat_defaults_to_claude_when_model_missing_or_invalid(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "ClaudeLLMClient",
        lambda: _FakeLLMClient(text='{"intent": "run_ticket", "ticket_id": "T1", "reply": "Starting now."}'),
    )

    response = client.post("/api/chat", json={"message": "run T1"}, headers=auth_headers)

    assert response.json()["model"] == "claude"


def test_chat_ignores_run_ticket_intent_with_no_ticket_id(client, auth_headers, monkeypatch):
    # A malformed/incomplete run_ticket response (no ticket_id) should
    # never be treated as an action - falls back to a plain chat reply
    # instead of trying to start a run with nothing to run.
    monkeypatch.setattr(
        main_module,
        "ClaudeLLMClient",
        lambda: _FakeLLMClient(text='{"intent": "run_ticket", "reply": "Which ticket should I run?"}'),
    )

    response = client.post("/api/chat", json={"message": "run something"}, headers=auth_headers)

    body = response.json()
    assert body["action"] is None
    assert body["reply"] == "Which ticket should I run?"


def test_chat_json_reply_shown_directly_for_plain_chat_intent(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "ClaudeLLMClient",
        lambda: _FakeLLMClient(text='{"intent": "chat", "reply": "The Explorer uses Playwright."}'),
    )

    response = client.post("/api/chat", json={"message": "how does the explorer work?"}, headers=auth_headers)

    body = response.json()
    assert body["action"] is None
    assert body["reply"] == "The Explorer uses Playwright."


def test_chat_prompt_is_grounded_in_real_registered_domains(client, auth_headers, monkeypatch):
    captured_client = _FakeLLMClient(text='{"intent": "chat", "reply": "ok"}')
    captured_client.complete = AsyncMock(wraps=captured_client.complete)
    monkeypatch.setattr(main_module, "ClaudeLLMClient", lambda: captured_client)

    client.post("/api/chat", json={"message": "what sites can you test?"}, headers=auth_headers)

    prompt = captured_client.complete.call_args.args[0]
    # Real registered domain names, not a generic/hallucinated list -
    # confirms the prompt is actually grounded in load_domains().
    assert "practice_software_testing" in prompt
    assert "parabank" in prompt


def test_chat_includes_conversation_history_in_prompt(client, auth_headers, monkeypatch):
    captured_client = _FakeLLMClient(text="ok")
    captured_client.complete = AsyncMock(wraps=captured_client.complete)
    monkeypatch.setattr(main_module, "ClaudeLLMClient", lambda: captured_client)

    client.post(
        "/api/chat",
        json={"message": "and then?", "history": [{"role": "user", "content": "tell me a story"}, {"role": "assistant", "content": "once upon a time"}]},
        headers=auth_headers,
    )

    prompt = captured_client.complete.call_args.args[0]
    assert "tell me a story" in prompt
    assert "once upon a time" in prompt
    assert "and then?" in prompt


def test_ask_about_report_requires_auth(client):
    response = client.post("/api/history/1/ask", json={"question": "why?"})
    assert response.status_code == 401


async def test_ask_about_report_404_when_run_missing(client, auth_headers):
    response = client.post("/api/history/999/ask", json={"question": "why?"}, headers=auth_headers)
    assert response.status_code == 404


async def test_ask_about_report_returns_grounded_answer(client, auth_headers, app_history, monkeypatch):
    result = PipelineResult(
        ticket_id="T1", provider="claude",
        plan=TestPlan(ticket_id="T1", matched=True, domain="practice_software_testing", workflow="login", steps=["a"]),
        started_at=0.0, finished_at=0.5, total_duration_ms=500.0,
    )
    run_id = await app_history.record_run(result)
    monkeypatch.setattr(main_module, "ClaudeLLMClient", lambda: _FakeLLMClient(text="It failed because of a timeout."))

    response = client.post(f"/api/history/{run_id}/ask", json={"question": "why did it fail?"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["answer"] == "It failed because of a timeout."
