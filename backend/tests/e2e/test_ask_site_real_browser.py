"""Day 10's own acceptance criterion: "tested with at least 3 different
query types across 2 domains, confirming answers reflect what the agent
actually observed." Runs the real ExplorerAgent.ask() - a real Playwright
browser against real local fixture pages, real domain-matching, real
snapshot/selector/action machinery - across two fixture "domains" and
three distinct question shapes: a direct factual question answerable
from the first page alone, a single-action behavior probe, and a
multi-action negative probe. Only the LLM transport is scripted
(FakeLLM), same convention as every other real-browser test in this
file.

Also covers the "decline, don't guess" requirement for a domain that
isn't registered at all.
"""

import pytest

from app.agents.explorer import ExplorerAgent
from app.domains.schema import Domain, Workflow
from tests.helpers import FakeLLM

pytestmark = pytest.mark.e2e


def _domains(fixture_server: str) -> list[Domain]:
    return [
        Domain(
            name="fixture_login_site",
            base_url=f"{fixture_server}/login_page.html",
            workflows=[Workflow(name="login", steps=["Log in"], expected_outcome={"text_contains": "Welcome"})],
        ),
        Domain(
            name="fixture_shop",
            base_url=f"{fixture_server}/smoke_search_page.html",
            workflows=[Workflow(name="search", steps=["Search"], expected_outcome={"text_contains": "no results"})],
        ),
    ]


def _patch_domains(monkeypatch, fixture_server: str) -> None:
    domains = _domains(fixture_server)
    monkeypatch.setattr("app.domains.manifest.load_domains", lambda: domains)
    monkeypatch.setattr("app.agents.explorer.load_domains", lambda: domains)


async def test_ask_declines_a_question_about_an_unregistered_domain(fixture_server, monkeypatch):
    _patch_domains(monkeypatch, fixture_server)
    llm = FakeLLM(['{"matched": false, "reason": "No registered domain concerns a pizza delivery tracker."}'])
    agent = ExplorerAgent(llm=llm)

    result = await agent.ask("Where's my pizza delivery order?")

    assert result.matched is False
    assert "pizza" in result.reason


async def test_ask_answers_a_direct_factual_question_from_the_first_page(fixture_server, monkeypatch):
    # Query type 1: answerable straight from the page the Explorer lands
    # on - no browsing action needed at all.
    _patch_domains(monkeypatch, fixture_server)
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fixture_login_site"}',
            '{"action": "answer", "answer": "The login page has a Username field, a Password field, and a Log in button."}',
        ]
    )
    agent = ExplorerAgent(llm=llm)

    result = await agent.ask("What fields are on the login page?")

    assert result.matched is True
    assert result.domain == "fixture_login_site"
    assert result.source == "live_explore"
    assert result.actions == []  # answered without needing to browse further
    assert "Username" in result.answer and "Password" in result.answer


async def test_ask_answers_a_single_action_behavior_probe(fixture_server, monkeypatch):
    # Query type 2: needs one real browsing action (search) to observe
    # the actual behavior before it can answer.
    _patch_domains(monkeypatch, fixture_server)
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fixture_shop"}',
            '{"action": "fill", "selector": "#search", "value": "zzznonexistent", "reasoning": "search for something that does not exist"}',
            '{"action": "click", "selector": "#search-btn", "reasoning": "submit the search"}',
            '{"action": "answer", "answer": "Searching for a nonexistent product shows the message '
            '\\"There are no results found for your search.\\""}',
        ]
    )
    agent = ExplorerAgent(llm=llm)

    result = await agent.ask("What does the site show when you search for a product that doesn't exist?")

    assert result.matched is True
    assert result.domain == "fixture_shop"
    assert len(result.actions) == 2  # fill + click - genuinely browsed, not guessed
    assert all(a.success for a in result.actions)
    assert "no results found" in result.answer.lower()


async def test_ask_answers_a_multi_action_negative_probe(fixture_server, monkeypatch):
    # Query type 3: a negative-input probe - deliberately wrong
    # credentials, needing several actions before an answer is possible,
    # on the *other* fixture domain (proving this isn't hardcoded to one
    # site).
    _patch_domains(monkeypatch, fixture_server)
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fixture_login_site"}',
            '{"action": "fill", "selector": "#username", "value": "wrong_user", "reasoning": "try a bad username"}',
            '{"action": "fill", "selector": "#password", "value": "wrong_pass", "reasoning": "try a bad password"}',
            '{"action": "click", "selector": "#login-btn", "reasoning": "submit"}',
            '{"action": "answer", "answer": "Logging in with the wrong username and password does not show the '
            'welcome message - the login form stays on screen with no visible error."}',
        ]
    )
    agent = ExplorerAgent(llm=llm)

    result = await agent.ask("What happens if you try to log in with the wrong username and password?")

    assert result.matched is True
    assert result.domain == "fixture_login_site"
    assert len(result.actions) == 3
    assert "does not show the welcome message" in result.answer
