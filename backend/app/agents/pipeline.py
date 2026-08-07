"""Pipeline runner - drives Planner -> Explorer -> Verifier -> Reporter as
one run on a chosen provider, timing each stage as it happens. This is what
lets a ticket run be launched with a model choice (Claude, Ollama, or both
side by side) from one place instead of the caller wiring up all four agents
by hand and losing track of timing.

"Both" runs the whole pipeline twice, concurrently, once per provider, and
then builds a ComparisonReport from the two finished runs - so a "both" run
always yields three things: a Claude PipelineResult, an Ollama
PipelineResult, and the comparison between them.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import TypeVar

from app.agents.claude_client import ClaudeLLMClient
from app.agents.explorer import ExplorerAgent
from app.agents.llm_client import LLMClient
from app.agents.ollama_client import OllamaLLMClient
from app.agents.planner import PlannerAgent
from app.agents.pricing import estimate_cost_usd
from app.agents.reporter import ReporterAgent
from app.agents.schema import (
    ComparisonReport,
    ExplorationResult,
    PipelineResult,
    RunMetrics,
    RunResult,
    StepTiming,
    TestPlan,
)
from app.agents.verifier import VerifierAgent

T = TypeVar("T")

# Called with one event dict per pipeline stage transition, e.g.
# {"type": "stage_start", "provider": "claude", "agent": "planner"} - the
# WebSocket layer forwards these straight to the client so the dashboard can
# show a live "talking agents" panel instead of one final blob at the end.
EventCallback = Callable[[dict], Awaitable[None]]


def make_llm(provider: str) -> LLMClient:
    if provider == "claude":
        return ClaudeLLMClient()
    if provider == "ollama":
        return OllamaLLMClient()
    raise ValueError(f"Unknown model provider: {provider!r} - expected 'claude' or 'ollama'.")


async def _emit(on_event: EventCallback | None, event: dict) -> None:
    if on_event is not None:
        await on_event(event)


def _narrate(agent_name: str, result) -> str:
    """One human-readable sentence per finished stage - what the "talking
    agents" panel actually shows instead of raw JSON."""
    if agent_name == "planner":
        if not result.matched:
            return f"No registered domain matched this ticket: {result.reason}"
        return f"Matched to {result.domain}/{result.workflow} - plan has {len(result.steps)} step(s)."
    if agent_name == "explorer":
        if not result.completed:
            return f"Exploration stopped early: {result.error}"
        return f"Completed the workflow in {len(result.actions)} action(s)."
    if agent_name == "verifier":
        suffix = f" {result.explanation}" if result.explanation else ""
        return f"Verdict: {result.verdict.replace('_', ' ').upper()}.{suffix}"
    if agent_name == "reporter":
        count = len(result.findings)
        return f"Report ready - {count} confirmed finding(s)." if count else "Report ready - no confirmed findings."
    return ""


def _compute_metrics(plan: TestPlan, exploration: ExplorationResult | None, llm: LLMClient) -> RunMetrics:
    """Coverage/accuracy/cost for one run, read off the shared LLMClient's
    running totals (every agent in a run uses the same instance) plus the
    Explorer's action log."""
    cost_usd = estimate_cost_usd(llm.provider, llm.total_input_tokens, llm.total_output_tokens)
    base = {
        "llm_call_count": llm.call_count,
        "input_tokens": llm.total_input_tokens,
        "output_tokens": llm.total_output_tokens,
        "estimated_cost_usd": cost_usd,
    }
    steps_planned = len(plan.steps)

    if exploration is None:
        return RunMetrics(steps_planned=steps_planned, steps_covered=0, missed_steps=list(plan.steps), **base)

    real_actions = [a for a in exploration.actions if not a.is_broken_input_attempt]
    covered_steps = list(dict.fromkeys(a.step for a in real_actions))
    missed_steps = [s for s in plan.steps if s not in covered_steps]
    actions_attempted = len(real_actions)
    actions_succeeded = sum(1 for a in real_actions if a.success)

    return RunMetrics(
        steps_planned=steps_planned,
        steps_covered=len(covered_steps),
        coverage_ratio=(len(covered_steps) / steps_planned) if steps_planned else 0.0,
        missed_steps=missed_steps,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_succeeded,
        accuracy_ratio=(actions_succeeded / actions_attempted) if actions_attempted else 0.0,
        **base,
    )


async def run_pipeline(ticket_id: str, provider: str, on_event: EventCallback | None = None) -> PipelineResult:
    """Runs the full pipeline with every agent on the same provider."""
    llm = make_llm(provider)
    timings: list[StepTiming] = []
    started_at = time.time()

    async def timed(agent_name: str, awaitable: Coroutine[None, None, T]) -> T:
        await _emit(on_event, {"type": "stage_start", "provider": provider, "agent": agent_name})
        stage_start_wall = time.time()
        stage_start_monotonic = time.monotonic()
        try:
            result = await awaitable
        except Exception as exc:
            # Some exceptions (asyncio.CancelledError, a bare TimeoutError
            # raised with no args) stringify to "" - never surface that as
            # a blank, unexplained failure in the UI.
            message = str(exc) or f"{exc.__class__.__name__} (no further detail)"
            await _emit(on_event, {"type": "stage_error", "provider": provider, "agent": agent_name, "message": message})
            raise
        duration_ms = (time.monotonic() - stage_start_monotonic) * 1000
        timings.append(
            StepTiming(
                agent=agent_name,
                provider=llm.provider,
                model=llm.model,
                started_at=stage_start_wall,
                finished_at=time.time(),
                duration_ms=duration_ms,
            )
        )
        await _emit(
            on_event,
            {
                "type": "stage_end",
                "provider": provider,
                "agent": agent_name,
                "duration_ms": duration_ms,
                "message": _narrate(agent_name, result),
            },
        )
        return result

    planner = PlannerAgent(llm=llm)
    plan = await timed("planner", planner.plan(ticket_id))

    if not plan.matched:
        finished_at = time.time()
        return PipelineResult(
            ticket_id=ticket_id,
            provider=provider,
            plan=plan,
            timings=timings,
            metrics=_compute_metrics(plan, None, llm),
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=(finished_at - started_at) * 1000,
        )

    async def on_action(event: dict) -> None:
        # The Explorer tags each event "action" (a discrete, model-decided
        # browser action - goes in the action log/filmstrip/report) or
        # "frame" (a background live-view tick on a fixed interval, purely
        # visual, never logged) - forwarded here as the WS event's own
        # "type" so the two render differently on the dashboard.
        event_type = event.pop("kind", "action")
        await _emit(on_event, {"type": event_type, "provider": provider, "agent": "explorer", **event})

    explorer = ExplorerAgent(llm=llm, on_action=on_action)
    exploration = await timed("explorer", explorer.explore(plan, close_browser=False))

    verifier = VerifierAgent(llm=llm)
    try:
        verification = await timed(
            "verifier",
            verifier.verify(
                plan.expected_outcome or {},
                exploration,
                browser=explorer.browser if exploration.completed else None,
            ),
        )
    finally:
        if exploration.completed:
            await explorer.browser.close()

    reporter = ReporterAgent(llm=llm)
    report = await timed(
        "reporter",
        reporter.report(ticket_id, [RunResult(exploration=exploration, verification=verification)]),
    )

    finished_at = time.time()
    return PipelineResult(
        ticket_id=ticket_id,
        provider=provider,
        plan=plan,
        exploration=exploration,
        verification=verification,
        report=report,
        timings=timings,
        metrics=_compute_metrics(plan, exploration, llm),
        started_at=started_at,
        finished_at=finished_at,
        total_duration_ms=(finished_at - started_at) * 1000,
    )


async def run_both(
    ticket_id: str, on_event: EventCallback | None = None
) -> tuple[PipelineResult | None, PipelineResult | None, ComparisonReport | None]:
    """Runs Claude's and Ollama's pipelines side by side. Events from both
    providers interleave on the same callback, tagged with "provider" so
    the dashboard can split them into two live panels.

    return_exceptions=True matters here: without it, the moment either
    side raises, asyncio.gather propagates that failure immediately and
    the *other* provider's task is abandoned mid-run - not cancelled, just
    orphaned, still running on the server with nowhere left to report to
    once the caller (the WebSocket handler) has already closed the
    connection and moved on. That's what made a genuinely-still-running
    Ollama call look permanently frozen in the UI. With this, both sides
    always run to their own natural completion or failure."""
    claude_outcome, ollama_outcome = await asyncio.gather(
        run_pipeline(ticket_id, "claude", on_event=on_event),
        run_pipeline(ticket_id, "ollama", on_event=on_event),
        return_exceptions=True,
    )

    claude_result = claude_outcome if isinstance(claude_outcome, PipelineResult) else None
    ollama_result = ollama_outcome if isinstance(ollama_outcome, PipelineResult) else None

    comparison = _compare(ticket_id, claude_result, ollama_result) if claude_result and ollama_result else None
    return claude_result, ollama_result, comparison


def _compare(ticket_id: str, claude_result: PipelineResult, ollama_result: PipelineResult) -> ComparisonReport:
    claude_verdict = claude_result.verification.verdict if claude_result.verification else None
    ollama_verdict = ollama_result.verification.verdict if ollama_result.verification else None
    faster = "claude" if claude_result.total_duration_ms <= ollama_result.total_duration_ms else "ollama"
    time_difference_ms = abs(claude_result.total_duration_ms - ollama_result.total_duration_ms)
    agreement = claude_verdict == ollama_verdict
    claude_findings = len(claude_result.report.findings) if claude_result.report else 0
    ollama_findings = len(ollama_result.report.findings) if ollama_result.report else 0

    claude_metrics, ollama_metrics = claude_result.metrics, ollama_result.metrics
    cheaper = cost_difference_usd = more_accurate = better_coverage = None
    missed_only_by_claude: list[str] = []
    missed_only_by_ollama: list[str] = []

    summary_lines = [
        f"Claude finished in {claude_result.total_duration_ms:.0f}ms, "
        f"Ollama finished in {ollama_result.total_duration_ms:.0f}ms "
        f"({faster} was faster by {time_difference_ms:.0f}ms).",
    ]
    if claude_verdict and ollama_verdict:
        summary_lines.append(
            f"Verdicts {'agree' if agreement else 'disagree'}: "
            f"Claude says {claude_verdict}, Ollama says {ollama_verdict}."
        )
    summary_lines.append(f"Claude confirmed {claude_findings} finding(s), Ollama confirmed {ollama_findings}.")

    if claude_metrics and ollama_metrics:
        cost_difference_usd = abs(claude_metrics.estimated_cost_usd - ollama_metrics.estimated_cost_usd)
        cheaper = "claude" if claude_metrics.estimated_cost_usd <= ollama_metrics.estimated_cost_usd else "ollama"
        more_accurate = "claude" if claude_metrics.accuracy_ratio >= ollama_metrics.accuracy_ratio else "ollama"
        better_coverage = "claude" if claude_metrics.coverage_ratio >= ollama_metrics.coverage_ratio else "ollama"

        claude_missed, ollama_missed = set(claude_metrics.missed_steps), set(ollama_metrics.missed_steps)
        missed_only_by_claude = sorted(claude_missed - ollama_missed)
        missed_only_by_ollama = sorted(ollama_missed - claude_missed)

        summary_lines.append(
            f"Coverage: Claude {claude_metrics.coverage_ratio:.0%}, Ollama {ollama_metrics.coverage_ratio:.0%}. "
            f"Accuracy: Claude {claude_metrics.accuracy_ratio:.0%}, Ollama {ollama_metrics.accuracy_ratio:.0%}."
        )
        summary_lines.append(
            f"Estimated cost: Claude ${claude_metrics.estimated_cost_usd:.4f}, Ollama $0.0000 (runs locally) - "
            f"{cheaper} is cheaper by ${cost_difference_usd:.4f}."
        )
        if missed_only_by_claude:
            summary_lines.append(f"Steps only Claude missed: {', '.join(missed_only_by_claude)}.")
        if missed_only_by_ollama:
            summary_lines.append(f"Steps only Ollama missed: {', '.join(missed_only_by_ollama)}.")

    return ComparisonReport(
        ticket_id=ticket_id,
        faster_provider=faster,
        time_difference_ms=time_difference_ms,
        verdict_agreement=agreement,
        claude_verdict=claude_verdict,
        ollama_verdict=ollama_verdict,
        claude_total_duration_ms=claude_result.total_duration_ms,
        ollama_total_duration_ms=ollama_result.total_duration_ms,
        claude_findings_count=claude_findings,
        ollama_findings_count=ollama_findings,
        claude_metrics=claude_metrics,
        ollama_metrics=ollama_metrics,
        missed_only_by_claude=missed_only_by_claude,
        missed_only_by_ollama=missed_only_by_ollama,
        cost_difference_usd=cost_difference_usd or 0.0,
        cheaper_provider=cheaper,
        more_accurate_provider=more_accurate,
        better_coverage_provider=better_coverage,
        summary="\n".join(summary_lines),
    )
