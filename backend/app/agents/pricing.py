"""Rough cost estimate for a run, used only for the Claude-vs-Ollama
comparison dashboard - not a billing-accurate figure. Ollama runs locally,
so its cost is always 0; Claude's is estimated from token usage at a
configurable per-million-token rate (env-overridable since list prices
change and this project shouldn't need a code change to stay current).
"""

import os

DEFAULT_CLAUDE_INPUT_COST_PER_MTOK = 3.0
DEFAULT_CLAUDE_OUTPUT_COST_PER_MTOK = 15.0


def estimate_cost_usd(provider: str, input_tokens: int, output_tokens: int) -> float:
    if provider != "claude":
        return 0.0
    input_rate = float(os.environ.get("CLAUDE_INPUT_COST_PER_MTOK", DEFAULT_CLAUDE_INPUT_COST_PER_MTOK))
    output_rate = float(os.environ.get("CLAUDE_OUTPUT_COST_PER_MTOK", DEFAULT_CLAUDE_OUTPUT_COST_PER_MTOK))
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
