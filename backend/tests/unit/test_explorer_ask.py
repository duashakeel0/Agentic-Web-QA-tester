"""Day 10 - Explorer.ask() on-demand Q&A mode. Reuses ExplorerAgent
rather than a separate agent (see explorer.py's ask() docstring), so
these tests live alongside the rest of test_explorer.py's fakes but in
their own file since ask() is a genuinely separate entry point from
explore()'s workflow-step loop.
"""

import pytest

from app.agents import explorer as explorer_module
from app.agents.explorer import ExplorerAgent
from app.agents.schema import ActionLogEntry, AskContext
from app.domains.schema import Domain
from tests.helpers import FakeLLM
from tests.unit.test_explorer import _FakeBrowserFull, _fake_action_success


@pytest.fixture(autouse=True)
def patch_manifest(monkeypatch):
    monkeypatch.setattr(
        explorer_module,
        "load_domains",
        lambda: [Domain(name="fake_domain", base_url="http://x/home", workflows=[])],
    )


async def test_ask_declines_an_unrecognized_domain():
    llm = FakeLLM(['{"matched": false, "reason": "No registered domain concerns pizza delivery."}'])
    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=llm)

    result = await agent.ask("Does this site deliver pizza?")

    assert result.matched is False
    assert result.answer is None
    assert "pizza" in result.reason
    assert fake_browser.started is False  # never touched the browser at all


async def test_ask_declines_when_matched_domain_is_not_in_the_real_manifest():
    # A hallucinated match (the model named something outside the real,
    # registered manifest) must be treated as unmatched, never trusted.
    llm = FakeLLM(['{"matched": true, "domain": "made_up_domain"}'])
    agent = ExplorerAgent(browser=_FakeBrowserFull(), llm=llm)

    result = await agent.ask("What products does this site sell?")

    assert result.matched is False
    assert "registered manifest" in result.reason


async def test_ask_answers_from_existing_context_without_browsing():
    # During/after a run: the richer context already collected answers
    # the question directly - re-exploring the same site moments later
    # would be wasteful and slower for no better an answer.
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fake_domain"}',
            "This site sells pliers, hammers, and wrenches, based on the search results observed.",
        ]
    )
    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=llm)
    context = AskContext(
        domain="fake_domain",
        final_url="http://x/search?q=pliers",
        final_page_text="Showing 1 result for 'pliers': Pliers - $12.99",
        actions=[
            ActionLogEntry(step="(ask)", action="fill", selector="#search", value="pliers", success=True),
        ],
    )

    result = await agent.ask("What did the search for pliers show?", existing_context=context)

    assert result.matched is True
    assert result.source == "existing_context"
    assert result.domain == "fake_domain"
    assert "pliers" in result.answer.lower()
    assert result.actions == []  # nothing browsed live - answered straight from the given context
    assert fake_browser.started is False


async def test_ask_ignores_existing_context_for_a_different_domain():
    # A live run's context for domain A must never answer a question
    # matched to domain B - only actually-relevant context counts as
    # "richer context already collected".
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fake_domain"}',
            '{"action": "answer", "answer": "The homepage lists three product categories."}',
        ]
    )
    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=llm)
    context = AskContext(domain="a_totally_different_domain", final_page_text="irrelevant")

    result = await agent.ask("What categories does this site have?", existing_context=context)

    assert result.source == "live_explore"
    assert fake_browser.started is True


async def test_ask_live_answers_immediately_when_the_first_page_is_enough():
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fake_domain"}',
            '{"action": "answer", "answer": "The homepage shows a login form with a username and password field."}',
        ]
    )
    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=llm)

    result = await agent.ask("What's on the homepage?")

    assert result.matched is True
    assert result.source == "live_explore"
    assert "login form" in result.answer
    assert result.actions == []  # answered without needing to take any browsing action
    assert fake_browser.started is True
    assert fake_browser.closed is True


async def test_ask_live_browses_before_answering():
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fake_domain"}',
            '{"action": "click", "selector": "#menu", "value": null, "reasoning": "open the menu to see categories"}',
            '{"action": "answer", "answer": "The menu lists Electronics, Clothing, and Home Goods."}',
        ]
    )
    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=llm)
    agent._execute_action = _fake_action_success

    result = await agent.ask("What categories are in the menu?")

    assert result.source == "live_explore"
    assert len(result.actions) == 1
    assert result.actions[0].action == "click"
    assert result.actions[0].success is True
    assert "Electronics" in result.answer


async def test_ask_live_falls_back_to_a_context_answer_when_the_budget_runs_out():
    # 4 browsing decisions (never "answer") exhaust ASK_MAX_ACTIONS -
    # still worth a best-effort answer from whatever was actually
    # observed rather than failing the whole question outright.
    llm = FakeLLM(
        [
            '{"matched": true, "domain": "fake_domain"}',
            *(
                '{"action": "click", "selector": "#x", "value": null, "reasoning": "keep looking"}'
                for _ in range(4)
            ),
            "Based on the pages visited, no clear answer was found for this question.",
        ]
    )
    fake_browser = _FakeBrowserFull()
    agent = ExplorerAgent(browser=fake_browser, llm=llm)
    agent._execute_action = _fake_action_success

    result = await agent.ask("Is there a loyalty program?")

    assert result.source == "live_explore"
    assert len(result.actions) == 4
    assert "no clear answer" in result.answer.lower()
