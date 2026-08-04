"""Thin wrapper around Ollama's local REST API. The Explorer makes far more
model calls than the Planner (one per browser action, across every step and
every broken-input attempt), so it runs on a local Llama 3.1 instead of
Claude - the volume is high but the stakes of any single decision are low,
unlike the Planner's one-shot domain match.
"""

import json
import os

import httpx

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"
# Generous on purpose: Ollama has to load the full model into memory on its
# first call (can take well over a minute on a laptop CPU), and every call
# after that runs on the model but still has no hard upper bound on a slow
# machine - too short a timeout here reads as "Ollama isn't running" when
# it's actually just still thinking.
REQUEST_TIMEOUT_SECONDS = 180.0


class OllamaError(Exception):
    """Raised when Ollama can't be reached or returns something unusable."""


class OllamaClient:
    def __init__(self) -> None:
        self._host = os.environ.get("OLLAMA_HOST", DEFAULT_HOST)
        self._model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)

    async def decide(self, prompt: str) -> dict:
        """Sends a prompt and returns the parsed JSON decision. Raises
        OllamaError for anything that isn't a reachable server returning
        parseable JSON - callers should not have to deal with raw httpx or
        json exceptions."""
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self._host}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise OllamaError(
                f"Ollama at {self._host} didn't respond within {REQUEST_TIMEOUT_SECONDS:.0f}s - "
                f"it's likely still loading the model into memory on its first call, or the "
                f"machine is slow. Try again once Ollama's warmed up. ({exc})"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaError(
                f"Could not reach Ollama at {self._host} - is it running? ({exc})"
            ) from exc

        if response.status_code != 200:
            raise OllamaError(f"Ollama returned HTTP {response.status_code}: {response.text}")

        body = response.json()
        raw_text = body.get("response", "")
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama returned an unparseable response: {raw_text!r}") from exc
