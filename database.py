import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "worklog.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project     TEXT    NOT NULL,
                description TEXT,
                task_type   TEXT    NOT NULL DEFAULT 'manual',
                actual_hours REAL   NOT NULL,
                manual_estimate REAL,
                timestamp   INTEGER NOT NULL,
                date        TEXT    NOT NULL,
                metadata    TEXT,
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.commit()


def save_session(project, description, task_type, actual_hours,
                 manual_estimate=None, timestamp=None, date=None, metadata=None):
    import time
    from datetime import datetime, timezone
    ts = timestamp or int(time.time() * 1000)
    dt = date or datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    meta_str = json.dumps(metadata) if metadata else None

    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO sessions
               (project, description, task_type, actual_hours, manual_estimate,
                timestamp, date, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (project, description, task_type, actual_hours,
             manual_estimate, ts, dt, meta_str)
        )
        conn.commit()
        return cur.lastrowid


def get_sessions(limit=200):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)            AS total_sessions,
                ROUND(SUM(actual_hours), 2) AS total_hours,
                ROUND(SUM(CASE WHEN manual_estimate IS NOT NULL
                          THEN MAX(0, manual_estimate - actual_hours)
                          ELSE 0 END), 2) AS hours_saved,
                COUNT(DISTINCT project) AS project_count
            FROM sessions
        """).fetchone()
        return dict(row)


def delete_session(session_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
