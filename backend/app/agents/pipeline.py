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
from collections.abc import Coroutine
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


def make_llm(provider: str) -> LLMClient:
    if provider == "claude":
        return ClaudeLLMClient()
    if provider == "ollama":
        return OllamaLLMClient()
    raise ValueError(f"Unknown model provider: {provider!r} - expected 'claude' or 'ollama'.")


async def run_pipeline(ticket_id: str, provider: str) -> PipelineResult:
    """Runs the full pipeline with every agent on the same provider."""
    llm = make_llm(provider)
    timings: list[StepTiming] = []
    started_at = time.time()

    async def timed(agent_name: str, awaitable: Coroutine[None, None, T]) -> T:
        stage_start_wall = time.time()
        stage_start_monotonic = time.monotonic()
        result = await awaitable
        timings.append(
            StepTiming(
                agent=agent_name,
                provider=llm.provider,
                model=llm.model,
                started_at=stage_start_wall,
                finished_at=time.time(),
                duration_ms=(time.monotonic() - stage_start_monotonic) * 1000,
            )
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


async def run_both(ticket_id: str) -> tuple[PipelineResult, PipelineResult, ComparisonReport]:
    """Runs Claude's and Ollama's pipelines side by side and compares them."""
    claude_result, ollama_result = await asyncio.gather(
        run_pipeline(ticket_id, "claude"),
        run_pipeline(ticket_id, "ollama"),
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
