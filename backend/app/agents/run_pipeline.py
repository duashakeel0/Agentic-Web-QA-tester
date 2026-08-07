"""Manual test runner for the full pipeline with a model choice, mirroring
run_reporter.py but going through pipeline.py so it exercises the same
Claude/Ollama/both path a real dashboard-triggered run will use.

Usage (from backend/):
    python -m app.agents.run_pipeline <ticket_id> [claude|ollama|both]
"""

import asyncio
import sys

from dotenv import load_dotenv

from app.agents.pipeline import run_both, run_pipeline

load_dotenv()


async def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python -m app.agents.run_pipeline <ticket_id> [claude|ollama|both]")
        sys.exit(1)

    ticket_id = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) == 3 else "claude"

    if model == "both":
        claude_result, ollama_result, comparison = await run_both(ticket_id)
        print("Claude run:")
        print(claude_result.model_dump_json(indent=2))
        print("\nOllama run:")
        print(ollama_result.model_dump_json(indent=2))
        print("\nComparison:")
        print(comparison.model_dump_json(indent=2))
    else:
        result = await run_pipeline(ticket_id, model)
        print(f"{model.title()} run:")
        print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
