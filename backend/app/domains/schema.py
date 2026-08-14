"""Structured shape of a registered domain. Each domain file (data/*.yaml)
must match this schema - it's the contract the Planner and, later, the
Verifier read against.
"""

from pydantic import BaseModel


class ExpectedOutcome(BaseModel):
    url_contains: str | None = None
    text_contains: str | None = None


class Workflow(BaseModel):
    name: str
    steps: list[str]
    expected_outcome: ExpectedOutcome
    # Marks this workflow as part of its domain's small unattended
    # "smoke" subset - the scheduler runs only these on a fixed interval
    # to catch regressions, independent of any ticket. Kept small and
    # deliberately picked for idempotency (safe to run over and over: no
    # unique-field registration, no fixed-email side effects) since these
    # run unattended with nobody resetting state between cycles.
    smoke: bool = False


class Domain(BaseModel):
    name: str
    base_url: str
    workflows: list[Workflow]
