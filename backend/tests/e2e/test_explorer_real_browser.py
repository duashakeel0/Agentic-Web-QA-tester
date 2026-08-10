"""The one real Playwright E2E test: drives an actual Chromium browser
through a real HTML fixture using the real BrowserSession/ExplorerAgent/
VerifierAgent code, only the LLM decision is scripted (via FakeLLM) since
the point here is to prove the browser-automation stack itself is
correct, not to re-verify model behavior already covered by the mocked
unit tests.
"""

import pytest

from app.agents.explorer import ExplorerAgent
from app.agents.schema import TestPlan
from app.agents.verifier import VerifierAgent
from app.browser import BrowserSession
from tests.helpers import FakeLLM

pytestmark = pytest.mark.e2e


async def test_real_browser_auto_accepts_a_confirm_dialog_on_submit(fixture_server):
    # Reproduces a real quirk on Automation Exercise's Contact Us form:
    # submission is gated behind a native confirm() dialog. Unhandled,
    # Playwright auto-cancels it, so the click reports success but the
    # page never reaches its actual result - a real assertion then fails
    # for a reason that has nothing to do with the workflow being wrong.
    session = BrowserSession()
    await session.start()
    try:
        await session.goto(f"{fixture_server}/confirm_dialog_form.html")
        await session.page.fill("#message", "hello")
        await session.page.click("#submit-btn")
        await session.page.wait_for_selector("#success", state="visible", timeout=5000)
        text = await session.page.evaluate("() => document.body.innerText")
        assert "Success! Your details have been submitted successfully." in text
    finally:
        await session.close()


async def test_real_browser_catches_a_fill_that_silently_gets_cleared(fixture_server):
    # Reproduces a real Toolshop login failure: the email field was
    # logged as filled successfully, but by the time Login was clicked
    # the page showed "Email is required" - the fill's own JS-side
    # validation/re-render had silently cleared it afterward, with no
    # exception for Playwright to ever catch on its own. Without a
    # read-back check, _execute_action would report this as a clean
    # success purely because fill() itself didn't throw.
    session = BrowserSession()
    await session.start()
    agent = ExplorerAgent(browser=session, llm=FakeLLM())
    try:
        await session.goto(f"{fixture_server}/self_clearing_field.html")

        success, error = await agent._execute_action("fill", "#email", "customer@example.com")

        assert success is False
        assert "didn't stick" in error
        assert "#email" in error
    finally:
        await session.close()


def _plan(base_url_placeholder_domain: str) -> TestPlan:
    return TestPlan(
        ticket_id="E2E-1",
        matched=True,
        domain=base_url_placeholder_domain,
        workflow="login",
        steps=["Enter a valid username and password", "Click the Login button"],
        expected_outcome={"text_contains": "Welcome, standard_user"},
    )


async def test_real_browser_completes_a_real_login_flow(fixture_server, monkeypatch):
    from app.domains import manifest
    from app.domains.schema import Domain, ExpectedOutcome, Workflow

    fixture_domain = Domain(
        name="fixture_login_site",
        base_url=f"{fixture_server}/login_page.html",
        workflows=[
            Workflow(
                name="login",
                steps=["Enter a valid username and password", "Click the Login button"],
                expected_outcome=ExpectedOutcome(text_contains="Welcome, standard_user"),
            )
        ],
    )
    monkeypatch.setattr(manifest, "load_domains", lambda: [fixture_domain])
    monkeypatch.setattr("app.agents.explorer.load_domains", lambda: [fixture_domain])

    llm = FakeLLM(
        [
            # step 1: fill username
            '{"action": "fill", "selector": "#username", "value": "standard_user", "reasoning": "fill username"}',
            # step 1: fill password, then done
            '{"action": "fill", "selector": "#password", "value": "secret_sauce", "reasoning": "fill password"}',
            '{"action": "done", "selector": null, "value": null, "reasoning": "both fields filled"}',
            # step 2: click login
            '{"action": "click", "selector": "#login-btn", "reasoning": "submit the form"}',
            '{"action": "done", "selector": null, "value": null, "reasoning": "submitted"}',
        ]
    )
    explorer = ExplorerAgent(llm=llm)
    plan = _plan("fixture_login_site")

    exploration = await explorer.explore(plan, close_browser=False)

    try:
        assert exploration.completed is True, exploration.error
        assert exploration.error is None
        assert all(a.success for a in exploration.actions), exploration.actions
        assert "Welcome, standard_user" in (exploration.final_page_text or "")

        verifier = VerifierAgent(llm=FakeLLM(["Login succeeded - the welcome message appeared."]))
        verdict = await verifier.verify(plan.expected_outcome, exploration, browser=explorer.browser)

        assert verdict.verdict == "pass"
        assert verdict.initial_check_passed is True
    finally:
        await explorer.browser.close()


async def test_real_browser_reports_failure_for_wrong_credentials(fixture_server, monkeypatch):
    from app.domains import manifest
    from app.domains.schema import Domain, ExpectedOutcome, Workflow

    fixture_domain = Domain(
        name="fixture_login_site",
        base_url=f"{fixture_server}/login_page.html",
        workflows=[
            Workflow(
                name="login",
                steps=["Enter a valid username and password", "Click the Login button"],
                expected_outcome=ExpectedOutcome(text_contains="Welcome, standard_user"),
            )
        ],
    )
    monkeypatch.setattr(manifest, "load_domains", lambda: [fixture_domain])
    monkeypatch.setattr("app.agents.explorer.load_domains", lambda: [fixture_domain])

    llm = FakeLLM(
        [
            '{"action": "fill", "selector": "#username", "value": "wrong_user", "reasoning": "fill username"}',
            '{"action": "fill", "selector": "#password", "value": "wrong_pass", "reasoning": "fill password"}',
            '{"action": "done", "selector": null, "value": null, "reasoning": "filled"}',
            '{"action": "click", "selector": "#login-btn", "reasoning": "submit"}',
            '{"action": "done", "selector": null, "value": null, "reasoning": "submitted"}',
        ]
    )
    explorer = ExplorerAgent(llm=llm)
    plan = _plan("fixture_login_site")

    exploration = await explorer.explore(plan, close_browser=False)

    try:
        assert exploration.completed is True
        # Wrong credentials -> the fixture's JS never swaps in the welcome
        # text, so a real assertion check against the real page correctly
        # catches this as a failure - not a scripted/mocked "fail". The
        # explanation LLM is still faked (deterministic, no network) since
        # that call itself is already covered by the mocked unit tests.
        verifier = VerifierAgent(llm=FakeLLM(["The welcome message never appeared - wrong credentials."]))
        verdict = await verifier.verify(plan.expected_outcome, exploration, browser=explorer.browser)

        assert verdict.verdict == "fail"
        assert verdict.initial_check_passed is False
    finally:
        await explorer.browser.close()
