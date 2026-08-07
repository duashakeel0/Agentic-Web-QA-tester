import asyncio
import contextlib

import pytest

from app.agents import explorer as explorer_module
from app.agents.explorer import ExplorerAgent, ExplorerError
from app.agents.llm_client import LLMError
from app.agents.schema import ActionLogEntry, TestPlan
from app.domains.schema import Domain
from tests.helpers import FakeLLM

_SNAPSHOT_ELEMENTS = [
    {
        "tag": "input",
        "type": "text",
        "id": "user-name",
        "name": None,
        "placeholder": "Username",
        "text": "",
        "rect": {"x": 10, "y": 20, "width": 200, "height": 30},
    },
]


class _FakeBrowser:
    """Just enough of BrowserSession's shape for tests that never actually
    need a real page - _execute_action reads .page before its guard
    clauses run, so it must exist even when unused."""

    page = object()


class _FakeLocator:
    """Enough of Playwright's Locator to exercise _element_box - .first
    just returns itself (a single-match locator has no chaining to do),
    matching real Locator semantics closely enough for this."""

    def __init__(self, box: dict | None):
        self._box = box

    @property
    def first(self):
        return self

    async def bounding_box(self, timeout=None):
        return self._box


class _FakePage:
    def __init__(self, boxes: dict[str, dict | None] | None = None):
        self.viewport_size = {"width": 1280, "height": 720}
        self.screenshot_calls = 0
        self.url = "http://x"
        self._boxes = boxes or {}

    async def screenshot(self):
        self.screenshot_calls += 1
        return b"fake-png-bytes"

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self._boxes.get(selector))

    async def evaluate(self, _script):
        return ""

    async def title(self):
        return "t"


class _FakeBrowserWithScreenshot:
    """Enough of BrowserSession's shape to exercise _emit_action's
    screenshot capture without a real Playwright page."""

    def __init__(self, boxes: dict[str, dict | None] | None = None):
        self.page = _FakePage(boxes)


class _FakeBrowserFull:
    """Enough of BrowserSession's shape to run explore() end-to-end - not
    just _emit_action in isolation - without a real Playwright browser.
    start/goto/close all just flip flags/fields."""

    def __init__(self):
        self.started = False
        self.closed = False
        self.page = _FakePage()

    async def start(self):
        self.started = True

    async def goto(self, url):
        self.page.url = url
        return "t"

    async def close(self):
        self.closed = True


@pytest.fixture
def explorer():
    return ExplorerAgent(browser=_FakeBrowser(), llm=FakeLLM())


async def test_execute_step_stops_on_done(explorer):
    explorer._llm.queue('{"action": "fill", "selector": "#user", "value": "bob", "reasoning": "fill it"}')
    explorer._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')
    explorer._snapshot = _fake_snapshot
    explorer._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await explorer._execute_step("Fill username", actions)

    assert len(actions) == 1
    assert actions[0].action == "fill"
    assert actions[0].success is True


async def test_execute_step_treats_navigate_to_current_url_as_done(explorer):
    # Reproduces the Sauce Demo login loop: a weaker model re-issues
    # "navigate" to the exact page it's already on instead of answering
    # "done" - should complete the step instead of looping/raising.
    for _ in range(3):
        explorer._llm.queue(
            '{"action": "navigate", "selector": null, "value": "https://www.saucedemo.com/", "reasoning": "go there"}'
        )

    async def _snapshot_at_saucedemo():
        return {"url": "https://www.saucedemo.com/", "title": "t", "elements": []}

    explorer._snapshot = _snapshot_at_saucedemo
    explorer._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await explorer._execute_step("Navigate to saucedemo.com", actions)

    assert actions == []


async def test_execute_step_reinterprets_navigate_with_selector_as_click(explorer):
    # Reproduces the the_internet/dropdown loop: model repeats
    # {"action": "navigate", "selector": "a[text()='Dropdown']", "value": null}
    # 3x (invalid - navigate needs a URL) instead of clicking the link -
    # should resolve the XPath-ish selector and click it instead of raising.
    explorer._llm.queue('{"action": "navigate", "selector": "a[text()=\'Dropdown\']", "value": null, "reasoning": "go"}')
    explorer._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')
    explorer._snapshot = _fake_snapshot
    clicked: list[tuple] = []

    async def _fake_execute(action, selector, value):
        clicked.append((action, selector, value))
        return True, None

    explorer._execute_action = _fake_execute

    actions: list[ActionLogEntry] = []
    await explorer._execute_step("Navigate to /dropdown", actions)

    assert clicked == [("click", 'text="Dropdown"', None)]
    assert actions[0].action == "click"
    assert actions[0].selector == 'text="Dropdown"'
    assert actions[0].success is True


async def test_execute_step_rejects_fill_on_a_navigation_only_step(explorer):
    # Reproduces a real Toolshop failure: step 1 is "Navigate to
    # /auth/login" (navigation-only - told not to interact with anything),
    # but the model filled the page's search bar with the login email
    # instead of issuing a real "navigate". A fill can never satisfy a
    # navigation-only step regardless of which element it targets, so it
    # should be rejected as a failed attempt (not executed against a real,
    # unrelated element) and the next decision should get a real navigate.
    explorer._llm.queue(
        '{"action": "fill", "selector": "#search", "value": "customer@example.com", "reasoning": "search for it"}'
    )
    explorer._llm.queue(
        '{"action": "navigate", "selector": null, "value": "https://x/auth/login", "reasoning": "go there"}'
    )
    explorer._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')
    explorer._snapshot = _fake_snapshot
    executed: list[tuple] = []

    async def _fake_execute(action, selector, value):
        executed.append((action, selector, value))
        return True, None

    explorer._execute_action = _fake_execute

    actions: list[ActionLogEntry] = []
    await explorer._execute_step("Navigate to /auth/login", actions)

    # The fill was never actually attempted against the real page - only
    # the subsequent, valid navigate was.
    assert executed == [("navigate", None, "https://x/auth/login")]
    assert actions[0].action == "fill"
    assert actions[0].success is False
    assert "cannot satisfy a navigation-only step" in actions[0].error
    assert actions[1].action == "navigate"
    assert actions[1].success is True


def test_resolve_selector_normalizes_xpath_text_pattern():
    assert ExplorerAgent._resolve_selector("a[text()='Dropdown']", []) == 'text="Dropdown"'
    assert ExplorerAgent._resolve_selector("a:contains('Dropdown')", []) == 'text="Dropdown"'


async def test_execute_step_raises_after_repeating_same_failing_action(explorer):
    # Same action/selector/value every time, and it keeps FAILING - a
    # genuinely stuck step, never "done" - should hit the loop guard.
    for _ in range(10):
        explorer._llm.queue('{"action": "click", "selector": "#x", "value": null, "reasoning": "again"}')
    explorer._snapshot = _fake_snapshot
    explorer._execute_action = _fake_action_failure

    with pytest.raises(ExplorerError, match="repeated the same action"):
        await explorer._execute_step("Click something", [])


async def test_execute_step_completes_when_repeating_an_already_succeeded_action(explorer):
    # Reproduces a real Toolshop login failure: the model filled the Email
    # field successfully, then re-issued the exact same fill 2 more times
    # instead of recognizing the step was already done (a fast/weaker
    # model especially) - should complete gracefully after the first
    # success instead of raising once the identical-action guard would
    # otherwise trip, since nothing was ever actually stuck/failing.
    for _ in range(3):
        explorer._llm.queue(
            '{"action": "fill", "selector": "#email", "value": "customer@example.com", "reasoning": "fill it"}'
        )
    explorer._snapshot = _fake_snapshot
    explorer._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await explorer._execute_step("Enter the email", actions)

    # Only the first attempt was ever actually executed - the repeat(s)
    # were recognized as redundant and treated as implicit completion
    # instead of being re-attempted or tripping the loop guard.
    assert len(actions) == 1
    assert actions[0].success is True


async def test_execute_step_raises_after_max_actions_without_done(explorer):
    from app.agents import explorer as explorer_module

    for i in range(explorer_module.MAX_ACTIONS_PER_STEP):
        explorer._llm.queue(f'{{"action": "click", "selector": "#btn{i}", "value": null, "reasoning": "try"}}')
    explorer._snapshot = _fake_snapshot
    explorer._execute_action = _fake_action_success

    with pytest.raises(ExplorerError, match="within .* actions"):
        await explorer._execute_step("Click something", [])


async def test_execute_step_resolves_bare_id_selector(explorer):
    # Ollama-style near-miss: echoes the element's bare id instead of a
    # real CSS selector - should resolve to "#user-name", not fail/hang.
    explorer._llm.queue('{"action": "fill", "selector": "user-name", "value": "bob", "reasoning": "fill it"}')
    explorer._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')

    async def _snapshot_with_elements():
        return {"url": "http://x", "title": "t", "elements": _SNAPSHOT_ELEMENTS}

    explorer._snapshot = _snapshot_with_elements
    explorer._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await explorer._execute_step("Fill username", actions)

    assert actions[0].selector == "#user-name"


def test_resolve_selector_normalizes_bare_id():
    resolved = ExplorerAgent._resolve_selector("user-name", _SNAPSHOT_ELEMENTS)
    assert resolved == "#user-name"


def test_resolve_selector_leaves_real_css_selector_alone():
    resolved = ExplorerAgent._resolve_selector("#already-a-selector", _SNAPSHOT_ELEMENTS)
    assert resolved == "#already-a-selector"


def test_resolve_selector_leaves_unmatched_selector_alone():
    resolved = ExplorerAgent._resolve_selector("nonexistent", _SNAPSHOT_ELEMENTS)
    assert resolved == "nonexistent"


def test_resolve_selector_corrects_wrong_case_bare_id_selector():
    # Reproduces a real Toolshop failure: the model wrote "#Email" (echoing
    # the human-readable "Email field" label's capitalization) instead of
    # the real snapshot id "email" - CSS id selectors are case-sensitive,
    # so that guess always fails outright even though it's clearly meant
    # to be this exact element.
    elements = [{"tag": "input", "type": "email", "id": "email", "name": None, "placeholder": "Email", "text": ""}]
    resolved = ExplorerAgent._resolve_selector("#Email", elements)
    assert resolved == "#email"


def test_resolve_selector_leaves_exact_case_bare_id_selector_alone():
    resolved = ExplorerAgent._resolve_selector("#user-name", _SNAPSHOT_ELEMENTS)
    assert resolved == "#user-name"


def test_resolve_selector_leaves_bare_id_alone_when_no_case_insensitive_match():
    # "#already-a-selector" isn't a near-miss of anything in the snapshot -
    # no element to correct it to, so it's left exactly as given rather
    # than guessed at.
    resolved = ExplorerAgent._resolve_selector("#already-a-selector", _SNAPSHOT_ELEMENTS)
    assert resolved == "#already-a-selector"


async def test_emit_action_sends_screenshot_and_target_box(tmp_path, monkeypatch):
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))
    events: list[dict] = []

    async def on_action(event: dict) -> None:
        events.append(event)

    fake_browser = _FakeBrowserWithScreenshot(boxes={"#user-name": {"x": 10, "y": 20, "width": 200, "height": 30}})
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM(), on_action=on_action)
    agent._llm.queue('{"action": "fill", "selector": "user-name", "value": "bob", "reasoning": "fill it"}')
    agent._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')

    async def _snapshot_with_elements():
        return {"url": "http://x", "title": "t", "elements": _SNAPSHOT_ELEMENTS}

    agent._snapshot = _snapshot_with_elements
    agent._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await agent._execute_step("Fill username", actions)

    assert fake_browser.page.screenshot_calls == 1
    assert len(events) == 1
    event = events[0]
    assert event["action"] == "fill"
    assert event["selector"] == "#user-name"
    assert event["success"] is True
    assert event["screenshot_url"].startswith("/screenshots/actions/")
    assert event["target_box"] == {"x": 10, "y": 20, "width": 200, "height": 30}
    assert event["viewport"] == {"width": 1280, "height": 720}
    assert actions[0].screenshot_path == event["screenshot_url"]
    # A normal action must never be mistaken for a deliberate broken-input
    # probe downstream - the live view would wrongly show it as a neutral
    # "testing invalid input" tag instead of a real pass/fail.
    assert event["is_broken_input_attempt"] is False


async def test_attempt_broken_input_emits_live_event_flagged_as_probe(tmp_path, monkeypatch):
    # The live-view fix for the false-alarm-red-fail bug: a deliberate
    # broken-input probe (expected to fail/be rejected) must carry
    # is_broken_input_attempt=True all the way into the emitted live event,
    # not just onto the persisted ActionLogEntry - otherwise the frontend
    # has no way to tell it apart from a genuine failed action.
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))
    events: list[dict] = []

    async def on_action(event: dict) -> None:
        events.append(event)

    fake_browser = _FakeBrowserWithScreenshot()
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM(), on_action=on_action)
    agent._llm.queue('{"action": "fill", "selector": "#search", "value": "", "reasoning": "try empty input"}')
    agent._snapshot = _fake_snapshot
    agent._execute_action = _fake_action_failure

    actions: list[ActionLogEntry] = []
    await agent._attempt_broken_input("Fill username", actions)

    assert len(events) == 1
    assert events[0]["is_broken_input_attempt"] is True
    assert actions[0].is_broken_input_attempt is True


async def test_emit_action_is_noop_without_listener(tmp_path, monkeypatch):
    # explorer fixture's browser.page is a bare object() with no
    # .screenshot() - if _emit_action didn't bail out immediately when
    # there's no on_action listener, this would blow up with an
    # AttributeError instead of just skipping quietly.
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))
    fake_browser = _FakeBrowser()
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM())
    agent._llm.queue('{"action": "fill", "selector": "#user-name", "value": "bob", "reasoning": "fill it"}')
    agent._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')
    agent._snapshot = _fake_snapshot
    agent._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await agent._execute_step("Fill username", actions)

    assert actions[0].screenshot_path is None


async def test_emit_action_failure_does_not_break_the_step(tmp_path, monkeypatch):
    # A live-view/report side effect (screenshot capture, the on_action
    # callback itself) must never fail the actual QA test it's reporting on.
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))

    async def broken_on_action(event: dict) -> None:
        raise RuntimeError("websocket send failed")

    fake_browser = _FakeBrowserWithScreenshot()
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM(), on_action=broken_on_action)
    agent._llm.queue('{"action": "fill", "selector": "#user-name", "value": "bob", "reasoning": "fill it"}')
    agent._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')
    agent._snapshot = _fake_snapshot
    agent._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await agent._execute_step("Fill username", actions)

    assert actions[0].success is True
    assert actions[0].screenshot_path is None


async def test_element_box_queries_the_live_page_locator():
    # Not a snapshot lookup - it asks Playwright directly for whatever
    # selector currently resolves to, so it works for any selector shape
    # (text=, class, attribute), not just the bare #id/[name] case a
    # hand-rolled snapshot match would catch.
    fake_browser = _FakeBrowserWithScreenshot(boxes={"text=\"Dropdown\"": {"x": 5, "y": 6, "width": 7, "height": 8}})
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM())
    box = await agent._element_box('text="Dropdown"')
    assert box == {"x": 5, "y": 6, "width": 7, "height": 8}


async def test_element_box_none_for_selectorless_action():
    agent = ExplorerAgent(browser=_FakeBrowserWithScreenshot(), llm=FakeLLM())
    assert await agent._element_box(None) is None


async def test_element_box_none_when_selector_matches_nothing():
    agent = ExplorerAgent(browser=_FakeBrowserWithScreenshot(boxes={}), llm=FakeLLM())
    assert await agent._element_box("#gone") is None


async def test_execute_step_recovers_from_llm_error(explorer):
    # A transient model failure (Ollama slow/unreachable) on one action
    # should be recorded and retried, not crash the whole step.
    explorer._llm.queue(LLMError("ollama unreachable"))
    explorer._llm.queue('{"action": "done", "selector": null, "value": null, "reasoning": "done"}')
    explorer._snapshot = _fake_snapshot
    explorer._execute_action = _fake_action_success

    actions: list[ActionLogEntry] = []
    await explorer._execute_step("Fill username", actions)

    assert len(actions) == 1
    assert actions[0].success is False
    assert "ollama unreachable" in actions[0].error


async def test_broken_input_llmerror_is_logged_not_raised(explorer):
    explorer._llm.queue(LLMError("ollama unreachable"))
    explorer._snapshot = _fake_snapshot

    actions: list[ActionLogEntry] = []
    await explorer._attempt_broken_input("Submit form", actions)

    assert len(actions) == 1
    assert actions[0].success is False
    assert "ollama unreachable" in actions[0].error
    assert actions[0].is_broken_input_attempt is True


async def test_execute_action_rejects_missing_selector(explorer):
    success, error = await explorer._execute_action("click", None, None)
    assert success is False
    assert "no selector" in error


async def test_execute_action_rejects_missing_navigate_url(explorer):
    success, error = await explorer._execute_action("navigate", None, None)
    assert success is False
    assert "no URL" in error


def test_is_interactive_step():
    assert ExplorerAgent._is_interactive_step("Navigate to /login") is False
    assert ExplorerAgent._is_interactive_step("Wait for the page to load") is False
    assert ExplorerAgent._is_interactive_step("Click the login button") is True


async def test_explore_requires_matched_plan(explorer):
    plan = TestPlan(ticket_id="T1", matched=False)
    with pytest.raises(ExplorerError, match="matched plan"):
        await explorer.explore(plan)


async def test_explore_requires_registered_domain(explorer):
    plan = TestPlan(ticket_id="T1", matched=True, domain="not_a_real_domain", workflow="w", steps=["a step"])
    with pytest.raises(ExplorerError, match="unregistered domain"):
        await explorer.explore(plan)


async def _fake_snapshot():
    return {"url": "http://x", "title": "t", "elements": []}


async def _fake_action_success(action, selector, value):
    return True, None


async def _fake_action_failure(action, selector, value):
    return False, "element not found"


async def test_live_frame_loop_emits_periodic_untagged_frame_events(tmp_path, monkeypatch):
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.setattr(explorer_module, "LIVE_FRAME_INTERVAL_S", 0)

    events: list[dict] = []

    async def on_action(event: dict) -> None:
        events.append(event)

    agent = ExplorerAgent(browser=_FakeBrowserWithScreenshot(), llm=FakeLLM(), on_action=on_action)

    task = asyncio.ensure_future(agent._live_frame_loop())
    for _ in range(200):
        if len(events) >= 3:
            break
        await asyncio.sleep(0)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert len(events) >= 3
    for event in events:
        # A live tick is purely visual - it never carries the
        # step/action/selector/target_box fields a discrete action event
        # does, so it can't accidentally get treated as one downstream.
        assert event["kind"] == "frame"
        assert event["screenshot_url"].startswith("/screenshots/actions/")
        assert "step" not in event
        assert "target_box" not in event


async def test_live_frame_loop_swallows_capture_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.setattr(explorer_module, "LIVE_FRAME_INTERVAL_S", 0)

    async def broken_on_action(event: dict) -> None:
        raise RuntimeError("websocket send failed")

    agent = ExplorerAgent(browser=_FakeBrowserWithScreenshot(), llm=FakeLLM(), on_action=broken_on_action)

    task = asyncio.ensure_future(agent._live_frame_loop())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    # The whole point of the try/except inside the loop - a listener that
    # raises must not blow up the background task or the exploration it
    # runs alongside.
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_explore_runs_live_frame_loop_alongside_steps_and_cancels_it(tmp_path, monkeypatch):
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.setattr(explorer_module, "LIVE_FRAME_INTERVAL_S", 0.01)
    monkeypatch.setattr(
        explorer_module,
        "load_domains",
        lambda: [Domain(name="fake_domain", base_url="http://x", workflows=[])],
    )

    events: list[dict] = []

    async def on_action(event: dict) -> None:
        events.append(event)

    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM(), on_action=on_action)

    async def _slow_execute_step(step, actions):
        await asyncio.sleep(0.05)

    async def _noop_broken_input(step, actions):
        return None

    agent._execute_step = _slow_execute_step
    agent._attempt_broken_input = _noop_broken_input

    plan = TestPlan(ticket_id="T1", matched=True, domain="fake_domain", workflow="w", steps=["Do something"])

    result = await agent.explore(plan)

    assert result.completed is True
    assert fake_browser.closed is True
    frame_events = [e for e in events if e.get("kind") == "frame"]
    # The interval is short and a step deliberately stalls for 50ms, giving
    # the background loop room to tick at least once - proving it actually
    # ran concurrently, not just that it was created and immediately
    # cancelled without doing anything.
    assert len(frame_events) >= 1
    assert frame_events[0]["screenshot_url"].startswith("/screenshots/actions/")


async def test_explore_skips_llm_call_for_redundant_first_navigate_step(monkeypatch):
    # Reproduces a real ParaBank failure: step 1 is "Navigate to the
    # ParaBank homepage", but explore() already goto()'d domain.base_url
    # before the step loop starts - so the browser's already there with
    # zero actions taken. A weaker model (llama3.2) sometimes ignores the
    # nav_hint telling it not to interact here and invents a click on a
    # selector that doesn't exist (e.g. "#home"), which only ever times
    # out. Should be skipped deterministically, with no model call at all.
    monkeypatch.setattr(
        explorer_module,
        "load_domains",
        lambda: [Domain(name="fake_domain", base_url="http://x/home", workflows=[])],
    )

    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM())

    executed_steps: list[str] = []

    async def _recording_execute_step(step, actions):
        executed_steps.append(step)

    async def _noop_broken_input(step, actions):
        return None

    agent._execute_step = _recording_execute_step
    agent._attempt_broken_input = _noop_broken_input

    plan = TestPlan(
        ticket_id="T1",
        matched=True,
        domain="fake_domain",
        workflow="w",
        steps=["Navigate to the homepage", "Click the login button"],
    )

    result = await agent.explore(plan)

    assert result.completed is True
    # The redundant first step never reached _execute_step (so never made
    # an LLM call) - only the genuinely interactive second step did.
    assert executed_steps == ["Click the login button"]


async def test_explore_does_not_skip_first_step_when_not_yet_at_base_url(monkeypatch):
    # The skip only applies when the browser is already exactly where the
    # step wants it - if goto() landed somewhere else (a redirect, a
    # different starting page), the step still needs a real decision.
    monkeypatch.setattr(
        explorer_module,
        "load_domains",
        lambda: [Domain(name="fake_domain", base_url="http://x/home", workflows=[])],
    )

    class _RedirectingBrowser(_FakeBrowserFull):
        async def goto(self, url):
            self.page.url = "http://x/redirected"
            return "t"

    fake_browser = _RedirectingBrowser()
    agent = ExplorerAgent(browser=fake_browser, llm=FakeLLM())

    executed_steps: list[str] = []

    async def _recording_execute_step(step, actions):
        executed_steps.append(step)

    agent._execute_step = _recording_execute_step
    agent._attempt_broken_input = _recording_execute_step

    plan = TestPlan(ticket_id="T1", matched=True, domain="fake_domain", workflow="w", steps=["Navigate to the homepage"])

    await agent.explore(plan)

    assert executed_steps == ["Navigate to the homepage"]
