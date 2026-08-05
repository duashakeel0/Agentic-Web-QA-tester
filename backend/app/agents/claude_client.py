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
# Applied whenever a caller doesn't pass its own timeout. Without this, a
# stalled network call to Claude hangs forever with zero indication - the
# caller (or the person watching the dashboard) can't tell "still working"
# from "dead" until this fires. 60s comfortably covers a real response;
# anything past that is a hung connection, not a slow one.
DEFAULT_TIMEOUT_SECONDS = 60.0


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
        effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS
        started_at = time.time()
        started_monotonic = time.monotonic()
        call = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            response = await asyncio.wait_for(call, timeout=effective_timeout)
        except asyncio.TimeoutError as exc:
            raise LLMError(f"Claude did not respond within {effective_timeout:.0f}s.") from exc
        except APIError as exc:
            raise LLMError(f"Claude API call failed: {exc}") from exc

        # Extended-thinking responses put a ThinkingBlock (no .text) ahead of
        # the actual reply, so content[0] isn't reliably the text block -
        # find the first block that actually has one instead of assuming.
        text_block = next((block for block in response.content if hasattr(block, "text")), None)
        if text_block is None:
            raise LLMError("Claude's response contained no text content.")

        finished_at, duration_ms = timed_since(started_monotonic)
        llm_response = LLMResponse(
            text=text_block.text.strip(),
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
