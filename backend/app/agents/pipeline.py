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
from app.agents.reporter import ReporterAgent
from app.agents.schema import ComparisonReport, PipelineResult, RunResult, StepTiming
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
        return f"Verdict: {result.verdict.upper()}.{suffix}"
    if agent_name == "reporter":
        count = len(result.findings)
        return f"Report ready - {count} confirmed finding(s)." if count else "Report ready - no confirmed findings."
    return ""


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
            await _emit(on_event, {"type": "stage_error", "provider": provider, "agent": agent_name, "message": str(exc)})
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
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=(finished_at - started_at) * 1000,
        )

    explorer = ExplorerAgent(llm=llm)
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
        started_at=started_at,
        finished_at=finished_at,
        total_duration_ms=(finished_at - started_at) * 1000,
    )


async def run_both(
    ticket_id: str, on_event: EventCallback | None = None
) -> tuple[PipelineResult, PipelineResult, ComparisonReport]:
    """Runs Claude's and Ollama's pipelines side by side and compares them.
    Events from both providers interleave on the same callback, tagged with
    "provider" so the dashboard can split them into two live panels."""
    claude_result, ollama_result = await asyncio.gather(
        run_pipeline(ticket_id, "claude", on_event=on_event),
        run_pipeline(ticket_id, "ollama", on_event=on_event),
    )
    return claude_result, ollama_result, _compare(ticket_id, claude_result, ollama_result)


def _compare(ticket_id: str, claude_result: PipelineResult, ollama_result: PipelineResult) -> ComparisonReport:
    claude_verdict = claude_result.verification.verdict if claude_result.verification else None
    ollama_verdict = ollama_result.verification.verdict if ollama_result.verification else None
    faster = "claude" if claude_result.total_duration_ms <= ollama_result.total_duration_ms else "ollama"
    time_difference_ms = abs(claude_result.total_duration_ms - ollama_result.total_duration_ms)
    agreement = claude_verdict == ollama_verdict
    claude_findings = len(claude_result.report.findings) if claude_result.report else 0
    ollama_findings = len(ollama_result.report.findings) if ollama_result.report else 0

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
        summary="\n".join(summary_lines),
    )
