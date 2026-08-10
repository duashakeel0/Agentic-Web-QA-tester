"""Day 9's own acceptance criterion: "a step is deliberately broken in a
test domain during development, and the scheduled run correctly flags it
as a failure - documented as evidence, not just claimed." Runs the real
SmokeScheduler.run_cycle() - real ExplorerAgent, real VerifierAgent, real
ReporterAgent, real HistoryStore, a real Playwright browser against a
real local page - twice against the same fixture site: once serving its
correct behavior (expect PASS), once serving a version with one line of
genuinely injected regression (expect FAIL). Only the LLM transport is
scripted (FakeLLM), same as every other test in this file - the point is
to prove the scheduler's own detection actually works end to end, not to
re-verify model behavior already covered elsewhere.

See prompts.md for the captured console output from the one live run
this reproduces.
"""

import pytest

import app.agents.pipeline as pipeline
import app.scheduler as scheduler_module
from app.domains import manifest
from app.domains.schema import Domain, ExpectedOutcome, Workflow
from app.history.store import HistoryStore
from tests.helpers import FakeLLM

pytestmark = pytest.mark.e2e


def _fixture_domain(fixture_server: str, page: str) -> Domain:
    return Domain(
        name="smoke_fixture_site",
        base_url=f"{fixture_server}/{page}",
        workflows=[
            Workflow(
                name="search_no_results",
                steps=["Search for a product that doesn't exist using the search bar"],
                expected_outcome=ExpectedOutcome(text_contains="no results found"),
                smoke=True,
            )
        ],
    )


def _patch_domains(monkeypatch, domain: Domain) -> None:
    monkeypatch.setattr(manifest, "load_domains", lambda: [domain])
    monkeypatch.setattr("app.agents.explorer.load_domains", lambda: [domain])
    monkeypatch.setattr(scheduler_module, "load_domains", lambda: [domain])


def _search_decisions() -> list[str]:
    return [
        '{"action": "fill", "selector": "#search", "value": "zzznonexistent", '
        '"reasoning": "search for a product that does not exist"}',
        '{"action": "click", "selector": "#search-btn", "reasoning": "submit the search"}',
        '{"action": "done", "selector": null, "value": null, "reasoning": "search submitted"}',
    ]


async def _no_op_post_summary(ticket_id, summary_text):
    return {}


async def test_scheduled_smoke_run_passes_against_the_real_correct_page(fixture_server, monkeypatch, tmp_path):
    _patch_domains(monkeypatch, _fixture_domain(fixture_server, "smoke_search_page.html"))
    llm = FakeLLM([*_search_decisions(), "The result area correctly showed the no-results message."])
    monkeypatch.setattr(pipeline, "make_llm", lambda provider: llm)
    monkeypatch.setattr("app.agents.reporter.post_summary", _no_op_post_summary)

    history = HistoryStore(db_path=str(tmp_path / "history.db"))
    sched = scheduler_module.SmokeScheduler(history=history, provider="claude")

    cycle = await sched.run_cycle(triggered_by="scheduled")

    assert cycle.pass_count == 1
    assert cycle.fail_count == 0
    assert cycle.errors == []
    assert cycle.results[0].verification.verdict == "pass"
    assert cycle.results[0].report.findings == []


async def test_scheduled_smoke_run_catches_a_real_deliberately_injected_regression(fixture_server, monkeypatch, tmp_path):
    # The only difference from the passing test above is which real page
    # the fixture server hands back. smoke_search_page_broken.html has one
    # line of genuinely injected regression (see its own comment): the "no
    # results" branch writes an empty string instead of the real message.
    # Nothing about the scheduler, Explorer, Verifier, or Reporter is
    # mocked or special-cased for failure here - this is what proves
    # detection actually works, not just that a FAIL branch exists in the
    # code somewhere.
    _patch_domains(monkeypatch, _fixture_domain(fixture_server, "smoke_search_page_broken.html"))
    llm = FakeLLM(
        [
            *_search_decisions(),
            "The result area never showed the expected no-results message - it stayed empty.",
            '{"severity": "medium", "summary": "Searching for a nonexistent product shows no message at all '
            'instead of a No results found notice."}',
        ]
    )
    monkeypatch.setattr(pipeline, "make_llm", lambda provider: llm)
    monkeypatch.setattr("app.agents.reporter.post_summary", _no_op_post_summary)

    history = HistoryStore(db_path=str(tmp_path / "history.db"))
    sched = scheduler_module.SmokeScheduler(history=history, provider="claude")

    cycle = await sched.run_cycle(triggered_by="scheduled")

    assert cycle.pass_count == 0
    assert cycle.fail_count == 1
    assert cycle.errors == []  # a failed *verdict* is not a crashed smoke workflow
    result = cycle.results[0]
    assert result.verification.verdict == "fail"
    assert len(result.report.findings) == 1
    assert "no message" in result.report.findings[0].summary.lower()

    # Recorded to the real, shared history store exactly like a
    # ticket-triggered run would be - this is what lets the dashboard's
    # Scheduler panel link straight to it.
    recorded = await history.get_run(cycle.run_ids[0])
    assert recorded.verdict == "fail"
