"""Pydantic shapes for the run history API - distinct from the agents' own
PipelineResult/ComparisonReport, which get stored as raw JSON for the
detail view rather than reshaped into their own history models.
"""

from pydantic import BaseModel


class HistoryEntry(BaseModel):
    id: int
    ticket_id: str
    domain: str | None = None
    workflow: str | None = None
    provider: str
    matched: bool
    verdict: str | None = None
    findings_count: int
    total_duration_ms: float
    estimated_cost_usd: float = 0.0
    started_at: float
    finished_at: float
    comparison_group: str | None = None
    created_at: float


class HistoryDetail(HistoryEntry):
    result: dict  # the full stored PipelineResult


class ComparisonHistoryEntry(BaseModel):
    comparison_group: str
    ticket_id: str
    comparison: dict  # the full stored ComparisonReport
    created_at: float


class HistoryStats(BaseModel):
    total_runs: int
    passed: int
    failed: int
    unmatched: int
    avg_duration_ms: float
    total_cost_usd: float = 0.0
    by_provider: dict[str, int]


class MissedStepCount(BaseModel):
    step: str
    count: int


class ProviderStats(BaseModel):
    """Aggregated across every run on this provider - what the Model
    Comparison page diffs, as opposed to ComparisonReport which is just
    one "both" run's pair."""

    provider: str
    run_count: int
    pass_count: int
    fail_count: int
    avg_duration_ms: float
    avg_coverage_ratio: float
    avg_accuracy_ratio: float
    avg_cost_usd: float
    total_cost_usd: float
    common_missed_steps: list[MissedStepCount] = []


class DailyStat(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    total: int
    passed: int
    failed: int
    total_cost_usd: float
    avg_duration_ms: float


class SiteStats(BaseModel):
    """How many times each registered website has actually been tested -
    the sidebar's "tested N times" summary, distinct from ProviderStats
    (grouped by model) or HistoryStats (one grand total across everything)."""

    domain: str
    run_count: int
    passed: int
    failed: int
    last_tested_at: float
