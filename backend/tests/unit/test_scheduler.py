import pytest

import app.scheduler as scheduler
from app.agents.schema import PipelineResult, TestPlan, VerifierResult
from app.domains.schema import Domain, ExpectedOutcome, Workflow
from app.history.store import HistoryStore
from app.scheduler import SmokeScheduler, SmokeWorkflowRef, _build_plan, list_smoke_workflows


def _domains():
    return [
        Domain(
            name="site_a",
            base_url="https://a.example",
            workflows=[
                Workflow(name="login", steps=["Log in"], expected_outcome=ExpectedOutcome(text_contains="Welcome"), smoke=True),
                Workflow(name="checkout", steps=["Buy"], expected_outcome=ExpectedOutcome(text_contains="Paid"), smoke=False),
            ],
        ),
        Domain(
            name="site_b",
            base_url="https://b.example",
            workflows=[
                Workflow(name="search", steps=["Search"], expected_outcome=ExpectedOutcome(text_contains="Results"), smoke=True),
            ],
        ),
    ]


@pytest.fixture
def history(tmp_path):
    return HistoryStore(db_path=str(tmp_path / "history.db"))


@pytest.fixture(autouse=True)
def patch_manifest(monkeypatch):
    monkeypatch.setattr(scheduler, "load_domains", _domains)


def _fake_pipeline_result(plan: TestPlan, provider: str, verdict: str) -> PipelineResult:
    return PipelineResult(
        ticket_id=plan.ticket_id,
        provider=provider,
        plan=plan,
        verification=VerifierResult(
            ticket_id=plan.ticket_id, domain=plan.domain, workflow=plan.workflow, verdict=verdict,
            assertion_checked=plan.expected_outcome or {}, initial_check_passed=(verdict != "fail"), retried=False,
        ),
        started_at=0.0,
        finished_at=1.0,
        total_duration_ms=1000.0,
    )


def test_list_smoke_workflows_only_returns_flagged_workflows():
    refs = list_smoke_workflows()

    assert refs == [
        SmokeWorkflowRef(domain="site_a", workflow="login"),
        SmokeWorkflowRef(domain="site_b", workflow="search"),
    ]


def test_build_plan_matches_the_domains_stored_workflow():
    plan = _build_plan(SmokeWorkflowRef(domain="site_a", workflow="login"))

    assert plan.matched is True
    assert plan.domain == "site_a"
    assert plan.workflow == "login"
    assert plan.steps == ["Log in"]
    assert plan.ticket_id.startswith("SMOKE-site_a-login-")


def test_build_plan_rejects_a_workflow_that_no_longer_exists():
    with pytest.raises(ValueError, match="no longer exists"):
        _build_plan(SmokeWorkflowRef(domain="site_a", workflow="deleted_workflow"))


async def test_run_cycle_runs_every_smoke_workflow_across_every_domain_and_records_history(monkeypatch, history):
    calls = []

    async def fake_run_plan(plan, provider, on_event=None):
        calls.append((plan.domain, plan.workflow))
        return _fake_pipeline_result(plan, provider, "pass")

    monkeypatch.setattr(scheduler, "run_plan", fake_run_plan)
    sched = SmokeScheduler(history=history, interval_minutes=30, provider="claude")

    cycle = await sched.run_cycle(triggered_by="scheduled")

    assert calls == [("site_a", "login"), ("site_b", "search")]
    assert cycle.triggered_by == "scheduled"
    assert cycle.pass_count == 2
    assert cycle.fail_count == 0
    assert len(cycle.run_ids) == 2
    assert sched.last_cycle is cycle
    # Recorded to the same history store any ticket-triggered run uses.
    recorded = await history.list_runs(limit=10)
    assert len(recorded) == 2
    assert {r.domain for r in recorded} == {"site_a", "site_b"}
    assert all(r.ticket_id.startswith("SMOKE-") for r in recorded)


async def test_run_now_is_the_same_execution_path_as_a_scheduled_tick(monkeypatch, history):
    # Day 9's own acceptance criteria: the on-demand trigger reuses the
    # scheduled run's execution path - proven here by both going through
    # the identical run_cycle(), just with a different triggered_by label.
    async def fake_run_plan(plan, provider, on_event=None):
        return _fake_pipeline_result(plan, provider, "pass")

    monkeypatch.setattr(scheduler, "run_plan", fake_run_plan)
    sched = SmokeScheduler(history=history, provider="claude")

    cycle = await sched.run_now()

    assert cycle.triggered_by == "on_demand"
    assert cycle.pass_count == 2


async def test_run_cycle_counts_a_fail_verdict_as_failed(monkeypatch, history):
    async def fake_run_plan(plan, provider, on_event=None):
        verdict = "pass" if plan.workflow == "login" else "fail"
        return _fake_pipeline_result(plan, provider, verdict)

    monkeypatch.setattr(scheduler, "run_plan", fake_run_plan)
    sched = SmokeScheduler(history=history)

    cycle = await sched.run_cycle(triggered_by="scheduled")

    assert cycle.pass_count == 1
    assert cycle.fail_count == 1


async def test_run_cycle_survives_one_workflow_raising_and_still_runs_the_rest(monkeypatch, history):
    # One unreachable/broken smoke workflow must not take the whole cycle
    # down with it - every other domain's smoke workflows still need to
    # run this tick, and the failure needs to be visible, not swallowed.
    async def fake_run_plan(plan, provider, on_event=None):
        if plan.domain == "site_a":
            raise RuntimeError("browser crashed")
        return _fake_pipeline_result(plan, provider, "pass")

    monkeypatch.setattr(scheduler, "run_plan", fake_run_plan)
    sched = SmokeScheduler(history=history)

    cycle = await sched.run_cycle(triggered_by="scheduled")

    assert len(cycle.results) == 1
    assert cycle.pass_count == 1
    assert cycle.fail_count == 1  # the crashed workflow counts as a failure too
    assert len(cycle.errors) == 1
    assert cycle.errors[0].domain == "site_a"
    assert cycle.errors[0].workflow == "login"
    assert "browser crashed" in cycle.errors[0].error


def test_scheduler_exposes_interval_and_provider(history):
    sched = SmokeScheduler(history=history, interval_minutes=45, provider="ollama")

    assert sched.interval_minutes == 45
    assert sched.provider == "ollama"
    assert sched.running is False  # never started in this test
    assert sched.next_run_at is None
    assert sched.last_cycle is None
