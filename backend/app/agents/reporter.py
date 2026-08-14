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

from app.agents.claude_client import ClaudeLLMClient
from app.agents.email_sender import EmailError, EmailSender
from app.agents.llm_client import LLMClient, LLMError
from app.agents.schema import ExplorationResult, Finding, Report, RunResult, VerifierResult
from app.mcp_server.server import post_summary

POST_SUMMARY_MAX_ATTEMPTS = 2
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

logger = logging.getLogger(__name__)


class ReporterAgent:
    def __init__(
        self,
        llm: LLMClient | None = None,
        email_sender: EmailSender | None = None,
    ) -> None:
        if llm is not None:
            self._llm = llm
        else:
            try:
                self._llm = ClaudeLLMClient()
            except LLMError:
                self._llm = None
        self._email_sender = email_sender if email_sender is not None else EmailSender()

    async def report(self, ticket_id: str, runs: list[RunResult]) -> Report:
        findings: list[Finding] = []

        for run in runs:
            verdict = run.verification.verdict
            if verdict == "pass":
                continue
            if verdict == "pass_with_issues":
                # The end state was genuinely correct - this isn't a bug to
                # classify, just worth surfacing that it wasn't clean. No
                # LLM call, no alert; a recovered hiccup on an otherwise
                # passing run doesn't need either.
                findings.append(self._minor_issues_finding(run))
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
        summary_text = self._render_summary(report, runs)
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
            error_message=self._error_message(exploration, verification),
            reproduction_steps=self._reproduction_steps(exploration),
            screenshot_path=verification.screenshot_path,
            explanation=verification.explanation,
        )

    @staticmethod
    def _minor_issues_finding(run: RunResult) -> Finding:
        exploration, verification = run.exploration, run.verification
        return Finding(
            ticket_id=exploration.ticket_id,
            domain=exploration.domain,
            workflow=exploration.workflow,
            severity="low",
            summary=(
                f"Workflow completed and passed, but {verification.warning_count} action(s) "
                "failed or needed a retry along the way."
            ),
            error_message=ReporterAgent._error_message(exploration, verification),
            reproduction_steps=ReporterAgent._reproduction_steps(exploration),
            screenshot_path=verification.screenshot_path,
            explanation=verification.explanation,
        )

    @staticmethod
    def _error_message(exploration: ExplorationResult, verification: VerifierResult) -> str | None:
        """The most specific underlying *execution* error available, distinct
        from the LLM-written failure reason - a Trello comment should show
        both, but only when there's a real execution error to show."""
        if verification.retry_error:
            return verification.retry_error
        if exploration.error:
            return exploration.error
        if exploration.completed:
            # The exploration reached the end of the workflow - every step,
            # including any that needed a retry along the way, ultimately
            # succeeded (that's what "completed" means). A transient failed
            # attempt earlier in the log is resolved noise at that point,
            # not the reason verification failed - the real reason is
            # whatever the assertion/explanation above already says. Showing
            # a stray retry's error here would misattribute a perfectly
            # normal recovery as if it were the actual cause of the finding.
            return None
        # Exploration never reached the end (a genuine ExplorerError stopped
        # it) - the last real failure (never a deliberate broken-input
        # probe, which is *supposed* to fail and is unrelated to why
        # execution actually got stuck) is the most specific info available.
        failed_actions = [a for a in exploration.actions if not a.success and a.error and not a.is_broken_input_attempt]
        return failed_actions[-1].error if failed_actions else None

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
        if self._llm is None:
            return "high", "Could not classify severity (no model configured) - defaulting to high severity out of caution."

        prompt = self._classification_prompt(exploration, verification)
        try:
            # No explicit timeout here on purpose - each provider's own
            # client already picks a sensible default (60s Claude, 180s
            # Ollama, which genuinely needs that long on a slow/cold local
            # machine). A single flat timeout for both providers was either
            # too tight for Ollama or too loose for Claude.
            data, _ = await self._llm.complete_json(prompt, max_tokens=300)
            severity = data.get("severity")
            if severity not in ("high", "medium", "low"):
                raise ValueError(f"Unexpected severity value: {severity!r}")
            return severity, data.get("summary", "")
        except (LLMError, ValueError):
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
    def _render_summary(report: Report, runs: list[RunResult]) -> str:
        """Every Trello comment leads with an explicit Result line and a
        testing summary, then one block per confirmed finding with its
        failure reason and raw error message - not just a list of bugs
        with no indication of what passed."""
        passed = [r for r in runs if r.verification.verdict == "pass"]
        passed_with_issues = [r for r in runs if r.verification.verdict == "pass_with_issues"]
        failed = [r for r in runs if r.verification.verdict == "fail"]

        # "ISSUE FOUND" rather than "FAIL" - by this point the agent has
        # run the workflow correctly and found a real defect on the site
        # under test, not failed to do its own job.
        overall = "ISSUE FOUND" if failed else ("PASS WITH ISSUES" if passed_with_issues else "PASS")
        lines = [
            f"Result: {overall}",
            f"Testing summary: {len(passed)} passed, {len(passed_with_issues)} passed with issues, "
            f"{len(failed)} failed out of {len(runs)} workflow(s) tested.",
            "",
        ]
        for run in passed:
            lines.append(
                f"[PASS] {run.exploration.domain}/{run.exploration.workflow} - "
                f"completed in {len(run.exploration.actions)} action(s)."
            )
        for run in passed_with_issues:
            lines.append(
                f"[PASS WITH ISSUES] {run.exploration.domain}/{run.exploration.workflow} - "
                f"completed in {len(run.exploration.actions)} action(s), "
                f"{run.verification.warning_count} recovered error(s) along the way."
            )

        if not report.findings:
            return "\n".join(lines).rstrip()

        lines.append("")
        lines.append(f"{len(report.findings)} confirmed finding(s), ranked by severity:")
        lines.append("")
        for finding in report.findings:
            lines.append(f"[{finding.severity.upper()}] {finding.domain}/{finding.workflow}")
            lines.append(f"Failure reason: {finding.summary}")
            if finding.error_message:
                lines.append(f"Error message: {finding.error_message}")
            if finding.reproduction_steps:
                lines.append("Reproduction steps:")
                lines.extend(f"  {i + 1}. {step}" for i, step in enumerate(finding.reproduction_steps))
            if finding.screenshot_path:
                lines.append(f"Screenshot: {finding.screenshot_path}")
            lines.append("")
        return "\n".join(lines).rstrip()
