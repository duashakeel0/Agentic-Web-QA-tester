"""Structured, validated output the Planner hands to the Explorer. Nothing
downstream should ever have to guess at the shape of a plan."""

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
