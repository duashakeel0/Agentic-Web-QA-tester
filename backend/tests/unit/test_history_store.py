import sqlite3

import pytest

from app.agents.schema import ComparisonReport, ExplorationResult, Finding, PipelineResult, Report, RunMetrics, TestPlan, VerifierResult
from app.history.store import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(db_path=str(tmp_path / "history.db"))


def _result(
    ticket_id, provider, verdict, matched=True, findings=0, cost=0.01, coverage=1.0, accuracy=1.0, missed=None,
    domain="practice_software_testing",
):
    verification = VerifierResult(
        ticket_id=ticket_id, domain=domain, workflow="login", verdict=verdict,
        assertion_checked={}, initial_check_passed=(verdict == "pass"), retried=False,
    ) if matched else None
    report = Report(
        ticket_id=ticket_id,
        findings=[
            Finding(ticket_id=ticket_id, domain=domain, workflow="login", severity="high",
                     summary="broke", reproduction_steps=[])
            for _ in range(findings)
        ],
    ) if matched else None
    metrics = RunMetrics(
        steps_planned=3, steps_covered=3, coverage_ratio=coverage, missed_steps=missed or [],
        actions_attempted=3, actions_succeeded=3, accuracy_ratio=accuracy, llm_call_count=5,
        input_tokens=100, output_tokens=50, estimated_cost_usd=cost,
    )
    return PipelineResult(
        ticket_id=ticket_id, provider=provider,
        plan=TestPlan(ticket_id=ticket_id, matched=matched, domain=domain if matched else None,
                       workflow="login" if matched else None, steps=["a", "b", "c"] if matched else []),
        verification=verification, report=report, metrics=metrics,
        started_at=0.0, finished_at=0.05, total_duration_ms=50.0,
    )


async def test_record_and_list_runs(store):
    run_id = await store.record_run(_result("T1", "claude", "pass"))
    assert run_id == 1

    entries = await store.list_runs()
    assert len(entries) == 1
    assert entries[0].ticket_id == "T1"
    assert entries[0].verdict == "pass"
    assert entries[0].estimated_cost_usd == 0.01


async def test_list_runs_ordered_newest_first(store):
    await store.record_run(_result("T1", "claude", "pass"))
    await store.record_run(_result("T2", "claude", "pass"))

    entries = await store.list_runs()

    assert [e.ticket_id for e in entries] == ["T2", "T1"]


async def test_list_runs_filters_by_search_and_provider(store):
    await store.record_run(_result("ALPHA-1", "claude", "pass"))
    await store.record_run(_result("BETA-1", "ollama", "fail"))

    assert [e.ticket_id for e in await store.list_runs(search="ALPHA")] == ["ALPHA-1"]
    assert [e.ticket_id for e in await store.list_runs(provider="ollama")] == ["BETA-1"]
    assert await store.list_runs(search="nonexistent") == []


async def test_get_run_returns_full_detail(store):
    run_id = await store.record_run(_result("T1", "claude", "fail", findings=1))

    detail = await store.get_run(run_id)

    assert detail.ticket_id == "T1"
    assert detail.verdict == "fail"
    assert detail.findings_count == 1
    assert detail.result["provider"] == "claude"


async def test_get_run_returns_none_when_missing(store):
    assert await store.get_run(999) is None


async def test_comparison_group_links_two_runs(store):
    group = store.new_comparison_group()
    claude_id = await store.record_run(_result("T1", "claude", "pass"), group)
    ollama_id = await store.record_run(_result("T1", "ollama", "fail"), group)
    comparison = ComparisonReport(ticket_id="T1", faster_provider="ollama", summary="Ollama was faster.")
    await store.record_comparison(comparison, group)

    claude_entry = await store.get_run(claude_id)
    ollama_entry = await store.get_run(ollama_id)
    comp_entry = await store.get_comparison(group)

    assert claude_entry.comparison_group == ollama_entry.comparison_group == group
    assert comp_entry.comparison["faster_provider"] == "ollama"


async def test_get_comparison_returns_none_when_missing(store):
    assert await store.get_comparison("nonexistent-group") is None


async def test_stats_aggregates_correctly(store):
    await store.record_run(_result("T1", "claude", "pass", cost=0.01))
    await store.record_run(_result("T2", "claude", "fail", findings=1, cost=0.02))
    await store.record_run(_result("T3", "ollama", "pass", cost=0.0))
    await store.record_run(_result("T4", "claude", None, matched=False, cost=0.0))

    stats = await store.stats()

    assert stats.total_runs == 4
    assert stats.passed == 2
    assert stats.failed == 1
    assert stats.unmatched == 1
    assert stats.total_cost_usd == pytest.approx(0.03)
    assert stats.by_provider == {"claude": 3, "ollama": 1}


async def test_provider_stats_aggregates_metrics_and_missed_steps(store):
    await store.record_run(_result("T1", "claude", "pass", cost=0.01, coverage=1.0, accuracy=1.0))
    await store.record_run(_result("T2", "claude", "fail", cost=0.02, coverage=0.5, accuracy=0.5, missed=["Click login"]))
    await store.record_run(_result("T3", "ollama", "fail", cost=0.0, missed=["Click login", "Enter password"]))

    stats = await store.provider_stats()
    by_provider = {p.provider: p for p in stats}

    assert by_provider["claude"].run_count == 2
    assert by_provider["claude"].pass_count == 1
    assert by_provider["claude"].fail_count == 1
    assert by_provider["claude"].avg_coverage_ratio == pytest.approx(0.75)
    assert by_provider["claude"].total_cost_usd == pytest.approx(0.03)
    assert by_provider["claude"].common_missed_steps[0].step == "Click login"
    assert by_provider["ollama"].total_cost_usd == 0.0
    assert len(by_provider["ollama"].common_missed_steps) == 2


async def test_daily_stats_buckets_by_day(store):
    await store.record_run(_result("T1", "claude", "pass", cost=0.01))
    await store.record_run(_result("T2", "ollama", "fail", cost=0.0))

    daily = await store.daily_stats(days=7)

    assert len(daily) == 1  # both recorded "now"
    assert daily[0].total == 2
    assert daily[0].passed == 1
    assert daily[0].failed == 1
    assert daily[0].total_cost_usd == pytest.approx(0.01)


async def test_site_stats_counts_runs_per_website(store):
    await store.record_run(_result("T1", "claude", "pass", domain="practice_software_testing"))
    await store.record_run(_result("T2", "ollama", "fail", domain="practice_software_testing"))
    await store.record_run(_result("T3", "claude", "pass", domain="parabank"))
    await store.record_run(_result("T4", "claude", "pass", matched=False))  # unmatched - no domain, excluded

    stats = await store.site_stats()
    by_domain = {s.domain: s for s in stats}

    assert set(by_domain) == {"practice_software_testing", "parabank"}
    assert by_domain["practice_software_testing"].run_count == 2
    assert by_domain["practice_software_testing"].passed == 1
    assert by_domain["practice_software_testing"].failed == 1
    assert by_domain["parabank"].run_count == 1
    assert by_domain["parabank"].passed == 1
    # Most-tested site first.
    assert stats[0].domain == "practice_software_testing"


async def test_site_stats_empty_when_no_runs(store):
    assert await store.site_stats() == []


async def test_migration_adds_cost_column_to_pre_existing_database(tmp_path):
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL, domain TEXT, workflow TEXT, provider TEXT NOT NULL,
            matched INTEGER NOT NULL, verdict TEXT, findings_count INTEGER NOT NULL DEFAULT 0,
            total_duration_ms REAL NOT NULL, started_at REAL NOT NULL, finished_at REAL NOT NULL,
            comparison_group TEXT, result_json TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE comparisons (
            comparison_group TEXT PRIMARY KEY, ticket_id TEXT NOT NULL,
            comparison_json TEXT NOT NULL, created_at REAL NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO runs (ticket_id, domain, workflow, provider, matched, verdict, findings_count, "
        "total_duration_ms, started_at, finished_at, comparison_group, result_json, created_at) "
        "VALUES ('OLD-1','d','w','claude',1,'pass',0,1000,0,1,NULL,'{}',0)"
    )
    conn.commit()
    conn.close()

    store = HistoryStore(db_path=db_path)
    entries = await store.list_runs()

    assert entries[0].ticket_id == "OLD-1"
    assert entries[0].estimated_cost_usd == 0.0
