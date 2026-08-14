from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic import APIError

from app.agents.claude_client import ClaudeLLMClient
from app.agents.llm_client import LLMError


def _fake_anthropic_response(text: str, input_tokens: int = 50, output_tokens: int = 10):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_constructor_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        ClaudeLLMClient()


async def test_complete_returns_text_and_usage():
    client = ClaudeLLMClient(api_key="test-key")
    client._client.messages.create = AsyncMock(return_value=_fake_anthropic_response("  hello  "))

    response = await client.complete("prompt")

    assert response.text == "hello"  # stripped
    assert response.provider == "claude"
    assert response.input_tokens == 50
    assert response.output_tokens == 10
    assert client.call_count == 1
    assert client.total_input_tokens == 50
    assert client.total_output_tokens == 10


async def test_complete_wraps_api_error():
    client = ClaudeLLMClient(api_key="test-key")
    client._client.messages.create = AsyncMock(side_effect=APIError("boom", request=None, body=None))

    with pytest.raises(LLMError, match="Claude API call failed"):
        await client.complete("prompt")

    assert client.call_count == 0  # no usage recorded on failure


async def test_complete_raises_helpful_error_when_no_text_block(monkeypatch):
    # Reproduces a real production failure: max_tokens was too tight and
    # Claude's whole budget went to a non-text block (e.g. reasoning) before
    # any real answer text, leaving content with nothing that has .text -
    # burns an Explorer step's entire action budget on repeated identical
    # failures if the error doesn't at least explain why.
    client = ClaudeLLMClient(api_key="test-key")
    response = SimpleNamespace(
        content=[SimpleNamespace(type="thinking")],  # no .text attribute
        stop_reason="max_tokens",
        usage=SimpleNamespace(input_tokens=50, output_tokens=10),
    )
    client._client.messages.create = AsyncMock(return_value=response)

    with pytest.raises(LLMError, match="cut off by max_tokens"):
        await client.complete("prompt")


async def test_complete_no_text_block_error_omits_hint_for_other_stop_reasons():
    client = ClaudeLLMClient(api_key="test-key")
    response = SimpleNamespace(
        content=[SimpleNamespace(type="thinking")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=50, output_tokens=10),
    )
    client._client.messages.create = AsyncMock(return_value=response)

    with pytest.raises(LLMError) as exc_info:
        await client.complete("prompt")
    assert "cut off by max_tokens" not in str(exc_info.value)


async def test_complete_times_out(monkeypatch):
    import asyncio

    client = ClaudeLLMClient(api_key="test-key")

    async def never_returns(*args, **kwargs):
        await asyncio.sleep(10)

    client._client.messages.create = AsyncMock(side_effect=never_returns)

    with pytest.raises(LLMError, match="did not respond within"):
        await client.complete("prompt", timeout=0.01)
