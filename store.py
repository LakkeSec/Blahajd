"""SQLite persistence: interview sessions and the audit log.

Sessions exist so a rollout can be resumed and so /rollout_status has
something to report. The audit log is append-only and is never wiped.
"""

import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    user_id    INTEGER PRIMARY KEY,
    answers    TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'sent',
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      TEXT    NOT NULL DEFAULT (datetime('now')),
    user_id INTEGER NOT NULL,
    action  TEXT    NOT NULL,
    details TEXT    NOT NULL
);
"""

# session statuses: sent (DM'd, no answers yet), active (mid-interview),
# pending (request submitted, awaiting mod approval), completed,
# rejected, cancelled
STATUSES = ("sent", "active", "pending", "completed", "rejected", "cancelled")

_db_path: str | None = None


def init(db_path: str) -> None:
    global _db_path
    _db_path = db_path
    # a fresh connection per call keeps things simple; the workload here is tiny
    with sqlite3.connect(_db_path) as conn:
        conn.executescript(SCHEMA)


def _conn() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("store.init() must be called before any store use")
    return sqlite3.connect(_db_path)


def upsert_session(user_id: int, answers: dict[str, str], status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown session status: {status}")
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO sessions (user_id, answers, status, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                answers = excluded.answers,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (user_id, json.dumps(answers), status),
        )


def status_counts() -> dict[str, int]:
    counts = {status: 0 for status in STATUSES}
    with _conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM sessions GROUP BY status").fetchall()
    for status, n in rows:
        counts[status] = n
    counts["total"] = sum(counts.values())
    return counts


def clear_sessions() -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM sessions")


def log_action(user_id: int, action: str, details: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details),
        )
