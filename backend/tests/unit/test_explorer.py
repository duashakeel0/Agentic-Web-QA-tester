import pytest

from app.agents import explorer as explorer_module
from app.agents.explorer import ExplorerAgent, ExplorerError
from app.agents.llm_client import LLMError
from app.agents.schema import ActionLogEntry, TestPlan
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


class _FakePage:
    def __init__(self):
        self.viewport_size = {"width": 1280, "height": 720}
        self.screenshot_calls = 0

    async def screenshot(self):
        self.screenshot_calls += 1
        return b"fake-png-bytes"


class _FakeBrowserWithScreenshot:
    """Enough of BrowserSession's shape to exercise _emit_action's
    screenshot capture without a real Playwright page."""

    def __init__(self):
        self.page = _FakePage()


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


def test_resolve_selector_normalizes_xpath_text_pattern():
    assert ExplorerAgent._resolve_selector("a[text()='Dropdown']", []) == 'text="Dropdown"'
    assert ExplorerAgent._resolve_selector("a:contains('Dropdown')", []) == 'text="Dropdown"'


async def test_execute_step_raises_after_repeating_same_action(explorer):
    # Same action/selector/value every time - never "done" - should hit the loop guard.
    for _ in range(10):
        explorer._llm.queue('{"action": "click", "selector": "#x", "value": null, "reasoning": "again"}')
    explorer._snapshot = _fake_snapshot
    explorer._execute_action = _fake_action_success

    with pytest.raises(ExplorerError, match="repeated the same action"):
        await explorer._execute_step("Click something", [])


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


async def test_emit_action_sends_screenshot_and_target_box(tmp_path, monkeypatch):
    monkeypatch.setattr(explorer_module, "ACTION_SCREENSHOT_DIR", str(tmp_path))
    events: list[dict] = []

    async def on_action(event: dict) -> None:
        events.append(event)

    fake_browser = _FakeBrowserWithScreenshot()
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


def test_element_box_matches_resolved_selector():
    box = ExplorerAgent._element_box("#user-name", _SNAPSHOT_ELEMENTS)
    assert box == {"x": 10, "y": 20, "width": 200, "height": 30}


def test_element_box_none_for_selectorless_action():
    assert ExplorerAgent._element_box(None, _SNAPSHOT_ELEMENTS) is None


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
