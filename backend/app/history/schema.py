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
    by_provider: dict[str, int]
