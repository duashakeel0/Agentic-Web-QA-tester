from app.agents.pipeline import _compute_metrics
from app.agents.schema import ActionLogEntry, ExplorationResult, TestPlan


class _FakeLLM:
    provider = "claude"
    model = "claude-fake"
    call_count = 5
    total_input_tokens = 2000
    total_output_tokens = 500


def test_full_coverage_with_partial_accuracy():
    plan = TestPlan(ticket_id="T1", matched=True, domain="d", workflow="w",
                     steps=["Navigate to /login", "Enter credentials", "Submit"])
    exploration = ExplorationResult(
        ticket_id="T1", domain="d", workflow="w", completed=True,
        actions=[
            ActionLogEntry(step="Navigate to /login", action="navigate", success=True),
            ActionLogEntry(step="Enter credentials", action="fill", success=True),
            ActionLogEntry(step="Enter credentials", action="fill", success=False, error="bad selector"),
            ActionLogEntry(step="Submit", action="click", success=True),
            ActionLogEntry(step="Enter credentials", action="fill", success=False, is_broken_input_attempt=True),
        ],
    )

    metrics = _compute_metrics(plan, exploration, _FakeLLM())

    assert metrics.steps_planned == 3
    assert metrics.steps_covered == 3
    assert metrics.coverage_ratio == 1.0
    assert metrics.missed_steps == []
    assert metrics.actions_attempted == 4  # excludes the broken-input probe
    assert metrics.actions_succeeded == 3
    assert metrics.accuracy_ratio == 0.75
    assert metrics.llm_call_count == 5
    assert metrics.input_tokens == 2000
    assert metrics.output_tokens == 500
    assert metrics.estimated_cost_usd > 0


def test_partial_coverage_when_exploration_stopped_early():
    plan = TestPlan(ticket_id="T2", matched=True, domain="d", workflow="w",
                     steps=["Navigate to /login", "Enter credentials", "Submit"])
    exploration = ExplorationResult(
        ticket_id="T2", domain="d", workflow="w", completed=False,
        actions=[ActionLogEntry(step="Navigate to /login", action="navigate", success=True)],
        error="Explorer could not complete step 'Enter credentials' within 6 actions.",
    )

    metrics = _compute_metrics(plan, exploration, _FakeLLM())

    assert metrics.steps_covered == 1
    assert metrics.coverage_ratio == 1 / 3
    assert metrics.missed_steps == ["Enter credentials", "Submit"]


def test_unmatched_plan_has_zeroed_step_metrics_but_real_llm_usage():
    plan = TestPlan(ticket_id="T3", matched=False, reason="no match")

    metrics = _compute_metrics(plan, None, _FakeLLM())

    assert metrics.steps_planned == 0
    assert metrics.steps_covered == 0
    assert metrics.missed_steps == []
    assert metrics.llm_call_count == 5  # the Planner still made a real call
