"""Structured, validated output the Planner hands to the Explorer, and the
Explorer hands to the Verifier. Nothing downstream should ever have to
guess at the shape of a plan or an exploration result."""

from pydantic import BaseModel


class TestPlan(BaseModel):
    ticket_id: str
    ticket_title: str | None = None
    matched: bool
    reason: str | None = None
    domain: str | None = None
    workflow: str | None = None
    steps: list[str] = []
    expected_outcome: dict | None = None


class ActionLogEntry(BaseModel):
    step: str
    action: str
    selector: str | None = None
    value: str | None = None
    reasoning: str | None = None
    success: bool
    error: str | None = None
    is_broken_input_attempt: bool = False


class ExplorationResult(BaseModel):
    ticket_id: str
    domain: str
    workflow: str
    completed: bool
    actions: list[ActionLogEntry] = []
    final_url: str | None = None
    final_page_text: str | None = None
    error: str | None = None


class VerifierResult(BaseModel):
    ticket_id: str
    domain: str
    workflow: str
    verdict: str  # "pass" | "fail"
    assertion_checked: dict
    initial_check_passed: bool
    retried: bool
    retry_passed: bool | None = None
    retry_error: str | None = None
    explanation: str | None = None
    explanation_status: str = "ok"  # "ok" | "inconclusive" | "skipped"
    screenshot_path: str | None = None


class RunResult(BaseModel):
    """Pairs one Explorer outcome with its Verifier outcome - the Reporter's
    unit of input. A real run today produces exactly one of these per
    ticket, but the Reporter takes a list so it's ready for the Scheduler's
    future nightly batch across several workflows at once."""

    exploration: ExplorationResult
    verification: VerifierResult


class Finding(BaseModel):
    ticket_id: str
    domain: str
    workflow: str
    severity: str  # "high" | "medium" | "low"
    summary: str
    reproduction_steps: list[str]
    screenshot_path: str | None = None
    explanation: str | None = None


class Report(BaseModel):
    ticket_id: str
    findings: list[Finding]  # ranked, highest severity first
    post_summary_status: str = "pending"  # "posted" | "failed"
    post_summary_error: str | None = None


class StepTiming(BaseModel):
    """One pipeline stage's timing on one provider - the raw material the
    dashboard's per-step timestamps and the comparison report's timing
    numbers are both built from."""

    agent: str  # "planner" | "explorer" | "verifier" | "reporter"
    provider: str  # "claude" | "ollama"
    model: str
    started_at: float  # unix timestamp
    finished_at: float
    duration_ms: float


class PipelineResult(BaseModel):
    """One full Planner -> Explorer -> Verifier -> Reporter run, entirely on
    one provider. A single-model ticket run produces exactly one of these;
    when the user picks "both", two run side by side and feed a
    ComparisonReport."""

    ticket_id: str
    provider: str  # "claude" | "ollama"
    plan: TestPlan
    exploration: ExplorationResult | None = None
    verification: VerifierResult | None = None
    report: Report | None = None
    timings: list[StepTiming] = []
    started_at: float
    finished_at: float
    total_duration_ms: float


class ComparisonReport(BaseModel):
    """Built once both providers' PipelineResults are in for the same
    ticket - a diff over the two runs, not a pipeline run itself."""

    ticket_id: str
    faster_provider: str | None = None
    time_difference_ms: float = 0.0
    verdict_agreement: bool = True
    claude_verdict: str | None = None
    ollama_verdict: str | None = None
    claude_total_duration_ms: float = 0.0
    ollama_total_duration_ms: float = 0.0
    claude_findings_count: int = 0
    ollama_findings_count: int = 0
    summary: str
