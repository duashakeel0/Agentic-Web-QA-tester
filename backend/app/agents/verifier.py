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

from anthropic import APIError, AsyncAnthropic
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.agents.schema import ExplorationResult, VerifierResult
from app.browser import BrowserSession

VERIFIER_MODEL = "claude-sonnet-5"
RECHECK_WAIT_SECONDS = 2
RECHECK_NAV_TIMEOUT_SECONDS = 15
LLM_TIMEOUT_SECONDS = 20
LLM_RETRY_TIMEOUT_SECONDS = 8
SCREENSHOT_DIR = "reports/screenshots"


class VerifierAgent:
    def __init__(self, anthropic_client: AsyncAnthropic | None = None, screenshot_dir: str = SCREENSHOT_DIR) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic_client if anthropic_client is not None else (
            AsyncAnthropic(api_key=api_key) if api_key else None
        )
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

        if initial_passed:
            explanation, status = await self._explain(expected_outcome, result, passed=True)
            return VerifierResult(
                ticket_id=result.ticket_id,
                domain=result.domain,
                workflow=result.workflow,
                verdict="pass",
                assertion_checked=expected_outcome,
                initial_check_passed=True,
                retried=False,
                explanation=explanation,
                explanation_status=status,
            )

        retry_passed, retry_error, screenshot_path = await self._recheck(
            expected_outcome, result.final_url, browser, result.ticket_id, result.domain, result.workflow
        )
        verdict = "pass" if retry_passed else "fail"
        explanation, status = await self._explain(expected_outcome, result, passed=retry_passed)

        return VerifierResult(
            ticket_id=result.ticket_id,
            domain=result.domain,
            workflow=result.workflow,
            verdict=verdict,
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
    def _check_assertion(expected: dict, url: str | None, text: str | None) -> bool:
        url_contains = expected.get("url_contains")
        text_contains = expected.get("text_contains")
        if url_contains and (not url or url_contains not in url):
            return False
        if text_contains and (not text or text_contains not in text):
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
        if self._client is None:
            return None, "skipped"

        prompt = self._explanation_prompt(expected, result, passed)
        try:
            return await self._call_with_timeout(prompt, LLM_TIMEOUT_SECONDS), "ok"
        except (TimeoutError, APIError):
            try:
                return await self._call_with_timeout(prompt, LLM_RETRY_TIMEOUT_SECONDS), "ok"
            except (TimeoutError, APIError):
                return None, "inconclusive"

    async def _call_with_timeout(self, prompt: str, timeout: float) -> str:
        response = await asyncio.wait_for(
            self._client.messages.create(
                model=VERIFIER_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            ),
            timeout=timeout,
        )
        return response.content[0].text.strip()

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
