"""Manual test runner for the Reporter agent - runs the full pipeline
(Planner -> Explorer -> Verifier -> Reporter) against a real ticket and
prints the final report, including whether the write-back to Trello
succeeded.

Usage (from backend/):
    python -m app.agents.run_reporter <ticket_id>
"""

import asyncio
import sys

from dotenv import load_dotenv

from app.agents.explorer import ExplorerAgent
from app.agents.planner import PlannerAgent
from app.agents.reporter import ReporterAgent
from app.agents.schema import RunResult
from app.agents.verifier import VerifierAgent

load_dotenv()


async def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m app.agents.run_reporter <ticket_id>")
        sys.exit(1)

    ticket_id = sys.argv[1]

    planner = PlannerAgent()
    plan = await planner.plan(ticket_id)
    print("Plan:")
    print(plan.model_dump_json(indent=2))

    if not plan.matched:
        print("\nPlan did not match a registered domain - nothing to explore, verify, or report.")
        return

    explorer = ExplorerAgent()
    exploration = await explorer.explore(plan, close_browser=False)
    print("\nExploration result:")
    print(exploration.model_dump_json(indent=2))

    verifier = VerifierAgent()
    try:
        verification = await verifier.verify(
            plan.expected_outcome or {},
            exploration,
            browser=explorer.browser if exploration.completed else None,
        )
    finally:
        if exploration.completed:
            await explorer.browser.close()

    print("\nVerification result:")
    print(verification.model_dump_json(indent=2))

    reporter = ReporterAgent()
    report = await reporter.report(ticket_id, [RunResult(exploration=exploration, verification=verification)])
    print("\nReport:")
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
