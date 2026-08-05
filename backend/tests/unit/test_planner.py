import pytest

from app.agents.planner import PlannerAgent, PlannerError
from tests.helpers import FakeLLM


@pytest.fixture
def planner():
    return PlannerAgent(llm=FakeLLM())


async def test_match_domain_returns_parsed_json(planner):
    planner._llm.queue('{"matched": true, "domain": "sauce_demo", "workflow": "login"}')
    match = await planner._match_domain({"title": "Test login", "description": "desc"})
    assert match == {"matched": True, "domain": "sauce_demo", "workflow": "login"}


async def test_match_domain_unparseable_raises_plannererror(planner):
    planner._llm.queue("not json")
    with pytest.raises(PlannerError):
        await planner._match_domain({"title": "t", "description": "d"})


async def test_plan_end_to_end_matched(monkeypatch, planner):
    async def fake_get_ticket(ticket_id):
        return {"title": "Verify login", "description": "Check the login form works"}

    monkeypatch.setattr("app.agents.planner.get_ticket", fake_get_ticket)
    planner._llm.queue('{"matched": true, "domain": "sauce_demo", "workflow": "login"}')

    plan = await planner.plan("TICKET-1")

    assert plan.matched is True
    assert plan.domain == "sauce_demo"
    assert plan.workflow == "login"
    assert plan.steps == ["Navigate to saucedemo.com", "Enter a valid username and password", "Click the Login button"]
    assert plan.expected_outcome == {"url_contains": "/inventory.html", "text_contains": "Products"}


async def test_plan_end_to_end_unmatched(monkeypatch, planner):
    async def fake_get_ticket(ticket_id):
        return {"title": "Unrelated ticket", "description": "nothing to do with any registered site"}

    monkeypatch.setattr("app.agents.planner.get_ticket", fake_get_ticket)
    planner._llm.queue('{"matched": false, "reason": "No registered domain matches."}')

    plan = await planner.plan("TICKET-2")

    assert plan.matched is False
    assert plan.reason == "No registered domain matches."
    assert plan.domain is None


async def test_plan_ticket_fetch_error_raises_plannererror(monkeypatch, planner):
    async def fake_get_ticket(ticket_id):
        return {"error": "Card not found"}

    monkeypatch.setattr("app.agents.planner.get_ticket", fake_get_ticket)

    with pytest.raises(PlannerError, match="Card not found"):
        await planner.plan("BAD-ID")


async def test_plan_treats_hallucinated_domain_as_unmatched(monkeypatch, planner):
    async def fake_get_ticket(ticket_id):
        return {"title": "t", "description": "d"}

    monkeypatch.setattr("app.agents.planner.get_ticket", fake_get_ticket)
    # Model names a domain/workflow that isn't in the real registered manifest.
    planner._llm.queue('{"matched": true, "domain": "nonexistent_site", "workflow": "ghost_workflow"}')

    plan = await planner.plan("TICKET-3")

    assert plan.matched is False
    assert "registered manifest" in plan.reason


def test_constructor_without_llm_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(PlannerError, match="ANTHROPIC_API_KEY"):
        PlannerAgent()
