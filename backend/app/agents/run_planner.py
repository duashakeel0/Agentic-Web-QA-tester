"""Manual test runner for the Planner agent - prints the resulting plan for
a given ticket ID so it can be reviewed by hand against the ticket's actual
intent, per this ticket's acceptance criteria.

Usage (from backend/):
    python -m app.agents.run_planner <ticket_id>
"""

import asyncio
import sys

from dotenv import load_dotenv

from app.agents.planner import PlannerAgent

load_dotenv()


async def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m app.agents.run_planner <ticket_id>")
        sys.exit(1)

    planner = PlannerAgent()
    plan = await planner.plan(sys.argv[1])
    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
