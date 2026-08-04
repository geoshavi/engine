import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from engine.state.models import (
    AgentExecutionMetric,
    AgentExecutionRecord,
    RunRecord,
    VerificationResult,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS verification_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    attempt_number INTEGER NOT NULL,
    gate_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS defects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    attempt_number INTEGER NOT NULL,
    defect_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    location TEXT NOT NULL,
    fix TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    attempt_number INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    subtask_text TEXT NOT NULL,
    success INTEGER NOT NULL,
    produced_files TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_execution_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    task_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_read_tokens INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    actual_spend TEXT,
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_run(conn: sqlite3.Connection, task_text: str, provider: str, model: str) -> int:
    cursor = conn.execute(
        "INSERT INTO runs (task_text, provider, model) VALUES (?, ?, ?)",
        (task_text, provider, model),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def record_verification(
    conn: sqlite3.Connection, run_id: int, attempt_number: int, results: list[VerificationResult]
) -> None:
    conn.executemany(
        "INSERT INTO verification_results (run_id, attempt_number, gate_name, passed, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        [(run_id, attempt_number, r.gate_name, int(r.passed), r.detail) for r in results],
    )


def record_defects(
    conn: sqlite3.Connection, run_id: int, attempt_number: int, defects: list[dict]
) -> None:
    conn.executemany(
        "INSERT INTO defects (run_id, attempt_number, defect_id, category, severity, location, fix) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                run_id,
                attempt_number,
                d.get("id", ""),
                d.get("category", ""),
                d.get("severity", ""),
                d.get("location", ""),
                d.get("fix", ""),
            )
            for d in defects
        ],
    )


def record_agent_executions(
    conn: sqlite3.Connection, run_id: int, attempt_number: int, records: list[AgentExecutionRecord]
) -> None:
    conn.executemany(
        "INSERT INTO agent_executions "
        "(run_id, attempt_number, agent_name, agent_role, subtask_text, success, produced_files, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                run_id,
                attempt_number,
                r.agent_name,
                r.agent_role,
                r.subtask_text,
                int(r.success),
                json.dumps(r.produced_files),
                r.error,
            )
            for r in records
        ],
    )


def record_agent_execution_metric(conn: sqlite3.Connection, metric: AgentExecutionMetric) -> None:
    """Written by the Gateway after every LLM call -- success or failure.
    ``actual_spend`` is stored as TEXT (``str(Decimal)``), never as a
    numeric SQLite column, so it round-trips at full precision instead of
    passing through SQLite's float-based REAL storage class.
    """
    conn.execute(
        "INSERT INTO agent_execution_metrics "
        "(run_id, task_id, agent_name, model, input_tokens, output_tokens, "
        "cache_read_tokens, cache_creation_tokens, latency_ms, actual_spend, status, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            metric.run_id,
            metric.task_id,
            metric.agent_name,
            metric.model,
            metric.input_tokens,
            metric.output_tokens,
            metric.cache_read_tokens,
            metric.cache_creation_tokens,
            metric.latency_ms,
            str(metric.actual_spend) if metric.actual_spend is not None else None,
            metric.status,
            metric.error,
        ),
    )


def get_agent_execution_metrics(conn: sqlite3.Connection, run_id: int) -> list[AgentExecutionMetric]:
    rows = conn.execute(
        "SELECT run_id, task_id, agent_name, model, input_tokens, output_tokens, "
        "cache_read_tokens, cache_creation_tokens, latency_ms, actual_spend, status, error "
        "FROM agent_execution_metrics WHERE run_id = ? ORDER BY id",
        (run_id,),
    ).fetchall()
    return [
        AgentExecutionMetric(
            run_id=row[0],
            task_id=row[1],
            agent_name=row[2],
            model=row[3],
            input_tokens=row[4],
            output_tokens=row[5],
            cache_read_tokens=row[6],
            cache_creation_tokens=row[7],
            latency_ms=row[8],
            actual_spend=Decimal(row[9]) if row[9] is not None else None,
            status=row[10],
            error=row[11],
        )
        for row in rows
    ]


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, attempts: int) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, attempts = ?, finished_at = datetime('now') WHERE id = ?",
        (status, attempts, run_id),
    )


def get_run(conn: sqlite3.Connection, run_id: int) -> RunRecord | None:
    row = conn.execute(
        "SELECT id, task_text, provider, model, status, attempts, created_at, finished_at "
        "FROM runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return RunRecord(*row)
