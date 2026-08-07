"""Shared test doubles - not fixtures themselves (pytest fixtures live in
conftest.py), just the plain classes fixtures and tests build on.
"""

from app.agents.llm_client import LLMClient, LLMError, LLMResponse


class FakeLLM(LLMClient):
    """Returns queued responses in order. Queue a string for a normal
    reply, or an Exception instance to make that call raise instead."""

    provider = "fake"
    model = "fake-model"

    def __init__(self, responses: list[str | Exception] | None = None) -> None:
        super().__init__()
        self._responses = list(responses or [])
        self.prompts: list[str] = []

    def queue(self, response: str | Exception) -> None:
        self._responses.append(response)

    async def complete(self, prompt: str, *, max_tokens: int = 300, timeout: float | None = None) -> LLMResponse:
        self.prompts.append(prompt)
        if not self._responses:
            raise LLMError("FakeLLM has no queued responses left.")
        next_response = self._responses.pop(0)
        if isinstance(next_response, Exception):
            raise next_response

        response = LLMResponse(
            text=next_response,
            provider=self.provider,
            model=self.model,
            started_at=0.0,
            finished_at=0.001,
            duration_ms=1.0,
            input_tokens=100,
            output_tokens=20,
        )
        self._record_usage(response)
        return response
