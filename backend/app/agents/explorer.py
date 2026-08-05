"""Explorer Agent - the only agent that touches the browser. Takes the
Planner's plan and drives Playwright through the stored workflow's steps,
deciding each concrete browser action from the current page state rather
than following a fixed script, so the same stored workflow keeps working
even if a page's layout shifts slightly.

Runs on a pluggable LLMClient rather than a hardcoded provider: a single
exploration makes one model call per browser action across every step and
every broken-input attempt, so whichever model the user picked for a run
(Claude, Ollama, or both side by side) drives every one of those calls too -
if one action is slightly off, the loop guard and the step's action budget
catch it well before it does real damage.
"""

import json

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.agents.claude_client import ClaudeLLMClient
from app.agents.llm_client import LLMClient, LLMError
from app.agents.schema import ActionLogEntry, ExplorationResult, TestPlan
from app.browser import BrowserSession
from app.domains.manifest import load_domains

MAX_ACTIONS_PER_STEP = 6
MAX_IDENTICAL_ACTION_REPEATS = 2

_NAVIGATION_ONLY_PREFIXES = ("navigate to", "wait for")

_SNAPSHOT_JS = """
() => Array.from(document.querySelectorAll(
  'input, textarea, select, button, a[href], [role="button"]'
)).slice(0, 40).map((el) => ({
  tag: el.tagName.toLowerCase(),
  type: el.getAttribute('type'),
  id: el.id || null,
  name: el.getAttribute('name'),
  placeholder: el.getAttribute('placeholder'),
  text: (el.innerText || el.value || '').trim().slice(0, 60),
}))
"""


class ExplorerError(Exception):
    """Raised when exploration can't proceed - an unmatched/malformed plan,
    an unregistered domain, a step that never completes, or a detected
    action loop."""


class ExplorerAgent:
    def __init__(self, browser: BrowserSession | None = None, llm: LLMClient | None = None) -> None:
        self._browser = browser or BrowserSession()
        self._llm = llm or ClaudeLLMClient()

    @property
    def browser(self) -> BrowserSession:
        return self._browser

    async def explore(self, plan: TestPlan, close_browser: bool = True) -> ExplorationResult:
        """close_browser=False leaves the browser session open on completion
        (but always closes it if exploration fails) so the Verifier can
        re-check the result on the exact same live page/session instead of
        a fresh, logged-out one."""
        if not plan.matched or not plan.domain or not plan.workflow:
            raise ExplorerError("Explorer requires a matched plan with a domain and workflow.")

        domain = next((d for d in load_domains() if d.name == plan.domain), None)
        if domain is None:
            raise ExplorerError(f"Plan references unregistered domain {plan.domain!r}.")

        actions: list[ActionLogEntry] = []
        broken_input_done = False
        completed_ok = False

        await self._browser.start()
        try:
            await self._browser.page.goto(domain.base_url)

            for step in plan.steps:
                if not broken_input_done and self._is_interactive_step(step):
                    await self._attempt_broken_input(step, actions)
                    broken_input_done = True

                await self._execute_step(step, actions)

            final_text = await self._browser.page.evaluate("() => document.body.innerText")
            completed_ok = True
            return ExplorationResult(
                ticket_id=plan.ticket_id,
                domain=plan.domain,
                workflow=plan.workflow,
                completed=True,
                actions=actions,
                final_url=self._browser.page.url,
                final_page_text=final_text,
            )
        except ExplorerError as exc:
            return ExplorationResult(
                ticket_id=plan.ticket_id,
                domain=plan.domain,
                workflow=plan.workflow,
                completed=False,
                actions=actions,
                error=str(exc),
            )
        finally:
            if not (completed_ok and not close_browser):
                await self._browser.close()

    @staticmethod
    def _is_interactive_step(step: str) -> bool:
        return not step.strip().lower().startswith(_NAVIGATION_ONLY_PREFIXES)

    async def _snapshot(self) -> dict:
        page = self._browser.page
        elements = await page.evaluate(_SNAPSHOT_JS)
        return {"url": page.url, "title": await page.title(), "elements": elements}

    async def _execute_action(self, action: str, selector: str | None, value: str | None) -> tuple[bool, str | None]:
        page = self._browser.page
        # A model call can succeed but still omit a field the action actually
        # needs (e.g. "navigate" with no URL) - checked explicitly so a
        # missing field is a clean failed action, not a crash deep inside
        # Playwright over a required-but-missing positional argument.
        if action in ("fill", "click", "select", "press") and not selector:
            return False, f"Model returned {action!r} with no selector."
        if action == "navigate" and not value:
            return False, "Model returned 'navigate' with no URL."

        try:
            if action == "fill":
                await page.fill(selector, value or "")
            elif action == "click":
                await page.click(selector)
            elif action == "select":
                await page.select_option(selector, value)
            elif action == "press":
                await page.press(selector, value or "Enter")
            elif action == "navigate":
                await page.goto(value)
            else:
                return False, f"Unknown action type: {action!r}"
            return True, None
        except PlaywrightTimeoutError as exc:
            return False, f"Timed out waiting for {selector!r}: {exc}"
        except PlaywrightError as exc:
            return False, str(exc)

    async def _execute_step(self, step: str, actions: list[ActionLogEntry]) -> None:
        seen_signatures: dict[tuple, int] = {}

        for _ in range(MAX_ACTIONS_PER_STEP):
            snapshot = await self._snapshot()
            decision, _ = await self._llm.complete_json(self._step_prompt(step, snapshot))
            action = decision.get("action", "unknown")

            if action == "done":
                return

            selector = decision.get("selector")
            value = decision.get("value")
            signature = (action, selector, value)
            seen_signatures[signature] = seen_signatures.get(signature, 0) + 1
            if seen_signatures[signature] > MAX_IDENTICAL_ACTION_REPEATS:
                raise ExplorerError(
                    f"Explorer repeated the same action {seen_signatures[signature]} times "
                    f"on step {step!r} ({action} on {selector!r}) - stopping to avoid a loop."
                )

            success, error = await self._execute_action(action, selector, value)
            actions.append(
                ActionLogEntry(
                    step=step,
                    action=action,
                    selector=selector,
                    value=value,
                    reasoning=decision.get("reasoning"),
                    success=success,
                    error=error,
                )
            )

        raise ExplorerError(f"Explorer could not complete step {step!r} within {MAX_ACTIONS_PER_STEP} actions.")

    async def _attempt_broken_input(self, step: str, actions: list[ActionLogEntry]) -> None:
        snapshot = await self._snapshot()
        try:
            decision, _ = await self._llm.complete_json(self._broken_input_prompt(step, snapshot))
        except LLMError as exc:
            actions.append(
                ActionLogEntry(
                    step=step,
                    action="broken_input",
                    success=False,
                    error=str(exc),
                    is_broken_input_attempt=True,
                )
            )
            return

        action = decision.get("action", "unknown")
        selector = decision.get("selector")
        value = decision.get("value")
        success, error = await self._execute_action(action, selector, value)
        actions.append(
            ActionLogEntry(
                step=step,
                action=action,
                selector=selector,
                value=value,
                reasoning=decision.get("reasoning"),
                success=success,
                error=error,
                is_broken_input_attempt=True,
            )
        )

    def _step_prompt(self, step: str, snapshot: dict) -> str:
        return f"""You are driving a real browser through one step of a QA workflow.
This step is a human-written skeleton, not a fixed script - you must find and
use the real elements on the current page to carry it out.

Step: "{step}"

Current page:
URL: {snapshot["url"]}
Title: {snapshot["title"]}

Interactive elements on the page (tag, type, id, name, placeholder, visible text):
{json.dumps(snapshot["elements"], indent=2)}

Decide the single next browser action needed to make progress on this step,
using the real element info above to build the selector. Respond with ONLY a
JSON object, no other text, in exactly this shape:
{{"action": "fill"|"click"|"select"|"press"|"navigate"|"done", "selector": "<CSS selector, or null for navigate/done>", "value": "<text/URL/option value, or null>", "reasoning": "<one short sentence>"}}

Use "done" only once the current page already satisfies this step.
"""

    def _broken_input_prompt(self, step: str, snapshot: dict) -> str:
        return f"""You are deliberately testing INVALID input handling for one step of a
QA workflow, on purpose, before the step is attempted for real. This is
intentional negative testing, not a mistake.

Step you must attempt with a deliberately broken variation (an invalid
input, an empty required field, or a boundary value - pick whichever is most
meaningful for this specific step):
"{step}"

Current page:
URL: {snapshot["url"]}
Title: {snapshot["title"]}

Interactive elements on the page (tag, type, id, name, placeholder, visible text):
{json.dumps(snapshot["elements"], indent=2)}

Decide ONE browser action that deliberately uses broken input for this step.
Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"action": "fill"|"click"|"select"|"press", "selector": "<selector>", "value": "<deliberately invalid/empty value, or null>", "reasoning": "<what makes this input broken and what you expect to happen>"}}
"""
