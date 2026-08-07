import asyncio

import pytest

import app.agents.pipeline as pipeline
from app.agents.schema import ExplorationResult, Finding, Report, TestPlan, VerifierResult

_real_make_llm = pipeline.make_llm  # captured before the autouse fixture patches it below


class _FakeBrowser:
    async def close(self):
        pass


class _FakePlanner:
    def __init__(self, llm=None):
        self.llm = llm

    async def plan(self, ticket_id):
        await asyncio.sleep(0)
        return TestPlan(
            ticket_id=ticket_id, matched=True, domain="sauce_demo", workflow="login",
            steps=["Log in"], expected_outcome={"url_contains": "/inventory.html"},
        )


class _FakePlannerUnmatched:
    def __init__(self, llm=None):
        self.llm = llm

    async def plan(self, ticket_id):
        return TestPlan(ticket_id=ticket_id, matched=False, reason="no match")


class _FakeExplorer:
    def __init__(self, llm=None, on_action=None):
        self.llm = llm
        self.on_action = on_action
        self.browser = _FakeBrowser()

    async def explore(self, plan, close_browser=True):
        await asyncio.sleep(0)
        return ExplorationResult(
            ticket_id=plan.ticket_id, domain=plan.domain, workflow=plan.workflow,
            completed=True, actions=[], final_url="https://x/inventory.html", final_page_text="Products",
        )


class _FakeVerifier:
    def __init__(self, llm=None):
        self.llm = llm

    async def verify(self, expected_outcome, result, browser=None):
        await asyncio.sleep(0)
        return VerifierResult(
            ticket_id=result.ticket_id, domain=result.domain, workflow=result.workflow, verdict="pass",
            assertion_checked=expected_outcome, initial_check_passed=True, retried=False,
        )


class _FakeVerifierFail:
    def __init__(self, llm=None):
        self.llm = llm

    async def verify(self, expected_outcome, result, browser=None):
        await asyncio.sleep(0)
        return VerifierResult(
            ticket_id=result.ticket_id, domain=result.domain, workflow=result.workflow, verdict="fail",
            assertion_checked=expected_outcome, initial_check_passed=False, retried=True,
        )


class _FakeReporter:
    def __init__(self, llm=None):
        self.llm = llm

    async def report(self, ticket_id, runs):
        await asyncio.sleep(0)
        findings = [] if runs[0].verification.verdict == "pass" else [
            Finding(
                ticket_id=ticket_id, domain=runs[0].exploration.domain, workflow=runs[0].exploration.workflow,
                severity="high", summary="broke", reproduction_steps=[],
            )
        ]
        return Report(ticket_id=ticket_id, findings=findings, post_summary_status="posted")


class _FakeLLM:
    def __init__(self, provider):
        self.provider = provider
        self.model = f"{provider}-fake"
        self.call_count = 3
        self.total_input_tokens = 100
        self.total_output_tokens = 50


@pytest.fixture(autouse=True)
def patch_agents(monkeypatch):
    monkeypatch.setattr(pipeline, "PlannerAgent", _FakePlanner)
    monkeypatch.setattr(pipeline, "ExplorerAgent", _FakeExplorer)
    monkeypatch.setattr(pipeline, "VerifierAgent", _FakeVerifier)
    monkeypatch.setattr(pipeline, "ReporterAgent", _FakeReporter)
    monkeypatch.setattr(pipeline, "make_llm", lambda provider: _FakeLLM(provider))


async def test_run_pipeline_matched_runs_all_four_stages():
    result = await pipeline.run_pipeline("T1", "claude")

    assert result.provider == "claude"
    assert [t.agent for t in result.timings] == ["planner", "explorer", "verifier", "reporter"]
    assert all(t.provider == "claude" for t in result.timings)
    assert result.report.post_summary_status == "posted"
    assert result.total_duration_ms >= 0
    assert result.metrics is not None
    assert result.metrics.estimated_cost_usd > 0  # claude, not free


async def test_run_pipeline_unmatched_short_circuits(monkeypatch):
    monkeypatch.setattr(pipeline, "PlannerAgent", _FakePlannerUnmatched)

    result = await pipeline.run_pipeline("T2", "ollama")

    assert result.plan.matched is False
    assert [t.agent for t in result.timings] == ["planner"]
    assert result.exploration is None
    assert result.verification is None
    assert result.report is None
    assert result.metrics.estimated_cost_usd == 0.0  # ollama is always free


async def test_run_pipeline_emits_events_in_order():
    events = []

    async def on_event(event):
        events.append(event["type"])

    await pipeline.run_pipeline("T1", "claude", on_event=on_event)

    assert events == [
        "stage_start", "stage_end",  # planner
        "stage_start", "stage_end",  # explorer
        "stage_start", "stage_end",  # verifier
        "stage_start", "stage_end",  # reporter
    ]


async def test_run_pipeline_emits_stage_error_and_reraises(monkeypatch):
    class _BrokenExplorer:
        def __init__(self, llm=None, on_action=None):
            self.browser = _FakeBrowser()

        async def explore(self, plan, close_browser=True):
            raise RuntimeError("browser crashed")

    monkeypatch.setattr(pipeline, "ExplorerAgent", _BrokenExplorer)
    events = []

    async def on_event(event):
        events.append(event)

    with pytest.raises(RuntimeError, match="browser crashed"):
        await pipeline.run_pipeline("T1", "claude", on_event=on_event)

    error_events = [e for e in events if e["type"] == "stage_error"]
    assert len(error_events) == 1
    assert error_events[0]["agent"] == "explorer"


async def test_run_both_produces_two_results_and_a_comparison():
    claude_result, ollama_result, comparison = await pipeline.run_both("T3")

    assert claude_result.provider == "claude"
    assert ollama_result.provider == "ollama"
    assert comparison.ticket_id == "T3"
    assert comparison.claude_verdict == "pass"
    assert comparison.ollama_verdict == "pass"
    assert comparison.verdict_agreement is True
    assert comparison.faster_provider in ("claude", "ollama")
    assert comparison.cheaper_provider == "ollama"  # always free


async def test_compare_flags_disagreement_and_missed_steps(monkeypatch):
    claude_result = await pipeline.run_pipeline("T4", "claude")
    monkeypatch.setattr(pipeline, "VerifierAgent", _FakeVerifierFail)
    ollama_result = await pipeline.run_pipeline("T4", "ollama")

    comparison = pipeline._compare("T4", claude_result, ollama_result)

    assert comparison.verdict_agreement is False
    assert comparison.claude_findings_count == 0
    assert comparison.ollama_findings_count == 1


def test_make_llm_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown model provider"):
        _real_make_llm("gpt4")
