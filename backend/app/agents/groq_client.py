"""Groq's hosted Llama models via its OpenAI-compatible chat completions
API - an alternative backend for the "ollama" provider slot, for when local
Ollama is too slow (e.g. CPU-only inference with no GPU). Kept behind the
same LLMClient interface and the same provider="ollama" label the local
client uses, so nothing downstream (comparison reports, history stats, the
frontend's "Llama (Ollama)" tag, cost estimation) needs to know or care
which one actually ran - see pipeline.py's make_llm() for how the choice
between the two is made.
"""

import asyncio
import os
import re
import time

import httpx

from app.agents.llm_client import LLMClient, LLMError, LLMResponse, timed_since

API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Groq's fastest Llama model - similar parameter count to what a local
# CPU setup would struggle with, but running on purpose-built hardware
# instead, so speed isn't the tradeoff switching to a smaller model is.
DEFAULT_MODEL = "llama-3.1-8b-instant"
# Generous but bounded - Groq's hosted hardware is dramatically faster
# than CPU-only local inference, so a real stall here means something's
# actually wrong (rate limit, outage), not "still thinking."
REQUEST_TIMEOUT_SECONDS = 60.0
# The free tier's tokens-per-minute budget is easy to blow through
# precisely because Groq is so fast - the Explorer's many rapid per-action
# calls used to be naturally paced out by local Ollama's own slowness, but
# nothing paces them against Groq. A 429 always tells us how long to wait
# (Retry-After header, or "try again in Xs" in the error body); retried a
# couple of times with that wait instead of failing the whole exploration
# outright the first time the per-minute budget is momentarily exceeded.
MAX_RATE_LIMIT_RETRIES = 3
_RETRY_AFTER_SECONDS_PATTERN = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)
_DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 5.0


class GroqLLMClient(LLMClient):
    # Deliberately "ollama", not "groq" - this is a drop-in backend for the
    # same free/local-model comparison arm, not a fourth provider concept.
    # Keeping the label means every existing report/stat/UI path (which
    # only knows "claude" and "ollama") keeps working unchanged; the real
    # model actually used is still visible via `model` below wherever a
    # run's timings are shown.
    provider = "ollama"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__()
        self._api_key = api_key or os.environ.get("GROQ_API_KEY")
        if not self._api_key:
            raise LLMError("GROQ_API_KEY is not set - required to use Groq as the Ollama backend.")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)

    @staticmethod
    def _rate_limit_wait_seconds(response: httpx.Response) -> float:
        header = response.headers.get("retry-after")
        if header:
            try:
                return max(float(header), 0.0) + 0.5
            except ValueError:
                pass
        match = _RETRY_AFTER_SECONDS_PATTERN.search(response.text)
        if match:
            return float(match.group(1)) + 0.5
        return _DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    async def complete(self, prompt: str, *, max_tokens: int = 300, timeout: float | None = None) -> LLMResponse:
        request_timeout = timeout if timeout is not None else REQUEST_TIMEOUT_SECONDS
        started_at = time.time()
        started_monotonic = time.monotonic()

        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=request_timeout) as client:
                    response = await client.post(
                        API_URL,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": max_tokens,
                            "response_format": {"type": "json_object"},
                        },
                    )
            except httpx.TimeoutException as exc:
                raise LLMError(f"Groq didn't respond within {request_timeout:.0f}s. ({exc})") from exc
            except httpx.RequestError as exc:
                raise LLMError(
                    f"Could not reach Groq - is GROQ_API_KEY valid and is there network access? ({exc})"
                ) from exc

            if response.status_code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                await asyncio.sleep(self._rate_limit_wait_seconds(response))
                continue
            break

        if response.status_code != 200:
            raise LLMError(f"Groq returned HTTP {response.status_code}: {response.text}")

        finished_at, duration_ms = timed_since(started_monotonic)
        body = response.json()
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Groq returned an unexpected response shape: {body!r}") from exc

        usage = body.get("usage", {})
        llm_response = LLMResponse(
            text=text,
            provider=self.provider,
            model=self.model,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
        self._record_usage(llm_response)
        return llm_response
