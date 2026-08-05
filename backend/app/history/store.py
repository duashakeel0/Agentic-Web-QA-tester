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
from contextlib import contextmanager

from app.agents.schema import ComparisonReport, PipelineResult
from app.history.schema import ComparisonHistoryEntry, HistoryDetail, HistoryEntry, HistoryStats

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
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO runs (
                    ticket_id, domain, workflow, provider, matched, verdict, findings_count,
                    total_duration_ms, started_at, finished_at, comparison_group, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.ticket_id, result.plan.domain, result.plan.workflow, result.provider,
                    int(result.plan.matched), verdict, findings_count, result.total_duration_ms,
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
                    total_duration_ms, started_at, finished_at, comparison_group, created_at
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
                    total_duration_ms, started_at, finished_at, comparison_group, result_json, created_at
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
            by_provider_rows = conn.execute("SELECT provider, COUNT(*) AS c FROM runs GROUP BY provider").fetchall()
        return HistoryStats(
            total_runs=total,
            passed=passed,
            failed=failed,
            unmatched=unmatched,
            avg_duration_ms=avg_duration,
            by_provider={row["provider"]: row["c"] for row in by_provider_rows},
        )

    async def stats(self) -> HistoryStats:
        return await asyncio.to_thread(self._stats_sync)


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
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        comparison_group=row["comparison_group"],
        created_at=row["created_at"],
    )
