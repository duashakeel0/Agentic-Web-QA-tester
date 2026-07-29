"""Manual test runner for the Explorer agent - runs the Planner and Explorer
back to back against a real ticket and prints the resulting exploration log
for review, per this ticket's acceptance criteria.

Usage (from backend/):
    python -m app.agents.run_explorer <ticket_id>
"""

import asyncio
import sys

from dotenv import load_dotenv

from app.agents.explorer import ExplorerAgent
from app.agents.planner import PlannerAgent

load_dotenv()


async def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m app.agents.run_explorer <ticket_id>")
        sys.exit(1)

    planner = PlannerAgent()
    plan = await planner.plan(sys.argv[1])
    print("Plan:")
    print(plan.model_dump_json(indent=2))

    if not plan.matched:
        print("\nPlan did not match a registered domain - nothing for the Explorer to run.")
        return

    explorer = ExplorerAgent()
    result = await explorer.explore(plan)
    print("\nExploration result:")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
