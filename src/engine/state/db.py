import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from engine.state.models import RunRecord, VerificationResult

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
