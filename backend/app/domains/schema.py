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


class Domain(BaseModel):
    name: str
    base_url: str
    workflows: list[Workflow]
