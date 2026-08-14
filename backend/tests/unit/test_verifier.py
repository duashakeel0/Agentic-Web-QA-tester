import pytest

from app.agents.llm_client import LLMError
from app.agents.schema import ActionLogEntry, ExplorationResult
from app.agents.verifier import VerifierAgent
from tests.helpers import FakeLLM


@pytest.fixture
def verifier():
    return VerifierAgent(llm=FakeLLM())


def _exploration(**overrides):
    defaults = dict(
        ticket_id="T1", domain="practice_software_testing", workflow="login", completed=True,
        actions=[], final_url="https://x/inventory.html", final_page_text="Products",
    )
    defaults.update(overrides)
    return ExplorationResult(**defaults)


async def test_verify_passes_when_assertion_matches(verifier):
    verifier._llm.queue("Login succeeded and landed on the inventory page.")
    result = _exploration()

    verdict = await verifier.verify({"url_contains": "/inventory.html", "text_contains": "Products"}, result)

    assert verdict.verdict == "pass"
    assert verdict.initial_check_passed is True
    assert verdict.retried is False
    assert verdict.explanation_status == "ok"


async def test_verify_passes_with_issues_when_actions_failed_but_end_state_is_correct(verifier):
    verifier._llm.queue("Login succeeded after one retry on a slow field.")
    failed_action = ActionLogEntry(step="Fill username", action="fill", selector="#u", success=False, error="timed out")
    result = _exploration(actions=[failed_action])

    verdict = await verifier.verify({"url_contains": "/inventory.html", "text_contains": "Products"}, result)

    assert verdict.verdict == "pass_with_issues"
    assert verdict.warning_count == 1


async def test_verify_ignores_unknown_action_failures_for_pass_with_issues(verifier):
    # Reproduces the real complaint this fixes: a retry caused by our own
    # agent's LLM-decision hiccup (recorded as action="unknown" - no real
    # action was ever attempted against the site) isn't evidence the site
    # under test has a real issue, and shouldn't demote an otherwise clean
    # pass. Distinct from a genuine site-side flake (a real Playwright
    # timeout on an actual click/fill), which still correctly counts.
    verifier._llm.queue("Login succeeded with no real issues.")
    llm_hiccup = ActionLogEntry(
        step="Click Submit", action="unknown", success=False,
        error="claude returned an unparseable response",
    )
    result = _exploration(actions=[llm_hiccup])

    verdict = await verifier.verify({"url_contains": "/inventory.html", "text_contains": "Products"}, result)

    assert verdict.verdict == "pass"
    assert verdict.warning_count == 0


async def test_verify_ignores_broken_input_probes_for_pass_with_issues(verifier):
    verifier._llm.queue("Login succeeded; the deliberate bad-input probe correctly failed.")
    probe = ActionLogEntry(
        step="Fill username", action="fill", selector="#u", success=False, error="empty value rejected",
        is_broken_input_attempt=True,
    )
    result = _exploration(actions=[probe])

    verdict = await verifier.verify({"url_contains": "/inventory.html", "text_contains": "Products"}, result)

    assert verdict.verdict == "pass"
    assert verdict.warning_count == 0


async def test_verify_fails_and_retries_when_no_browser_or_url_given(verifier):
    verifier._llm.queue("The login never redirected.")
    # final_url=None with browser=None takes the fast "nothing to re-check
    # against" path rather than actually launching a real browser - a real
    # re-check against a live page/session is covered by the E2E test.
    result = _exploration(final_url=None, final_page_text="Invalid credentials")

    verdict = await verifier.verify({"url_contains": "/inventory.html"}, result, browser=None)

    assert verdict.verdict == "fail"
    assert verdict.initial_check_passed is False
    assert verdict.retried is True
    assert verdict.retry_error == "No final URL to re-check."


async def test_verify_skips_check_when_exploration_not_completed(verifier):
    result = _exploration(completed=False, final_url=None, final_page_text=None, error="Explorer timed out.")

    verdict = await verifier.verify({"url_contains": "/inventory.html"}, result)

    assert verdict.verdict == "fail"
    assert verdict.explanation == "Explorer timed out."
    assert verdict.explanation_status == "skipped"


async def test_explain_retries_once_then_inconclusive(verifier):
    verifier._llm.queue(LLMError("timeout 1"))
    verifier._llm.queue(LLMError("timeout 2"))
    result = _exploration()

    text, status = await verifier._explain({"text_contains": "Products"}, result, passed=False)

    assert text is None
    assert status == "inconclusive"
    assert len(verifier._llm.prompts) == 2


async def test_explain_skipped_when_no_llm_configured():
    verifier = VerifierAgent(llm=None)
    verifier._llm = None
    result = _exploration()

    text, status = await verifier._explain({}, result, passed=True)

    assert text is None
    assert status == "skipped"


def test_check_assertion_requires_all_present_fields():
    check = VerifierAgent._check_assertion
    assert check({"url_contains": "/x"}, "https://site/x", "any text") is True
    assert check({"url_contains": "/x"}, "https://site/y", "any text") is False
    assert check({"text_contains": "Products"}, "https://site", "Products page") is True
    assert check({"text_contains": "Products"}, "https://site", "Nope") is False
    assert check({}, None, None) is True


def test_check_assertion_text_contains_is_case_insensitive():
    # Reproduces a real Toolshop false FAIL: the YAML's expected_outcome
    # writes "No results" (capital N), but the real page's text reads
    # "...there are no results." (lowercase, mid-sentence) - the assertion
    # is clearly satisfied and shouldn't fail a run over capitalization.
    check = VerifierAgent._check_assertion
    assert check({"text_contains": "No results"}, "https://site", "There are no results.") is True
    assert check({"text_contains": "no results"}, "https://site", "THERE ARE NO RESULTS.") is True
    assert check({"text_contains": "No results"}, "https://site", "Everything matched fine") is False


def test_check_assertion_url_contains_stays_case_sensitive():
    # Unlike text_contains, a URL's exact casing can be meaningful (path
    # segments, slugs) - only the human-readable text assertion should be
    # forgiving of capitalization.
    check = VerifierAgent._check_assertion
    assert check({"url_contains": "/Inventory"}, "https://site/inventory", "text") is False
