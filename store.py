"""SQLite persistence: interview sessions and the audit log.

Sessions track interview progress so /rollout_status has something to
report. The audit log is append-only and is never wiped.

The database file is created automatically if it doesn't exist. If it can't
be opened, every store call becomes a no-op and the bot keeps running — just
without sessions or an audit log.
"""

import json
import logging
import sqlite3

log = logging.getLogger("blahajd.store")

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
_disabled = False


def init(db_path: str) -> None:
    """Create the database and tables if needed, preserving existing records."""
    global _db_path, _disabled
    _db_path = db_path
    _disabled = False

    # a fresh connection per call keeps things simple; the workload here is tiny
    try:
        with sqlite3.connect(_db_path) as conn:
            conn.executescript(SCHEMA)
    except sqlite3.Error:
        log.warning(
            "could not open database %s — running without persistence", db_path,
            exc_info=True,
        )
        _disabled = True


def _conn() -> sqlite3.Connection:
    if _disabled or _db_path is None:
        raise RuntimeError("store.init() must be called before any store use")
    return sqlite3.connect(_db_path)


def upsert_session(user_id: int, answers: dict[str, object], status: str) -> None:
    if _disabled:
        return
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
    if _disabled:
        counts["total"] = 0
        return counts
    with _conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM sessions GROUP BY status").fetchall()
    for status, n in rows:
        counts[status] = n
    counts["total"] = sum(counts.values())
    return counts


def clear_sessions() -> None:
    if _disabled:
        return
    with _conn() as conn:
        conn.execute("DELETE FROM sessions")


def log_action(user_id: int, action: str, details: str) -> None:
    if _disabled:
        return
    with _conn() as conn:
        conn.execute(
            "INSERT INTO audit_log (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details),
        )
