import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "goals.db"
MAX_TITLE_LENGTH = 160
MAX_DETAILS_LENGTH = 1000


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'completed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return connection


def add_goal(title, details=""):
    title = title.strip() if isinstance(title, str) else ""
    details = details.strip() if isinstance(details, str) else ""
    if not title:
        raise ValueError("Goal title cannot be empty.")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Goal title must be {MAX_TITLE_LENGTH} characters or fewer.")
    if len(details) > MAX_DETAILS_LENGTH:
        raise ValueError(f"Goal details must be {MAX_DETAILS_LENGTH} characters or fewer.")

    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO goals (title, details) VALUES (?, ?)",
            (title, details),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def list_goals(include_completed=True):
    connection = _connect()
    try:
        status_filter = "" if include_completed else "WHERE status = 'active'"
        rows = connection.execute(
            "SELECT id, title, details, status, created_at FROM goals "
            + status_filter
            + " ORDER BY status, id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_goal(goal_id):
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT id, title, details, status, created_at FROM goals WHERE id = ?",
            (goal_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def set_goal_status(goal_id, status):
    if status not in ("active", "completed"):
        raise ValueError("Goal status must be active or completed.")
    connection = _connect()
    try:
        cursor = connection.execute(
            "UPDATE goals SET status = ? WHERE id = ?",
            (status, goal_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()