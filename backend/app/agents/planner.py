"""Planner Agent - the supervisor in the pipeline. Reads a ticket via the
Trello MCP tool, matches it against the registered domain manifest, and
produces a structured, validated test plan for the Explorer.

Domain matching is deliberately a Claude call, not string matching: the
ticket's wording needs to be interpreted, and a wrong match here would
send every downstream agent testing the wrong thing.
"""

import json
import os

from anthropic import AsyncAnthropic

from app.agents.schema import TestPlan
from app.domains.manifest import load_domains
from app.mcp_server.server import get_ticket

PLANNER_MODEL = "claude-sonnet-5"


class PlannerError(Exception):
    """Raised when the Planner cannot proceed - a missing API key, an
    unreadable ticket, or a model response that doesn't parse."""


class PlannerAgent:
    def __init__(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise PlannerError("ANTHROPIC_API_KEY must be set before the Planner can run.")
        self._client = AsyncAnthropic(api_key=api_key)
        self._domains = load_domains()

    async def plan(self, ticket_id: str) -> TestPlan:
        ticket = await get_ticket(ticket_id)
        if "error" in ticket:
            raise PlannerError(f"Could not read ticket {ticket_id}: {ticket['error']}")

        match = await self._match_domain(ticket)

        if not match.get("matched"):
            return TestPlan(
                ticket_id=ticket_id,
                ticket_title=ticket.get("title"),
                matched=False,
                reason=match.get("reason", "No domain knowledge for this target."),
            )

        domain = next((d for d in self._domains if d.name == match.get("domain")), None)
        workflow = next((w for w in domain.workflows if w.name == match.get("workflow")), None) if domain else None

        if domain is None or workflow is None:
            # The model named something outside the real manifest - treat
            # this as unmatched rather than trusting a hallucinated result.
            return TestPlan(
                ticket_id=ticket_id,
                ticket_title=ticket.get("title"),
                matched=False,
                reason="Model matched to a domain/workflow that isn't in the registered manifest.",
            )

        return TestPlan(
            ticket_id=ticket_id,
            ticket_title=ticket.get("title"),
            matched=True,
            domain=domain.name,
            workflow=workflow.name,
            steps=workflow.steps,
            expected_outcome=workflow.expected_outcome.model_dump(),
        )

    async def _match_domain(self, ticket: dict) -> dict:
        manifest_summary = [
            {"domain": d.name, "base_url": d.base_url, "workflows": [w.name for w in d.workflows]}
            for d in self._domains
        ]

        prompt = f"""You are matching a QA test ticket to one known, registered domain and workflow.

Registered domains (this is the COMPLETE list - nothing else is known to this system):
{json.dumps(manifest_summary, indent=2)}

Ticket:
Title: {ticket.get("title")}
Description: {ticket.get("description")}

Decide which registered domain and workflow this ticket is asking to test, based on the
title/description text and any URL mentioned. If the ticket does not clearly match one of
the registered domains and workflows above, you MUST say it doesn't match - never guess or
substitute the closest one.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"matched": true, "domain": "<domain name>", "workflow": "<workflow name>"}}
or
{{"matched": false, "reason": "<short reason>"}}
"""

        response = await self._client.messages.create(
            model=PLANNER_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text.strip()
        try:
            return json.loads(raw_text)
        except (json.JSONDecodeError, IndexError) as exc:
            raise PlannerError(f"Planner model returned an unparseable response: {raw_text!r}") from exc
