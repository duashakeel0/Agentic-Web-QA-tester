"""Reporter Agent - closes the loop. Turns every Verifier-confirmed
finding from a run into one severity-ranked report with reproduction
steps and a screenshot where one was captured, posts it back to the
originating ticket, and fires an immediate email alert for anything
high-severity instead of waiting for someone to check a dashboard.

Takes a list of RunResults rather than just one, since a real run (and
the Scheduler's future nightly batch) can confirm several findings of
different severities in one go - severity ranking is what lets someone
triage a report with several findings in it, and scoping alerts to
high-severity only is escalation, not noise.
"""

import asyncio
import json
import logging
import os

from anthropic import APIError, AsyncAnthropic

from app.agents.email_sender import EmailError, EmailSender
from app.agents.schema import ExplorationResult, Finding, Report, RunResult, VerifierResult
from app.mcp_server.server import post_summary

REPORTER_MODEL = "claude-sonnet-5"
CLASSIFY_TIMEOUT_SECONDS = 20
POST_SUMMARY_MAX_ATTEMPTS = 2
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

logger = logging.getLogger(__name__)


class ReporterAgent:
    def __init__(
        self,
        anthropic_client: AsyncAnthropic | None = None,
        email_sender: EmailSender | None = None,
    ) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic_client if anthropic_client is not None else (
            AsyncAnthropic(api_key=api_key) if api_key else None
        )
        self._email_sender = email_sender if email_sender is not None else EmailSender()

    async def report(self, ticket_id: str, runs: list[RunResult]) -> Report:
        findings: list[Finding] = []

        for run in runs:
            if run.verification.verdict != "fail":
                continue
            finding = await self._classify(run)
            findings.append(finding)
            if finding.severity == "high":
                # Fired the moment this one finding is confirmed high
                # severity, not batched until the whole report is done -
                # that's the difference between an alert and a digest.
                await self._alert(finding)

        findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 99))

        report = Report(ticket_id=ticket_id, findings=findings)
        summary_text = self._render_summary(report)
        await self._post_with_retry(ticket_id, summary_text, report)

        return report

    async def _classify(self, run: RunResult) -> Finding:
        exploration, verification = run.exploration, run.verification
        severity, summary = await self._classify_with_llm(exploration, verification)

        return Finding(
            ticket_id=exploration.ticket_id,
            domain=exploration.domain,
            workflow=exploration.workflow,
            severity=severity,
            summary=summary,
            reproduction_steps=self._reproduction_steps(exploration),
            screenshot_path=verification.screenshot_path,
            explanation=verification.explanation,
        )

    @staticmethod
    def _reproduction_steps(exploration: ExplorationResult) -> list[str]:
        steps = []
        for action in exploration.actions:
            if action.is_broken_input_attempt:
                continue
            piece = action.action
            if action.selector:
                piece += f" on {action.selector}"
            if action.value:
                piece += f" with {action.value!r}"
            steps.append(piece)
        return steps

    async def _classify_with_llm(self, exploration: ExplorationResult, verification: VerifierResult) -> tuple[str, str]:
        if self._client is None:
            return "high", "Could not classify severity (no model configured) - defaulting to high severity out of caution."

        prompt = self._classification_prompt(exploration, verification)
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=REPORTER_MODEL,
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=CLASSIFY_TIMEOUT_SECONDS,
            )
            data = json.loads(response.content[0].text.strip())
            severity = data.get("severity")
            if severity not in ("high", "medium", "low"):
                raise ValueError(f"Unexpected severity value: {severity!r}")
            return severity, data.get("summary", "")
        except (TimeoutError, APIError, json.JSONDecodeError, ValueError):
            logger.exception("Severity classification failed for ticket %s", exploration.ticket_id)
            return "high", "Could not classify severity (model call failed) - defaulting to high severity out of caution."

    @staticmethod
    def _classification_prompt(exploration: ExplorationResult, verification: VerifierResult) -> str:
        return f"""You are triaging a confirmed QA finding for severity.

Workflow: {exploration.workflow} (domain: {exploration.domain})
Expected outcome: {json.dumps(verification.assertion_checked)}
Actual final URL: {exploration.final_url}
Actual final page text (truncated): {(exploration.final_page_text or "")[:300]}
Why it failed: {verification.explanation}

Rate this "high" if it breaks a core piece of functionality (e.g. can't log in,
can't complete the workflow at all), "medium" if the workflow still basically
works but something is visibly wrong, or "low" if it's cosmetic/minor.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"severity": "high"|"medium"|"low", "summary": "<one sentence for a bug report>"}}
"""

    async def _alert(self, finding: Finding) -> None:
        subject = f"[HIGH SEVERITY] {finding.domain}/{finding.workflow} - {finding.ticket_id}"
        body = f"{finding.summary}\n\nReproduction steps:\n" + "\n".join(
            f"{i + 1}. {step}" for i, step in enumerate(finding.reproduction_steps)
        )
        try:
            await asyncio.to_thread(self._email_sender.send, subject, body)
        except EmailError:
            logger.exception("Failed to send high-severity alert email for ticket %s", finding.ticket_id)

    async def _post_with_retry(self, ticket_id: str, summary_text: str, report: Report) -> None:
        last_error = None
        for attempt in range(POST_SUMMARY_MAX_ATTEMPTS):
            result = await post_summary(ticket_id, summary_text)
            if "error" not in result:
                report.post_summary_status = "posted"
                return
            last_error = result["error"]
            logger.warning("post_summary attempt %d failed for ticket %s: %s", attempt + 1, ticket_id, last_error)

        report.post_summary_status = "failed"
        report.post_summary_error = last_error

    @staticmethod
    def _render_summary(report: Report) -> str:
        if not report.findings:
            return "Verification run completed - no confirmed findings."

        lines = [f"{len(report.findings)} confirmed finding(s), ranked by severity:", ""]
        for finding in report.findings:
            lines.append(f"[{finding.severity.upper()}] {finding.domain}/{finding.workflow}: {finding.summary}")
            if finding.reproduction_steps:
                lines.append("Reproduction steps:")
                lines.extend(f"  {i + 1}. {step}" for i, step in enumerate(finding.reproduction_steps))
            if finding.screenshot_path:
                lines.append(f"Screenshot: {finding.screenshot_path}")
            lines.append("")
        return "\n".join(lines)
