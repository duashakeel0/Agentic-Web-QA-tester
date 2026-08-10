"""Day 9 - unattended smoke testing. A small, deliberately-idempotent
subset of each domain's workflows (Workflow.smoke=True) run end-to-end on
a fixed interval, independent of any ticket, so a regression on a known
workflow surfaces on its own instead of waiting for a real ticket to
happen to touch that page next.

The dashboard's on-demand "Run Smoke Tests Now" trigger calls the exact
same run_cycle() a scheduled tick calls - a scheduled run and an
on-demand run are the same execution path, just a different trigger,
which is the whole point: nothing about how a cycle runs is
scheduling-specific, only when it starts.
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.agents.pipeline import run_plan
from app.agents.schema import PipelineResult, TestPlan
from app.domains.manifest import load_domains
from app.history.store import HistoryStore

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = int(os.environ.get("SMOKE_INTERVAL_MINUTES", "60"))
DEFAULT_PROVIDER = os.environ.get("SMOKE_PROVIDER", "claude")
JOB_ID = "smoke_cycle"


@dataclass(frozen=True)
class SmokeWorkflowRef:
    domain: str
    workflow: str


def list_smoke_workflows() -> list[SmokeWorkflowRef]:
    """Every workflow across every registered domain that's opted into
    unattended smoke runs - read fresh off the manifest each time, same
    as the Planner does, so a newly-flagged workflow is picked up on the
    very next cycle with no restart needed."""
    return [
        SmokeWorkflowRef(domain=d.name, workflow=w.name) for d in load_domains() for w in d.workflows if w.smoke
    ]


def _build_plan(ref: SmokeWorkflowRef) -> TestPlan:
    """Builds a TestPlan directly from a domain's stored workflow instead
    of going through the Planner - there's no Trello ticket behind a
    scheduled smoke run for the Planner to read, but the plan it produces
    is otherwise identical to one the Planner would have matched, so
    run_plan() downstream can't tell (and doesn't need to) the difference."""
    domain = next((d for d in load_domains() if d.name == ref.domain), None)
    workflow = next((w for w in domain.workflows if w.name == ref.workflow), None) if domain else None
    if domain is None or workflow is None:
        raise ValueError(f"Smoke workflow no longer exists: {ref.domain}/{ref.workflow}")

    ticket_id = f"SMOKE-{ref.domain}-{ref.workflow}-{uuid.uuid4().hex[:8]}"
    return TestPlan(
        ticket_id=ticket_id,
        ticket_title=f"Scheduled smoke test: {ref.domain}/{ref.workflow}",
        matched=True,
        domain=domain.name,
        workflow=workflow.name,
        steps=workflow.steps,
        expected_outcome=workflow.expected_outcome.model_dump(),
    )


@dataclass
class SmokeCycleError:
    domain: str
    workflow: str
    error: str


@dataclass
class SmokeCycleResult:
    triggered_by: str  # "scheduled" or "on_demand"
    provider: str
    started_at: float
    finished_at: float
    results: list[PipelineResult] = field(default_factory=list)
    run_ids: list[int] = field(default_factory=list)
    errors: list[SmokeCycleError] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(
            1 for r in self.results if r.verification and r.verification.verdict in ("pass", "pass_with_issues")
        )

    @property
    def fail_count(self) -> int:
        return len(self.results) - self.pass_count + len(self.errors)


class SmokeScheduler:
    """Owns the APScheduler job and the shared run_cycle() both the
    scheduled tick and the on-demand endpoint call into."""

    def __init__(
        self,
        history: HistoryStore,
        interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
        provider: str = DEFAULT_PROVIDER,
    ) -> None:
        self._history = history
        self._interval_minutes = interval_minutes
        self._provider = provider
        self._scheduler = AsyncIOScheduler()
        self._last_cycle: SmokeCycleResult | None = None

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_scheduled,
            "interval",
            minutes=self._interval_minutes,
            id=JOB_ID,
            # A cycle that's still running (a full browser workflow can
            # take a while) must never overlap with the next tick, and a
            # missed tick shouldn't fire a backlog of catch-up runs the
            # moment the process is free again.
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def _run_scheduled(self) -> None:
        await self.run_cycle(triggered_by="scheduled")

    async def run_now(self) -> SmokeCycleResult:
        return await self.run_cycle(triggered_by="on_demand")

    async def run_cycle(self, triggered_by: str) -> SmokeCycleResult:
        started_at = time.time()
        results: list[PipelineResult] = []
        run_ids: list[int] = []
        errors: list[SmokeCycleError] = []

        for ref in list_smoke_workflows():
            try:
                plan = _build_plan(ref)
                result = await run_plan(plan, self._provider)
                run_id = await self._history.record_run(result)
                results.append(result)
                run_ids.append(run_id)
            except Exception as exc:
                # One broken/unreachable smoke workflow must not take the
                # rest of the cycle down with it - every other domain's
                # smoke workflows still need to run this tick.
                logger.exception("Smoke workflow %s/%s failed to run", ref.domain, ref.workflow)
                errors.append(SmokeCycleError(domain=ref.domain, workflow=ref.workflow, error=str(exc) or exc.__class__.__name__))

        finished_at = time.time()
        cycle = SmokeCycleResult(
            triggered_by=triggered_by,
            provider=self._provider,
            started_at=started_at,
            finished_at=finished_at,
            results=results,
            run_ids=run_ids,
            errors=errors,
        )
        self._last_cycle = cycle
        return cycle

    @property
    def last_cycle(self) -> SmokeCycleResult | None:
        return self._last_cycle

    @property
    def next_run_at(self) -> float | None:
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time.timestamp() if job and job.next_run_time else None

    @property
    def interval_minutes(self) -> int:
        return self._interval_minutes

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def running(self) -> bool:
        return self._scheduler.running
