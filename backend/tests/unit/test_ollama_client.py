import httpx
import pytest

from app.agents.llm_client import LLMError
from app.agents.ollama_client import OllamaLLMClient


async def test_complete_returns_text_and_token_counts(httpx_mock):
    httpx_mock.add_response(
        url="http://localhost:11434/api/generate",
        json={"response": '{"action": "click"}', "prompt_eval_count": 42, "eval_count": 7},
    )
    client = OllamaLLMClient()

    response = await client.complete("prompt")

    assert response.text == '{"action": "click"}'
    assert response.provider == "ollama"
    assert response.input_tokens == 42
    assert response.output_tokens == 7
    assert client.call_count == 1


async def test_non_200_response_raises_llmerror(httpx_mock):
    httpx_mock.add_response(status_code=500, text="internal error")
    client = OllamaLLMClient()

    with pytest.raises(LLMError, match="HTTP 500"):
        await client.complete("prompt")


async def test_connection_error_raises_llmerror(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))
    client = OllamaLLMClient()

    with pytest.raises(LLMError, match="Could not reach Ollama"):
        await client.complete("prompt")


async def test_timeout_raises_llmerror_with_helpful_message(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))
    client = OllamaLLMClient()

    with pytest.raises(LLMError, match="didn't respond within"):
        await client.complete("prompt")


async def test_custom_host_and_model_from_constructor(httpx_mock):
    httpx_mock.add_response(url="http://custom-host:1234/api/generate", json={"response": "ok"})
    client = OllamaLLMClient(host="http://custom-host:1234", model="custom-model")

    await client.complete("prompt")

    request = httpx_mock.get_requests()[0]
    assert request.url == "http://custom-host:1234/api/generate"
    import json

    body = json.loads(request.content)
    assert body["model"] == "custom-model"


async def test_sends_keep_alive_so_ollama_stays_warm_between_calls(httpx_mock):
    # Ollama's own default unloads the model 5 minutes after the last call -
    # sending keep_alive on every request means a normal gap between
    # actions/runs doesn't pay the multi-minute reload penalty again.
    httpx_mock.add_response(json={"response": "ok"})
    client = OllamaLLMClient()

    await client.complete("prompt")

    import json

    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["keep_alive"] == "30m"


async def test_keep_alive_configurable_via_env(monkeypatch, httpx_mock):
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "1h")
    httpx_mock.add_response(json={"response": "ok"})
    client = OllamaLLMClient()

    await client.complete("prompt")

    import json

    body = json.loads(httpx_mock.get_requests()[0].content)
    assert body["keep_alive"] == "1h"
