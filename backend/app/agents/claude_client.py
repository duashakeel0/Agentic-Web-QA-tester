"""Claude implementation of the LLMClient interface. Used by default for the
Planner/Verifier/Reporter's low-volume, high-stakes calls, and selectable for
the Explorer too now that every agent can run on either provider.
"""

import asyncio
import os
import time

from anthropic import APIError, AsyncAnthropic

from app.agents.llm_client import LLMClient, LLMError, LLMResponse, timed_since

DEFAULT_MODEL = "claude-sonnet-5"


class ClaudeLLMClient(LLMClient):
    provider = "claude"

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        super().__init__()
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY must be set to use the Claude client.")
        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def complete(self, prompt: str, *, max_tokens: int = 300, timeout: float | None = None) -> LLMResponse:
        started_at = time.time()
        started_monotonic = time.monotonic()
        call = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            response = await (asyncio.wait_for(call, timeout=timeout) if timeout is not None else call)
        except asyncio.TimeoutError as exc:
            raise LLMError(f"Claude did not respond within {timeout:.0f}s.") from exc
        except APIError as exc:
            raise LLMError(f"Claude API call failed: {exc}") from exc

        finished_at, duration_ms = timed_since(started_monotonic)
        llm_response = LLMResponse(
            text=response.content[0].text.strip(),
            provider=self.provider,
            model=self.model,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        self._record_usage(llm_response)
        return llm_response
