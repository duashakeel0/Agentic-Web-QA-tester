"""Verifier Agent - what separates this from a scanner that reports "no
crash" as "no bug." It checks the Explorer's final page state against the
workflow's stored, known-correct assertion (a URL fragment, a piece of
text) instead of a subjective read of the page - "the page loaded with no
error" is not the same as "the page is correct," and only an explicit
assertion catches the difference.

A failed check is never confirmed on the first try: it's re-run once on
the exact same live page/session the Explorer ended on (not a fresh,
logged-out one), which is what separates a one-off slow render from a
real bug - if it still doesn't match a moment later, it's real.
"""

import asyncio
import json
import os

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.agents.claude_client import ClaudeLLMClient
from app.agents.llm_client import LLMClient, LLMError
from app.agents.schema import ExplorationResult, VerifierResult
from app.browser import BrowserSession

RECHECK_WAIT_SECONDS = 2
RECHECK_NAV_TIMEOUT_SECONDS = 15
LLM_TIMEOUT_SECONDS = 20
LLM_RETRY_TIMEOUT_SECONDS = 8
SCREENSHOT_DIR = "reports/screenshots"


class VerifierAgent:
    def __init__(self, llm: LLMClient | None = None, screenshot_dir: str = SCREENSHOT_DIR) -> None:
        if llm is not None:
            self._llm = llm
        else:
            try:
                self._llm = ClaudeLLMClient()
            except LLMError:
                self._llm = None
        self._screenshot_dir = screenshot_dir

    async def verify(
        self,
        expected_outcome: dict,
        result: ExplorationResult,
        browser: BrowserSession | None = None,
    ) -> VerifierResult:
        """browser, if given, should be the Explorer's own still-open
        session (only meaningful when result.completed is True) - the
        retry re-reads that same page rather than a fresh, logged-out
        navigation, since a slow render resolves itself in place but a
        lost session would look like a failure for the wrong reason."""
        if not result.completed:
            return VerifierResult(
                ticket_id=result.ticket_id,
                domain=result.domain,
                workflow=result.workflow,
                verdict="fail",
                assertion_checked=expected_outcome,
                initial_check_passed=False,
                retried=False,
                explanation=result.error,
                explanation_status="skipped",
            )

        initial_passed = self._check_assertion(expected_outcome, result.final_url, result.final_page_text)
        error_count = self._count_errors(result)

        if initial_passed:
            explanation, status = await self._explain(expected_outcome, result, passed=True)
            return VerifierResult(
                ticket_id=result.ticket_id,
                domain=result.domain,
                workflow=result.workflow,
                verdict=self._verdict_for_pass(error_count),
                warning_count=error_count,
                assertion_checked=expected_outcome,
                initial_check_passed=True,
                retried=False,
                explanation=explanation,
                explanation_status=status,
            )

        retry_passed, retry_error, screenshot_path = await self._recheck(
            expected_outcome, result.final_url, browser, result.ticket_id, result.domain, result.workflow
        )
        verdict = self._verdict_for_pass(error_count) if retry_passed else "fail"
        explanation, status = await self._explain(expected_outcome, result, passed=retry_passed)

        return VerifierResult(
            ticket_id=result.ticket_id,
            domain=result.domain,
            workflow=result.workflow,
            verdict=verdict,
            warning_count=error_count if retry_passed else 0,
            assertion_checked=expected_outcome,
            initial_check_passed=False,
            retried=True,
            retry_passed=retry_passed,
            retry_error=retry_error,
            explanation=explanation,
            explanation_status=status,
            screenshot_path=screenshot_path,
        )

    @staticmethod
    def _verdict_for_pass(error_count: int) -> str:
        # The end state is genuinely correct either way - the only question
        # is whether it got there cleanly. A user shouldn't read "FAILED"
        # for a run that actually reached the right outcome; a handful of
        # recovered hiccups along the way is a real signal worth surfacing,
        # just not one that should read as a broken workflow.
        return "pass" if error_count == 0 else "pass_with_issues"

    @staticmethod
    def _count_errors(result: ExplorationResult) -> int:
        # Deliberate broken-input probes are SUPPOSED to fail - excluded so
        # intentional negative testing never counts against a clean run.
        #
        # action == "unknown" means no real action was ever attempted
        # against the site at all - it's Explorer's own LLMError catch
        # (a model call that timed out, returned unparseable JSON, or
        # omitted a required field), logged as "unknown" precisely because
        # there was no usable decision to execute. That's a hiccup in our
        # own agent's decision-making, not evidence the site under test has
        # a real issue - counting it here conflates the two, and demotes
        # an otherwise clean pass to pass_with_issues over a resolved
        # mistake of ours rather than a genuine site-side flake (a real
        # Playwright timeout/error on an actual click, fill, etc. still
        # counts, since that's real signal about the application).
        return sum(
            1
            for a in result.actions
            if not a.success and not a.is_broken_input_attempt and a.action != "unknown"
        )

    @staticmethod
    def _check_assertion(expected: dict, url: str | None, text: str | None) -> bool:
        url_contains = expected.get("url_contains")
        text_contains = expected.get("text_contains")
        if url_contains and (not url or url_contains not in url):
            return False
        # Case-insensitive on purpose: a real page's exact capitalization
        # ("There are no results.") often doesn't match a hand-written
        # expected_outcome's casing ("No results") even though the
        # assertion is clearly satisfied - text_contains is checking that
        # a message appears, not testing capitalization as the bug itself.
        if text_contains and (not text or text_contains.lower() not in text.lower()):
            return False
        return True

    async def _recheck(
        self,
        expected: dict,
        final_url: str | None,
        browser: BrowserSession | None,
        ticket_id: str,
        domain: str,
        workflow: str,
    ) -> tuple[bool, str | None, str | None]:
        if browser is not None:
            try:
                await asyncio.sleep(RECHECK_WAIT_SECONDS)
                text = await browser.page.evaluate("() => document.body.innerText")
                passed = self._check_assertion(expected, browser.page.url, text)
                screenshot_path = None if passed else await self._capture_screenshot(browser, ticket_id, domain, workflow)
                return passed, None, screenshot_path
            except PlaywrightTimeoutError as exc:
                return False, f"Re-check timed out: {exc}", None
            except PlaywrightError as exc:
                return False, f"Browser crashed during re-check: {exc}", None

        if not final_url:
            return False, "No final URL to re-check.", None

        fresh = BrowserSession()
        try:
            await fresh.start()
            await asyncio.wait_for(fresh.page.goto(final_url), timeout=RECHECK_NAV_TIMEOUT_SECONDS)
            await asyncio.sleep(RECHECK_WAIT_SECONDS)
            text = await fresh.page.evaluate("() => document.body.innerText")
            passed = self._check_assertion(expected, fresh.page.url, text)
            screenshot_path = None if passed else await self._capture_screenshot(fresh, ticket_id, domain, workflow)
            return passed, None, screenshot_path
        except asyncio.TimeoutError:
            return False, "Re-check navigation timed out.", None
        except PlaywrightError as exc:
            return False, f"Browser crashed during re-check: {exc}", None
        finally:
            await fresh.close()

    async def _capture_screenshot(self, browser: BrowserSession, ticket_id: str, domain: str, workflow: str) -> str | None:
        try:
            os.makedirs(self._screenshot_dir, exist_ok=True)
            path = os.path.join(self._screenshot_dir, f"{ticket_id}_{domain}_{workflow}.png")
            await browser.page.screenshot(path=path)
            return path
        except PlaywrightError:
            # A crashed/closed browser can't be screenshotted either - the
            # finding still gets reported, just without a screenshot.
            return None

    async def _explain(
        self,
        expected: dict,
        result: ExplorationResult,
        passed: bool,
    ) -> tuple[str | None, str]:
        if self._llm is None:
            return None, "skipped"

        prompt = self._explanation_prompt(expected, result, passed)
        try:
            response = await self._llm.complete(prompt, max_tokens=400, timeout=LLM_TIMEOUT_SECONDS)
            return response.text, "ok"
        except LLMError:
            try:
                response = await self._llm.complete(prompt, max_tokens=400, timeout=LLM_RETRY_TIMEOUT_SECONDS)
                return response.text, "ok"
            except LLMError:
                return None, "inconclusive"

    @staticmethod
    def _explanation_prompt(expected: dict, result: ExplorationResult, passed: bool) -> str:
        return f"""You are writing a one-sentence QA note explaining a verification result.

Workflow: {result.workflow} (domain: {result.domain})
Expected outcome: {json.dumps(expected)}
Actual final URL: {result.final_url}
Actual final page text (truncated): {(result.final_page_text or "")[:300]}
Verdict: {"PASSED" if passed else "FAILED"}

Write one short, plain sentence explaining why this {"passed" if passed else "failed"}, suitable
for a bug/QA report. No other text.
"""
