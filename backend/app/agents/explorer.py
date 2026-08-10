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

import asyncio
import contextlib
import json
import logging
import os
import re
import uuid
from collections.abc import Awaitable, Callable

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.agents.claude_client import ClaudeLLMClient
from app.agents.llm_client import LLMClient, LLMError
from app.agents.schema import ActionLogEntry, AskContext, AskResult, ExplorationResult, TestPlan
from app.browser import BrowserSession
from app.domains.manifest import load_domains

logger = logging.getLogger(__name__)

# Called with one dict per browser action (live view + report material) -
# never allowed to affect whether exploration itself succeeds or fails,
# see _emit_action.
ActionCallback = Callable[[dict], Awaitable[None]]

# Screenshots served straight off disk by main.py's /screenshots static
# mount - kept separate from verifier.py's SCREENSHOT_DIR (one overwritten
# failure shot per run) since this is one file per action, per run.
ACTION_SCREENSHOT_DIR = "reports/screenshots/actions"
_UNSAFE_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]+")

MAX_ACTIONS_PER_STEP = 6
MAX_IDENTICAL_ACTION_REPEATS = 2
# How often the background live-frame loop grabs a screenshot, independent
# of the discrete per-action captures below. Discrete actions alone can be
# seconds apart while the model "thinks" or a page loads, which reads as a
# frozen still image rather than a live camera; this fills the gaps so the
# live view keeps updating continuously like real video monitoring.
LIVE_FRAME_INTERVAL_S = 0.75
# Playwright's default actionability timeout is 30s - fine for a real,
# slow-loading element, but ruinous for a hallucinated/invalid selector
# (the loop guard already caps an exploration at MAX_ACTIONS_PER_STEP
# attempts, but at the default timeout a bad step could still burn minutes
# waiting on failures that were never going to resolve). Kept short enough
# that a real element still has time to appear.
ACTION_TIMEOUT_MS = 5000
NAVIGATE_TIMEOUT_MS = 15000
# Decisions are one short JSON object with a one-sentence reasoning field,
# but 200, then 600, both proved too tight in practice - Claude sometimes
# spends part of the budget on brief internal reasoning before the actual
# JSON, cutting the response off with no text content at all. Past just
# costing an extra retry, this has a worse failure mode under tight
# budgets: a short decision ("done") fits where a longer one ("fill" with
# a selector/value/reasoning) doesn't, so truncation can systematically
# bias the model toward falsely claiming a step is done rather than
# actually completing it - confirmed on a real ParaBank run where a
# required field was silently never filled this way, correctly failing
# the real site's own form validation. 1200 leaves real headroom.
DECISION_MAX_TOKENS = 1200
# An ask-mode question isn't a workflow with known steps - it's bounded by
# a small action budget instead, since a plain-English question should
# only ever need a couple of clicks (open a menu, follow a link) to find
# its answer, not a full multi-step workflow's worth of browsing.
ASK_MAX_ACTIONS = 4

_NAVIGATION_ONLY_PREFIXES = ("navigate to", "wait for")
# A selector starting with any of these is already a real CSS selector
# (id/class/attribute/combinator) and left alone by _resolve_selector.
_CSS_SELECTOR_PREFIX_CHARS = ("#", ".", "[", "*", ">", "~", "+", ":")
# Ollama's Llama 3.1 sometimes writes an XPath-style text match where a CSS
# selector is expected - a[text()='Dropdown'] or a:contains('Dropdown') -
# which isn't valid CSS/Playwright syntax and never matches anything. The
# *intent* (match by visible text) is real, though, and maps directly onto
# Playwright's own text= selector engine.
_XPATH_TEXT_PATTERN = re.compile(r"""text\(\)\s*=\s*['"]([^'"]+)['"]""")
_CONTAINS_TEXT_PATTERN = re.compile(r"""contains\([^,)]*,?\s*['"]([^'"]+)['"]\s*\)""")
# Matches only a plain "#some-id" selector - not "#foo .bar", "#foo[x=y]",
# or anything more elaborate - since only this simple shape is safe to
# rewrite by matching against a single element's real id.
_BARE_ID_SELECTOR_PATTERN = re.compile(r"^#([\w-]+)$")

_SNAPSHOT_JS = """
() => Array.from(document.querySelectorAll(
  'input, textarea, select, button, a[href], [role="button"]'
)).slice(0, 25).map((el) => {
  const r = el.getBoundingClientRect();
  return {
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type'),
    id: el.id || null,
    name: el.getAttribute('name'),
    placeholder: el.getAttribute('placeholder'),
    text: (el.innerText || el.value || '').trim().slice(0, 60),
    // Viewport-relative, matching a non-full-page page.screenshot() 1:1 -
    // what lets the live view draw a box over exactly the element a
    // decision acted on.
    rect: { x: r.x, y: r.y, width: r.width, height: r.height },
  };
})
"""


def _safe_filename(raw: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", raw)[:120]


class ExplorerError(Exception):
    """Raised when exploration can't proceed - an unmatched/malformed plan,
    an unregistered domain, a step that never completes, or a detected
    action loop."""


class ExplorerAgent:
    def __init__(
        self,
        browser: BrowserSession | None = None,
        llm: LLMClient | None = None,
        on_action: ActionCallback | None = None,
    ) -> None:
        self._browser = browser or BrowserSession()
        self._llm = llm or ClaudeLLMClient()
        self._on_action = on_action
        self._action_index = 0
        self._live_frame_index = 0
        self._run_key = "run"

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
        self._action_index = 0
        self._live_frame_index = 0
        # Namespaces screenshot filenames so a concurrent "compare both" run
        # (same ticket/domain/workflow, two providers at once) never has one
        # provider's screenshots overwrite the other's.
        self._run_key = _safe_filename(f"{plan.ticket_id}_{plan.domain}_{plan.workflow}_{self._llm.provider}")

        await self._browser.start()
        # Runs alongside the whole exploration below, only when someone's
        # actually listening for live frames - a dashboard-less/report-only
        # run (e.g. Trello-triggered) has no on_action, so there's no point
        # burning screenshot IO for a live view nobody's watching.
        frame_task = asyncio.create_task(self._live_frame_loop()) if self._on_action is not None else None
        try:
            # BrowserSession.goto(), not page.goto() directly - it already
            # waits on "domcontentloaded" instead of "load", which is what
            # makes real-world sites that never cleanly fire "load" work.
            await self._browser.goto(domain.base_url)
            await self._emit_action(
                step="(start)", action="page_loaded", selector=None, value=domain.base_url, success=True, error=None
            )

            for index, step in enumerate(plan.steps):
                if (
                    index == 0
                    and not self._is_interactive_step(step)
                    and self._same_url(self._browser.page.url, domain.base_url)
                ):
                    # The goto() above already put the browser on
                    # domain.base_url - a first step that's just asking to
                    # be "on the homepage"/navigated to that same page is
                    # therefore already satisfied, deterministically, with
                    # no model call needed at all. Skips a weaker model
                    # sometimes ignoring the nav_hint instruction not to
                    # interact here and inventing an unnecessary click
                    # instead (e.g. a hallucinated, nonexistent "#home"
                    # selector that only ever times out).
                    continue

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
            if frame_task is not None:
                frame_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await frame_task
            if not (completed_ok and not close_browser):
                await self._browser.close()

    async def ask(
        self,
        question: str,
        existing_context: AskContext | None = None,
        close_browser: bool = True,
    ) -> AskResult:
        """On-demand Q&A mode - Day 10's "Ask the Site" search bar. Answers
        a plain-English question about a known domain instead of running a
        stored workflow toward a pass/fail assertion, reusing the same
        domain manifest, browser session, and snapshot/selector/action
        machinery explore() uses rather than being a separate, simpler
        lookup - an accurate answer needs real page context, not a guess
        from the domain's name alone. An unrecognized domain is declined
        outright, the same "don't guess" principle the Planner already
        applies when a ticket doesn't clearly match anything registered.

        existing_context, when given and for the same domain the question
        matches, skips live browsing entirely and answers from what a
        live/just-finished run already observed - re-exploring a site
        that was just explored moments ago to answer a question about it
        would be wasteful and slower for no better an answer.
        """
        match = await self._match_domain_for_question(question)
        if not match.get("matched"):
            return AskResult(
                question=question, matched=False,
                reason=match.get("reason", "No domain knowledge for this target."),
            )

        domain = next((d for d in load_domains() if d.name == match.get("domain")), None)
        if domain is None:
            # The model named something outside the real manifest - treat
            # this as unmatched rather than trusting a hallucinated result.
            return AskResult(
                question=question, matched=False,
                reason="Model matched to a domain that isn't in the registered manifest.",
            )

        if existing_context is not None and existing_context.domain == domain.name:
            answer = await self._answer_from_context(question, existing_context)
            return AskResult(
                question=question, matched=True, domain=domain.name, answer=answer,
                source="existing_context", final_url=existing_context.final_url,
            )

        return await self._ask_live(question, domain, close_browser=close_browser)

    async def _match_domain_for_question(self, question: str) -> dict:
        manifest_summary = [
            {"domain": d.name, "base_url": d.base_url, "workflows": [w.name for w in d.workflows]}
            for d in load_domains()
        ]

        prompt = f"""You are matching a free-form question to one known, registered domain.

Registered domains (this is the COMPLETE list - nothing else is known to this system):
{json.dumps(manifest_summary, indent=2)}

Question: "{question}"

Decide which registered domain this question is asking about, based on the question's
wording and any URL/site name mentioned. If the question does not clearly concern one of
the registered domains above, you MUST say it doesn't match - never guess or substitute
the closest one.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"matched": true, "domain": "<domain name>"}}
or
{{"matched": false, "reason": "<short reason>"}}
"""
        try:
            data, _ = await self._llm.complete_json(prompt, max_tokens=200)
            return data
        except LLMError as exc:
            return {"matched": False, "reason": str(exc)}

    async def _answer_from_context(self, question: str, context: AskContext) -> str:
        actions_summary = (
            "\n".join(
                f'- {a.action} on {a.selector!r} with {a.value!r} -> '
                f'{"succeeded" if a.success else f"FAILED: {a.error}"}'
                for a in context.actions
            )
            or "(no actions recorded)"
        )
        prompt = f"""You are answering a question about a site using ONLY what was actually
observed during a recent automated run - if the answer isn't in this data, say so
plainly instead of guessing.

Final page reached: {context.final_url}
Final page text (truncated): {(context.final_page_text or "")[:2000]}

Actions taken during the run:
{actions_summary}

Question: {question}

Answer in 2-4 plain sentences, no other text.
"""
        try:
            response = await self._llm.complete(prompt, max_tokens=300, timeout=20)
            return response.text
        except LLMError as exc:
            return f"Could not generate an answer: {exc}"

    async def _ask_live(self, question: str, domain, close_browser: bool) -> AskResult:
        actions: list[ActionLogEntry] = []
        self._action_index = 0
        self._live_frame_index = 0
        self._run_key = _safe_filename(f"ask_{domain.name}_{self._llm.provider}_{uuid.uuid4().hex[:8]}")

        await self._browser.start()
        frame_task = asyncio.create_task(self._live_frame_loop()) if self._on_action is not None else None
        try:
            await self._browser.goto(domain.base_url)
            await self._emit_action(
                step="(ask)", action="page_loaded", selector=None, value=domain.base_url, success=True, error=None
            )

            answer: str | None = None
            for _ in range(ASK_MAX_ACTIONS):
                snapshot = await self._snapshot()
                try:
                    decision, _ = await self._llm.complete_json(
                        self._ask_prompt(question, snapshot, actions), max_tokens=DECISION_MAX_TOKENS
                    )
                except LLMError as exc:
                    actions.append(ActionLogEntry(step="(ask)", action="unknown", success=False, error=str(exc)))
                    continue

                if decision.get("action") == "answer":
                    answer = decision.get("answer") or "The agent didn't provide a clear answer."
                    break

                action = decision.get("action", "unknown")
                selector = self._resolve_selector(decision.get("selector"), snapshot["elements"])
                value = decision.get("value")
                success, error = await self._execute_action(action, selector, value)
                screenshot_url = await self._emit_action(
                    step="(ask)", action=action, selector=selector, value=value, success=success, error=error
                )
                actions.append(
                    ActionLogEntry(
                        step="(ask)", action=action, selector=selector, value=value,
                        reasoning=decision.get("reasoning"), success=success, error=error,
                        screenshot_path=screenshot_url,
                    )
                )

            if answer is None:
                # Budget exhausted without the model ever answering
                # directly - still worth a best-effort answer from
                # whatever was actually observed along the way, rather
                # than failing the whole question outright.
                final_text = await self._browser.page.evaluate("() => document.body.innerText")
                answer = await self._answer_from_context(
                    question,
                    AskContext(
                        domain=domain.name, final_url=self._browser.page.url,
                        final_page_text=final_text, actions=actions,
                    ),
                )

            return AskResult(
                question=question, matched=True, domain=domain.name, answer=answer,
                source="live_explore", final_url=self._browser.page.url, actions=actions,
            )
        finally:
            if frame_task is not None:
                frame_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await frame_task
            if close_browser:
                await self._browser.close()

    def _ask_prompt(self, question: str, snapshot: dict, actions_so_far: list[ActionLogEntry]) -> str:
        history = ""
        if actions_so_far:
            done_list = "\n".join(
                f'- {a.action} on {a.selector!r} with {a.value!r} -> '
                f'{"succeeded" if a.success else f"FAILED: {a.error}"}'
                for a in actions_so_far
            )
            history = f"""
Actions already taken while looking for the answer, in order:
{done_list}
"""

        return f"""You are answering a plain-English question about a real, live site by
browsing it - not by guessing. You may take ONE browsing action to find more
information (e.g. open a menu, follow a link, search for something), or answer
now if the current page already has what you need.

Question: "{question}"
{history}
Current page:
URL: {snapshot["url"]}
Title: {snapshot["title"]}

Interactive elements on the page (tag, type, id, name, placeholder, visible text):
{json.dumps(snapshot["elements"], indent=2)}

If you can answer the question now from what you've seen, respond with:
{{"action": "answer", "answer": "<your answer in 2-4 plain sentences, grounded only in what you actually observed>"}}

Otherwise, take one browsing action to find out more. The selector must be a real CSS
selector, not a bare id/name string - if an element's "id" is "search", the selector is
"#search", NOT "search". Never use XPath syntax like [text()='X'] or :contains('X') - to
match by visible text use Playwright's own syntax instead: text="X".
Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"action": "fill"|"click"|"select"|"press"|"navigate", "selector": "<CSS selector, or null for navigate>", "value": "<text/URL/option value, or null>", "reasoning": "<one short sentence>"}}
"""

    @staticmethod
    def _is_interactive_step(step: str) -> bool:
        return not step.strip().lower().startswith(_NAVIGATION_ONLY_PREFIXES)

    async def _snapshot(self) -> dict:
        page = self._browser.page
        elements = await page.evaluate(_SNAPSHOT_JS)
        return {"url": page.url, "title": await page.title(), "elements": elements}

    @staticmethod
    def _same_url(a: str, b: str) -> bool:
        return a.rstrip("/") == b.rstrip("/")

    @staticmethod
    def _resolve_selector(selector: str | None, elements: list[dict]) -> str | None:
        """A weaker model (Ollama's local Llama 3.1 especially) sometimes
        echoes an element's bare id/name straight from the snapshot instead
        of building a real CSS selector from it - "user-name" instead of
        "#user-name" - which then fails or times out against a real page
        even though the model clearly meant that exact element. Matched
        against the same snapshot the model was shown, so a near-miss like
        that still resolves to the right element instead of failing the
        action outright.
        """
        if not selector:
            return selector
        candidate = selector.strip()
        if not candidate:
            return selector

        text_match = _XPATH_TEXT_PATTERN.search(candidate) or _CONTAINS_TEXT_PATTERN.search(candidate)
        if text_match:
            return f'text="{text_match.group(1)}"'

        bare_id_match = _BARE_ID_SELECTOR_PATTERN.match(candidate)
        if bare_id_match:
            id_part = bare_id_match.group(1)
            if not any(element.get("id") == id_part for element in elements):
                for element in elements:
                    el_id = element.get("id")
                    if el_id and el_id.lower() == id_part.lower():
                        # A model sometimes echoes the human-readable field
                        # label's capitalization ("#Email", from "the Email
                        # field") instead of the real id it was shown in the
                        # snapshot ("email") - CSS id selectors are
                        # case-sensitive, so that guess always fails
                        # outright even though it's clearly meant to be
                        # this exact element. Corrected to the real casing.
                        return f"#{el_id}"
            return selector

        if candidate.startswith(_CSS_SELECTOR_PREFIX_CHARS) or " " in candidate:
            return selector
        for element in elements:
            if element.get("id") == candidate:
                return f"#{candidate}"
        for element in elements:
            if element.get("name") == candidate:
                return f'[name="{candidate}"]'
        return selector

    async def _element_box(self, selector: str | None) -> dict | None:
        """The live bounding box of whatever `selector` currently resolves
        to on the real page, queried straight through Playwright rather
        than cross-referenced against the snapshot list - works for every
        selector shape the model can produce (#id, class, attribute,
        Playwright's own text= engine, nested combinators), not just a
        bare id/name lookup. None for a selector-less action or one that
        matches nothing (already gone, hidden, or never existed)."""
        if not selector:
            return None
        try:
            box = await self._browser.page.locator(selector).first.bounding_box(timeout=1000)
        except PlaywrightError:
            return None
        if box is None:
            return None
        return {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]}

    async def _emit_action(
        self,
        *,
        step: str,
        action: str,
        selector: str | None,
        value: str | None,
        success: bool,
        error: str | None,
        is_broken_input_attempt: bool = False,
    ) -> str | None:
        """Best-effort live-view/report material for one action: a
        screenshot saved to disk (served by main.py's /screenshots mount,
        and what the PDF report + ReportCard embed later, via the returned
        URL) plus a bounding box for whatever element the action targeted.
        Wrapped in one broad try/except on purpose - a screenshot failure
        (page mid-navigation, browser closing, disk full) must never fail
        the actual QA test, which is the entire point of this being a side
        channel and not part of the real action-execution path above.
        Returns the screenshot's URL (for ActionLogEntry.screenshot_path),
        or None if there's no on_action listener or capture failed."""
        if self._on_action is None:
            return None
        try:
            screenshot_bytes = await self._browser.page.screenshot()
            self._action_index += 1
            filename = f"{self._run_key}_{self._action_index:03d}.png"
            os.makedirs(ACTION_SCREENSHOT_DIR, exist_ok=True)
            with open(os.path.join(ACTION_SCREENSHOT_DIR, filename), "wb") as f:
                f.write(screenshot_bytes)
            screenshot_url = f"/screenshots/actions/{filename}"
            viewport = self._browser.page.viewport_size
            await self._on_action(
                {
                    "kind": "action",
                    "step": step,
                    "action": action,
                    "selector": selector,
                    "value": value,
                    "success": success,
                    "error": error,
                    "screenshot_url": screenshot_url,
                    "target_box": await self._element_box(selector),
                    "viewport": viewport,
                    "is_broken_input_attempt": is_broken_input_attempt,
                }
            )
            return screenshot_url
        except Exception:
            logger.exception("Failed to capture/emit a live action frame - continuing without it.")
            return None

    async def _live_frame_loop(self) -> None:
        """Continuously emits a screenshot at a fixed interval, independent
        of the discrete per-action captures above - what gives the live
        view a genuinely video-like, always-updating feed instead of one
        that only jumps at each browser action (which can be seconds apart
        while the model "thinks" or a page loads). Runs as a background
        task alongside the step loop for the lifetime of one exploration
        and is cancelled by explore() once it ends."""
        while True:
            await asyncio.sleep(LIVE_FRAME_INTERVAL_S)
            try:
                screenshot_bytes = await self._browser.page.screenshot()
                self._live_frame_index += 1
                filename = f"{self._run_key}_live_{self._live_frame_index:04d}.png"
                os.makedirs(ACTION_SCREENSHOT_DIR, exist_ok=True)
                with open(os.path.join(ACTION_SCREENSHOT_DIR, filename), "wb") as f:
                    f.write(screenshot_bytes)
                await self._on_action(
                    {
                        "kind": "frame",
                        "screenshot_url": f"/screenshots/actions/{filename}",
                        "viewport": self._browser.page.viewport_size,
                    }
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Live frame capture failed - continuing without it.", exc_info=True)

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
                await page.fill(selector, value or "", timeout=ACTION_TIMEOUT_MS)
            elif action == "click":
                await page.click(selector, timeout=ACTION_TIMEOUT_MS)
            elif action == "select":
                await page.select_option(selector, value, timeout=ACTION_TIMEOUT_MS)
            elif action == "press":
                await page.press(selector, value or "Enter", timeout=ACTION_TIMEOUT_MS)
            elif action == "navigate":
                await page.goto(value, wait_until="domcontentloaded", timeout=NAVIGATE_TIMEOUT_MS)
            else:
                return False, f"Unknown action type: {action!r}"
            return True, None
        except PlaywrightTimeoutError as exc:
            return False, f"Timed out waiting for {selector!r}: {exc}"
        except PlaywrightError as exc:
            return False, str(exc)

    async def _execute_step(self, step: str, actions: list[ActionLogEntry]) -> None:
        seen_signatures: dict[tuple, int] = {}
        step_actions: list[ActionLogEntry] = []

        for _ in range(MAX_ACTIONS_PER_STEP):
            snapshot = await self._snapshot()
            try:
                decision, _ = await self._llm.complete_json(
                    self._step_prompt(step, snapshot, step_actions), max_tokens=DECISION_MAX_TOKENS
                )
            except LLMError as exc:
                # A transient model failure (Ollama slow/unreachable for one
                # call, an unparseable response) shouldn't blow up the whole
                # exploration - recorded as a failed "attempt" like any other
                # so it counts against the step's action budget and the next
                # loop iteration gets a fresh chance instead of crashing out.
                screenshot_url = await self._emit_action(
                    step=step, action="unknown", selector=None, value=None, success=False, error=str(exc)
                )
                entry = ActionLogEntry(
                    step=step, action="unknown", success=False, error=str(exc), screenshot_path=screenshot_url
                )
                actions.append(entry)
                step_actions.append(entry)
                continue
            action = decision.get("action", "unknown")

            if action == "done":
                return

            value = decision.get("value")
            if action == "navigate" and value and self._same_url(value, snapshot["url"]):
                # The model asked to navigate to the page it's already on -
                # for a navigation-only step that IS "done", just phrased as
                # a navigate. Told to answer "done" directly in this case
                # (see the nav_hint in _step_prompt), but a weaker model
                # (Ollama's) doesn't reliably follow that and instead
                # re-issues the same no-op navigate call every time,
                # tripping the identical-action loop guard below. Checked
                # deterministically here so the step still completes
                # regardless of whether the model phrases it correctly.
                return

            selector = self._resolve_selector(decision.get("selector"), snapshot["elements"])

            if action == "navigate" and not value and selector:
                # The model gave "navigate" a selector instead of a URL -
                # almost always means "follow this link" rather than a URL
                # it forgot to build, and executing it as a literal
                # navigate always fails outright (no URL). Reinterpreted as
                # a click on that same element instead of failing the exact
                # same malformed decision 3 times in a row and tripping the
                # loop guard below over something a click would've handled.
                action = "click"

            if not self._is_interactive_step(step) and action in ("fill", "select", "press"):
                # A navigation-only step (see nav_hint in _step_prompt) is
                # asking to be on a different page, not to interact with
                # anything currently on this one - "fill"/"select"/"press"
                # can never accomplish that regardless of which element
                # they target (only "navigate" or "click"-a-link can), so
                # one here is always wrong, not just usually wrong. Most
                # commonly shows up as typing real values into whatever
                # text input the page happens to have (a search bar), which
                # this rejects deterministically instead of letting
                # Playwright actually type into it - fed back as a failed
                # attempt (not silently dropped) so the next decision sees
                # exactly why and which action types are actually valid here.
                error = (
                    f"{action!r} cannot satisfy a navigation-only step - "
                    "use 'navigate' with a full URL, or 'click' a link, instead."
                )
                screenshot_url = await self._emit_action(
                    step=step, action=action, selector=selector, value=value, success=False, error=error
                )
                entry = ActionLogEntry(
                    step=step,
                    action=action,
                    selector=selector,
                    value=value,
                    reasoning=decision.get("reasoning"),
                    success=False,
                    error=error,
                    screenshot_path=screenshot_url,
                )
                actions.append(entry)
                step_actions.append(entry)
                continue

            if any(a.action == action and a.selector == selector and a.value == value and a.success for a in step_actions):
                # The model re-issued an action that already succeeded
                # earlier this step instead of recognizing the step is
                # done - e.g. re-filling the same field with the same
                # value repeatedly rather than answering "done" (told to
                # in the prompt/history above, but a weaker or
                # speed-optimized model doesn't always follow it). The
                # field's already in that state; repeating it again can
                # only ever be a no-op, so it's treated as implicit
                # completion instead of burning the action budget or
                # eventually tripping the loop guard below into a hard
                # failure over something that was never actually stuck.
                return

            signature = (action, selector, value)
            seen_signatures[signature] = seen_signatures.get(signature, 0) + 1
            if seen_signatures[signature] > MAX_IDENTICAL_ACTION_REPEATS:
                raise ExplorerError(
                    f"Explorer repeated the same action {seen_signatures[signature]} times "
                    f"on step {step!r} ({action} on {selector!r}) - stopping to avoid a loop."
                )

            success, error = await self._execute_action(action, selector, value)
            screenshot_url = await self._emit_action(
                step=step,
                action=action,
                selector=selector,
                value=value,
                success=success,
                error=error,
            )
            entry = ActionLogEntry(
                step=step,
                action=action,
                selector=selector,
                value=value,
                reasoning=decision.get("reasoning"),
                success=success,
                error=error,
                screenshot_path=screenshot_url,
            )
            actions.append(entry)
            step_actions.append(entry)

            if success and action == "click" and not self._same_url(self._browser.page.url, snapshot["url"]):
                # A successful click that actually navigated to a new page
                # almost always means the step's real-world goal (submit a
                # form, follow a link, log in) was just achieved - looping
                # back to the model hands it a brand-new page it was never
                # asked about, and a weaker model can mistake an unrelated
                # element there for something it still needs to click. Real
                # case this reproduces: a successful ParaBank login click
                # landed on the Accounts Overview page, which has its own
                # "Log Out" link - Llama took that as something to act on
                # next and clicked it, undoing the login it had just
                # completed. Checked deterministically rather than relying
                # on the model reliably answering "done" itself once the
                # goal's already met.
                return

        raise ExplorerError(f"Explorer could not complete step {step!r} within {MAX_ACTIONS_PER_STEP} actions.")

    async def _attempt_broken_input(self, step: str, actions: list[ActionLogEntry]) -> None:
        snapshot = await self._snapshot()
        try:
            decision, _ = await self._llm.complete_json(
                self._broken_input_prompt(step, snapshot), max_tokens=DECISION_MAX_TOKENS
            )
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
        selector = self._resolve_selector(decision.get("selector"), snapshot["elements"])
        value = decision.get("value")
        success, error = await self._execute_action(action, selector, value)
        screenshot_url = await self._emit_action(
            step=step,
            action=action,
            selector=selector,
            value=value,
            success=success,
            error=error,
            is_broken_input_attempt=True,
        )
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
                screenshot_path=screenshot_url,
            )
        )

    def _step_prompt(self, step: str, snapshot: dict, step_actions: list[ActionLogEntry]) -> str:
        nav_hint = ""
        if not self._is_interactive_step(step):  # pure navigation/wait step
            nav_hint = """
This step needs no form interaction - it's only asking to be on the right
page or for something to have finished loading, nothing more. If the current
URL/page state above already satisfies it, respond with "done" immediately.
Do NOT fill in, click, or otherwise interact with any form or element on the
page for this step, even if the page shows a login form or other inputs -
those belong to a later step, not this one.
"""
        history = ""
        if step_actions:
            done_list = "\n".join(
                f'- {a.action} on {a.selector!r} with {a.value!r} -> {"succeeded" if a.success else f"FAILED: {a.error}"}'
                for a in step_actions
            )
            history = f"""
Actions already taken THIS step, in order - do not repeat one that already
succeeded, the field/element is already in that state even if it's not
obviously reflected below:
{done_list}
"""

        return f"""You are driving a real browser through one step of a QA workflow.
This step is a human-written skeleton, not a fixed script - you must find and
use the real elements on the current page to carry it out.

Step: "{step}"
{nav_hint}{history}
Current page:
URL: {snapshot["url"]}
Title: {snapshot["title"]}

Interactive elements on the page (tag, type, id, name, placeholder, visible text):
{json.dumps(snapshot["elements"], indent=2)}

Decide the single next browser action needed to make progress on this step,
using the real element info above to build the selector. The selector must
be a real CSS selector, not a bare id/name string - if an element's "id" is
"user-name", the selector is "#user-name", NOT "user-name". Never use XPath
syntax like [text()='X'] or :contains('X') - they are not valid CSS; to
match by visible text use Playwright's own syntax instead: text="X".

"navigate" is ONLY for typing a full URL directly (selector must be null,
value must be the complete URL). To follow a link that's already on the
page, use "click" with that link's selector instead - never "navigate"
with a selector and no URL.

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"action": "fill"|"click"|"select"|"press"|"navigate"|"done", "selector": "<CSS selector, e.g. '#user-name', or null for navigate/done>", "value": "<text/URL/option value, or null>", "reasoning": "<one short sentence>"}}

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
The selector must be a real CSS selector, not a bare id/name string - if an
element's "id" is "user-name", the selector is "#user-name", NOT "user-name".
Never use XPath syntax like [text()='X'] or :contains('X') - they are not
valid CSS; to match by visible text use Playwright's own syntax instead:
text="X". Respond with ONLY a JSON object, no other text, in exactly this
shape:
{{"action": "fill"|"click"|"select"|"press", "selector": "<CSS selector, e.g. '#user-name'>", "value": "<deliberately invalid/empty value, or null>", "reasoning": "<what makes this input broken and what you expect to happen>"}}
"""
