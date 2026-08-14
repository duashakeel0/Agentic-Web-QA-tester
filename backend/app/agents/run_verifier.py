"""Manual test runner for the Verifier agent - runs the Planner, Explorer,
and Verifier back to back against a real ticket, reusing the Explorer's
own live browser session for the Verifier's re-check, and prints the final
verdict.

Usage (from backend/):
    python -m app.agents.run_verifier <ticket_id>
"""

import asyncio
import sys

from dotenv import load_dotenv

from app.agents.explorer import ExplorerAgent
from app.agents.planner import PlannerAgent
from app.agents.verifier import VerifierAgent

load_dotenv()


async def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m app.agents.run_verifier <ticket_id>")
        sys.exit(1)

    planner = PlannerAgent()
    plan = await planner.plan(sys.argv[1])
    print("Plan:")
    print(plan.model_dump_json(indent=2))

    if not plan.matched:
        print("\nPlan did not match a registered domain - nothing to explore or verify.")
        return

    explorer = ExplorerAgent()
    exploration = await explorer.explore(plan, close_browser=False)
    print("\nExploration result:")
    print(exploration.model_dump_json(indent=2))

    verifier = VerifierAgent()
    try:
        verdict = await verifier.verify(
            plan.expected_outcome or {},
            exploration,
            browser=explorer.browser if exploration.completed else None,
        )
    finally:
        if exploration.completed:
            await explorer.browser.close()

    print("\nVerification result:")
    print(verdict.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
