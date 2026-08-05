"""Ollama implementation of the LLMClient interface. A local Llama 3.1
instance, useful for high call-volume/low-stakes work (the Explorer makes one
call per browser action) or when the user picks Ollama - or Claude+Ollama
side by side - for a run.
"""

import os
import time

import httpx

from app.agents.llm_client import LLMClient, LLMError, LLMResponse, timed_since

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"
# Generous on purpose: Ollama has to load the full model into memory on its
# first call (can take well over a minute on a laptop CPU), and every call
# after that runs on the model but still has no hard upper bound on a slow
# machine - too short a timeout here reads as "Ollama isn't running" when
# it's actually just still thinking.
REQUEST_TIMEOUT_SECONDS = 180.0


class OllamaLLMClient(LLMClient):
    provider = "ollama"

    def __init__(self, host: str | None = None, model: str | None = None) -> None:
        self._host = host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST)
        self.model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)

    async def complete(self, prompt: str, *, max_tokens: int = 300, timeout: float | None = None) -> LLMResponse:
        request_timeout = timeout if timeout is not None else REQUEST_TIMEOUT_SECONDS
        started_at = time.time()
        started_monotonic = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.post(
                    f"{self._host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"Ollama at {self._host} didn't respond within {request_timeout:.0f}s - "
                f"it's likely still loading the model into memory on its first call, or the "
                f"machine is slow. Try again once Ollama's warmed up. ({exc})"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMError(f"Could not reach Ollama at {self._host} - is it running? ({exc})") from exc

        if response.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {response.status_code}: {response.text}")

        finished_at, duration_ms = timed_since(started_monotonic)
        return LLMResponse(
            text=response.json().get("response", ""),
            provider=self.provider,
            model=self.model,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
        )
