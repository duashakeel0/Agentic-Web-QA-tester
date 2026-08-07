import json

import httpx
import pytest

from app.agents.groq_client import GroqLLMClient
from app.agents.llm_client import LLMError


async def test_complete_returns_text_and_token_counts(httpx_mock):
    httpx_mock.add_response(
        url="https://api.groq.com/openai/v1/chat/completions",
        json={
            "choices": [{"message": {"content": '{"action": "click"}'}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 7},
        },
    )
    client = GroqLLMClient(api_key="test-key")

    response = await client.complete("prompt")

    assert response.text == '{"action": "click"}'
    # Deliberately "ollama", not "groq" - a drop-in backend for the same
    # provider slot, not a distinct fourth provider (see groq_client.py).
    assert response.provider == "ollama"
    assert response.input_tokens == 42
    assert response.output_tokens == 7
    assert client.call_count == 1


async def test_sends_bearer_auth_and_json_mode(httpx_mock):
    httpx_mock.add_response(json={"choices": [{"message": {"content": "ok"}}]})
    client = GroqLLMClient(api_key="test-key", model="custom-model")

    await client.complete("prompt", max_tokens=123)

    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "custom-model"
    assert body["messages"] == [{"role": "user", "content": "prompt"}]
    assert body["max_tokens"] == 123
    assert body["response_format"] == {"type": "json_object"}


async def test_missing_api_key_raises_llmerror():
    with pytest.raises(LLMError, match="GROQ_API_KEY is not set"):
        GroqLLMClient(api_key=None)


async def test_api_key_from_env(monkeypatch, httpx_mock):
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    httpx_mock.add_response(json={"choices": [{"message": {"content": "ok"}}]})
    client = GroqLLMClient()

    await client.complete("prompt")

    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer env-key"


async def test_model_configurable_via_env(monkeypatch, httpx_mock):
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    httpx_mock.add_response(json={"choices": [{"message": {"content": "ok"}}]})
    client = GroqLLMClient(api_key="test-key")

    await client.complete("prompt")

    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["model"] == "llama-3.3-70b-versatile"


async def test_non_200_response_raises_llmerror(httpx_mock):
    httpx_mock.add_response(status_code=500, text="internal error")
    client = GroqLLMClient(api_key="test-key")

    with pytest.raises(LLMError, match="HTTP 500"):
        await client.complete("prompt")


async def test_retries_after_429_and_succeeds(monkeypatch, httpx_mock):
    # A momentarily exceeded free-tier tokens-per-minute budget shouldn't
    # fail the whole exploration - Groq tells us exactly how long to wait
    # ("try again in Xs" in the error body), and the very next call
    # typically succeeds once that window passes.
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("app.agents.groq_client.asyncio.sleep", fake_sleep)

    httpx_mock.add_response(
        status_code=429,
        json={"error": {"message": "Rate limit reached... Please try again in 2.5s.", "code": "rate_limit_exceeded"}},
    )
    httpx_mock.add_response(json={"choices": [{"message": {"content": "ok"}}]})

    client = GroqLLMClient(api_key="test-key")
    response = await client.complete("prompt")

    assert response.text == "ok"
    assert slept == [3.0]  # 2.5s parsed from the message + 0.5s buffer
    assert len(httpx_mock.get_requests()) == 2


async def test_gives_up_after_max_retries_on_persistent_429(monkeypatch, httpx_mock):
    from app.agents.groq_client import MAX_RATE_LIMIT_RETRIES

    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr("app.agents.groq_client.asyncio.sleep", fake_sleep)

    # 1 initial attempt + MAX_RATE_LIMIT_RETRIES retries, then it gives up
    # rather than retrying forever against a genuinely exhausted quota.
    for _ in range(MAX_RATE_LIMIT_RETRIES + 1):
        httpx_mock.add_response(status_code=429, text="still rate limited")

    client = GroqLLMClient(api_key="test-key")

    with pytest.raises(LLMError, match="HTTP 429"):
        await client.complete("prompt")

    assert len(httpx_mock.get_requests()) == MAX_RATE_LIMIT_RETRIES + 1


def test_rate_limit_wait_seconds_uses_retry_after_header():
    response = httpx.Response(status_code=429, headers={"retry-after": "10"}, text="")
    assert GroqLLMClient._rate_limit_wait_seconds(response) == 10.5


def test_rate_limit_wait_seconds_falls_back_to_default_when_unparseable():
    response = httpx.Response(status_code=429, text="no useful info here")
    from app.agents.groq_client import _DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    assert GroqLLMClient._rate_limit_wait_seconds(response) == _DEFAULT_RATE_LIMIT_BACKOFF_SECONDS


async def test_connection_error_raises_llmerror(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    client = GroqLLMClient(api_key="test-key")

    with pytest.raises(LLMError, match="Could not reach Groq"):
        await client.complete("prompt")


async def test_timeout_raises_llmerror_with_helpful_message(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))
    client = GroqLLMClient(api_key="test-key")

    with pytest.raises(LLMError, match="didn't respond within"):
        await client.complete("prompt")


async def test_unexpected_response_shape_raises_llmerror(httpx_mock):
    httpx_mock.add_response(json={"unexpected": "shape"})
    client = GroqLLMClient(api_key="test-key")

    with pytest.raises(LLMError, match="unexpected response shape"):
        await client.complete("prompt")
