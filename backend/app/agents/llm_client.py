"""Common interface both model providers implement, so any agent can run
on either Claude or a local model without knowing which one it's actually
talking to. Every call is timed (started_at/finished_at/duration_ms) since
that's exactly the data the dual-model comparison report is built from -
timing isn't an afterthought bolted on later, it's part of the contract.
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(Exception):
    """Raised by any LLMClient implementation when a call fails - timeout,
    unreachable server, bad credentials, or an unparseable response.
    Provider-specific detail stays in the message; callers only need to
    catch this one type regardless of which provider is behind it."""


@dataclass
class LLMResponse:
    text: str
    provider: str  # "claude" | "ollama"
    model: str
    started_at: float  # unix timestamp (time.time())
    finished_at: float
    duration_ms: float


class LLMClient(ABC):
    provider: str
    model: str

    @abstractmethod
    async def complete(self, prompt: str, *, max_tokens: int = 300, timeout: float | None = None) -> LLMResponse:
        """Sends a prompt, returns the raw text response plus timing.
        Raises LLMError for anything that isn't a successful response in
        time - callers never have to deal with provider-specific
        exceptions (httpx, anthropic's APIError, etc.) directly."""

    async def complete_json(
        self, prompt: str, *, max_tokens: int = 300, timeout: float | None = None
    ) -> tuple[dict, LLMResponse]:
        """Convenience wrapper for the common case: every prompt in this
        project asks the model to respond with ONLY a JSON object, so every
        agent needs the same parse-and-validate step after calling
        complete(). Kept here once instead of duplicated in every agent."""
        response = await self.complete(prompt, max_tokens=max_tokens, timeout=timeout)
        try:
            return json.loads(response.text), response
        except json.JSONDecodeError as exc:
            raise LLMError(f"{self.provider} returned an unparseable response: {response.text!r}") from exc


def timed_since(started_monotonic: float) -> tuple[float, float]:
    """Shared by every concrete client: given the time.monotonic() value
    recorded right before a call started, returns (finished wall-clock
    timestamp, elapsed milliseconds) for the LLMResponse."""
    return time.time(), (time.monotonic() - started_monotonic) * 1000
