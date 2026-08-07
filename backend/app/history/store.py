"""SQLite-backed run history - every pipeline run gets one row (two, tagged
with a shared comparison_group, when the user picks "both"), so the
dashboard's history table and stat cards have something real to read
instead of only ever seeing the most recent run.

Uses the stdlib sqlite3 module run through asyncio.to_thread rather than an
extra async driver dependency - this project's other blocking I/O (sending
email in reporter.py) already follows that same pattern.
"""

import asyncio
import json
import os
import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager

from app.agents.schema import ComparisonReport, PipelineResult
from app.history.schema import (
    ComparisonHistoryEntry,
    DailyStat,
    HistoryDetail,
    HistoryEntry,
    HistoryStats,
    MissedStepCount,
    ProviderStats,
)

DEFAULT_DB_PATH = "data/history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    domain TEXT,
    workflow TEXT,
    provider TEXT NOT NULL,
    matched INTEGER NOT NULL,
    verdict TEXT,
    findings_count INTEGER NOT NULL DEFAULT 0,
    total_duration_ms REAL NOT NULL,
    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL,
    comparison_group TEXT,
    result_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS comparisons (
    comparison_group TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    comparison_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


class HistoryStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """A database created before estimated_cost_usd existed needs the
        column added - CREATE TABLE IF NOT EXISTS only helps fresh files."""
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        if "estimated_cost_usd" not in existing_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0.0")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def new_comparison_group() -> str:
        return uuid.uuid4().hex

    def _record_run_sync(self, result: PipelineResult, comparison_group: str | None) -> int:
        verdict = result.verification.verdict if result.verification else None
        findings_count = len(result.report.findings) if result.report else 0
        cost = result.metrics.estimated_cost_usd if result.metrics else 0.0
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO runs (
                    ticket_id, domain, workflow, provider, matched, verdict, findings_count,
                    total_duration_ms, estimated_cost_usd, started_at, finished_at, comparison_group,
                    result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.ticket_id, result.plan.domain, result.plan.workflow, result.provider,
                    int(result.plan.matched), verdict, findings_count, result.total_duration_ms, cost,
                    result.started_at, result.finished_at, comparison_group,
                    result.model_dump_json(), time.time(),
                ),
            )
            return cursor.lastrowid

    async def record_run(self, result: PipelineResult, comparison_group: str | None = None) -> int:
        return await asyncio.to_thread(self._record_run_sync, result, comparison_group)

    def _record_comparison_sync(self, comparison: ComparisonReport, comparison_group: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO comparisons (comparison_group, ticket_id, comparison_json, created_at)
                VALUES (?, ?, ?, ?)""",
                (comparison_group, comparison.ticket_id, comparison.model_dump_json(), time.time()),
            )

    async def record_comparison(self, comparison: ComparisonReport, comparison_group: str) -> None:
        await asyncio.to_thread(self._record_comparison_sync, comparison, comparison_group)

    def _list_runs_sync(
        self,
        limit: int,
        offset: int,
        search: str | None,
        provider: str | None,
        domain: str | None,
    ) -> list[HistoryEntry]:
        clauses = []
        params: list = []
        if search:
            clauses.append("(ticket_id LIKE ? OR domain LIKE ? OR workflow LIKE ?)")
            like = f"%{search}%"
            params += [like, like, like]
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""SELECT id, ticket_id, domain, workflow, provider, matched, verdict, findings_count,
                    total_duration_ms, estimated_cost_usd, started_at, finished_at, comparison_group, created_at
                FROM runs {where} ORDER BY id DESC LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    async def list_runs(
        self,
        limit: int = 20,
        offset: int = 0,
        search: str | None = None,
        provider: str | None = None,
        domain: str | None = None,
    ) -> list[HistoryEntry]:
        return await asyncio.to_thread(self._list_runs_sync, limit, offset, search, provider, domain)

    def _get_run_sync(self, run_id: int) -> HistoryDetail | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT id, ticket_id, domain, workflow, provider, matched, verdict, findings_count,
                    total_duration_ms, estimated_cost_usd, started_at, finished_at, comparison_group,
                    result_json, created_at
                FROM runs WHERE id = ?""",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return HistoryDetail(**_row_to_entry(row).model_dump(), result=json.loads(row["result_json"]))

    async def get_run(self, run_id: int) -> HistoryDetail | None:
        return await asyncio.to_thread(self._get_run_sync, run_id)

    def _get_comparison_sync(self, comparison_group: str) -> ComparisonHistoryEntry | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT comparison_group, ticket_id, comparison_json, created_at FROM comparisons "
                "WHERE comparison_group = ?",
                (comparison_group,),
            ).fetchone()
        if row is None:
            return None
        return ComparisonHistoryEntry(
            comparison_group=row["comparison_group"],
            ticket_id=row["ticket_id"],
            comparison=json.loads(row["comparison_json"]),
            created_at=row["created_at"],
        )

    async def get_comparison(self, comparison_group: str) -> ComparisonHistoryEntry | None:
        return await asyncio.to_thread(self._get_comparison_sync, comparison_group)

    def _stats_sync(self) -> HistoryStats:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]
            passed = conn.execute("SELECT COUNT(*) AS c FROM runs WHERE verdict = 'pass'").fetchone()["c"]
            failed = conn.execute("SELECT COUNT(*) AS c FROM runs WHERE verdict = 'fail'").fetchone()["c"]
            unmatched = conn.execute("SELECT COUNT(*) AS c FROM runs WHERE matched = 0").fetchone()["c"]
            avg_duration = conn.execute("SELECT AVG(total_duration_ms) AS a FROM runs").fetchone()["a"] or 0.0
            total_cost = conn.execute("SELECT SUM(estimated_cost_usd) AS s FROM runs").fetchone()["s"] or 0.0
            by_provider_rows = conn.execute("SELECT provider, COUNT(*) AS c FROM runs GROUP BY provider").fetchall()
        return HistoryStats(
            total_runs=total,
            passed=passed,
            failed=failed,
            unmatched=unmatched,
            avg_duration_ms=avg_duration,
            total_cost_usd=total_cost,
            by_provider={row["provider"]: row["c"] for row in by_provider_rows},
        )

    async def stats(self) -> HistoryStats:
        return await asyncio.to_thread(self._stats_sync)

    def _provider_stats_sync(self) -> list[ProviderStats]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT provider, verdict, total_duration_ms, estimated_cost_usd, result_json FROM runs"
            ).fetchall()

        by_provider: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            by_provider.setdefault(row["provider"], []).append(row)

        stats: list[ProviderStats] = []
        for provider, provider_rows in by_provider.items():
            run_count = len(provider_rows)
            pass_count = sum(1 for r in provider_rows if r["verdict"] == "pass")
            fail_count = sum(1 for r in provider_rows if r["verdict"] == "fail")
            avg_duration = sum(r["total_duration_ms"] for r in provider_rows) / run_count
            total_cost = sum(r["estimated_cost_usd"] for r in provider_rows)

            coverage_ratios, accuracy_ratios = [], []
            missed_steps: Counter[str] = Counter()
            for r in provider_rows:
                metrics = json.loads(r["result_json"]).get("metrics")
                if metrics:
                    coverage_ratios.append(metrics["coverage_ratio"])
                    accuracy_ratios.append(metrics["accuracy_ratio"])
                    missed_steps.update(metrics.get("missed_steps", []))

            stats.append(
                ProviderStats(
                    provider=provider,
                    run_count=run_count,
                    pass_count=pass_count,
                    fail_count=fail_count,
                    avg_duration_ms=avg_duration,
                    avg_coverage_ratio=(sum(coverage_ratios) / len(coverage_ratios)) if coverage_ratios else 0.0,
                    avg_accuracy_ratio=(sum(accuracy_ratios) / len(accuracy_ratios)) if accuracy_ratios else 0.0,
                    avg_cost_usd=(total_cost / run_count) if run_count else 0.0,
                    total_cost_usd=total_cost,
                    common_missed_steps=[
                        MissedStepCount(step=step, count=count) for step, count in missed_steps.most_common(5)
                    ],
                )
            )
        return stats

    async def provider_stats(self) -> list[ProviderStats]:
        return await asyncio.to_thread(self._provider_stats_sync)

    def _daily_stats_sync(self, days: int) -> list[DailyStat]:
        cutoff = time.time() - days * 86400
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT created_at, verdict, estimated_cost_usd, total_duration_ms FROM runs WHERE created_at >= ?",
                (cutoff,),
            ).fetchall()

        buckets: dict[str, dict] = {}
        for row in rows:
            day = time.strftime("%Y-%m-%d", time.gmtime(row["created_at"]))
            bucket = buckets.setdefault(day, {"total": 0, "passed": 0, "failed": 0, "cost": 0.0, "duration": 0.0})
            bucket["total"] += 1
            if row["verdict"] == "pass":
                bucket["passed"] += 1
            elif row["verdict"] == "fail":
                bucket["failed"] += 1
            bucket["cost"] += row["estimated_cost_usd"]
            bucket["duration"] += row["total_duration_ms"]

        return [
            DailyStat(
                date=day,
                total=b["total"],
                passed=b["passed"],
                failed=b["failed"],
                total_cost_usd=b["cost"],
                avg_duration_ms=(b["duration"] / b["total"]) if b["total"] else 0.0,
            )
            for day, b in sorted(buckets.items())
        ]

    async def daily_stats(self, days: int = 7) -> list[DailyStat]:
        return await asyncio.to_thread(self._daily_stats_sync, days)


def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        id=row["id"],
        ticket_id=row["ticket_id"],
        domain=row["domain"],
        workflow=row["workflow"],
        provider=row["provider"],
        matched=bool(row["matched"]),
        verdict=row["verdict"],
        findings_count=row["findings_count"],
        total_duration_ms=row["total_duration_ms"],
        estimated_cost_usd=row["estimated_cost_usd"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        comparison_group=row["comparison_group"],
        created_at=row["created_at"],
    )
