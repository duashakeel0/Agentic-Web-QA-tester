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
