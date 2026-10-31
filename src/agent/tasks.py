"""Local task tracking for explicit assistant requests."""
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "tasks.db"
MAX_TITLE_LENGTH = 500


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'completed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
    """)
    return connection


def add_task(title, due_date=None):
    title = title.strip() if isinstance(title, str) else ""
    if not title:
        raise ValueError("Task title cannot be empty.")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Task title must be {MAX_TITLE_LENGTH} characters or fewer.")
    if due_date is not None:
        if not isinstance(due_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
            raise ValueError("Due date must use YYYY-MM-DD format.")
        try:
            due_date = date.fromisoformat(due_date).isoformat()
        except (TypeError, ValueError) as error:
            raise ValueError("Due date must use YYYY-MM-DD format.") from error

    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO tasks (title, due_date) VALUES (?, ?)",
            (title, due_date),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def list_tasks(include_completed=False):
    connection = _connect()
    try:
        if include_completed:
            rows = connection.execute(
                "SELECT id, title, due_date, status, created_at, completed_at "
                "FROM tasks ORDER BY status, due_date IS NULL, due_date, id"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id, title, due_date, status, created_at, completed_at "
                "FROM tasks WHERE status = 'open' "
                "ORDER BY due_date IS NULL, due_date, id"
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def search_tasks(query, include_completed=False):
    """Find tasks by title, case-insensitively, without interpreting SQL wildcards."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Task search cannot be empty.")
    escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    connection = _connect()
    try:
        status_filter = "" if include_completed else "AND status = 'open'"
        rows = connection.execute(
            "SELECT id, title, due_date, status, created_at, completed_at "
            "FROM tasks WHERE title LIKE ? ESCAPE '\\' " + status_filter +
            " ORDER BY due_date IS NULL, due_date, id",
            (f"%{escaped}%",),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_task(task_id, title=None, due_date=None, clear_due_date=False):
    """Update an open task. None leaves a field unchanged; clear_due_date clears it."""
    if title is not None:
        title = title.strip() if isinstance(title, str) else ""
        if not title:
            raise ValueError("Task title cannot be empty.")
        if len(title) > MAX_TITLE_LENGTH:
            raise ValueError(f"Task title must be {MAX_TITLE_LENGTH} characters or fewer.")
    if due_date is not None:
        if not isinstance(due_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
            raise ValueError("Due date must use YYYY-MM-DD format.")
        try:
            due_date = date.fromisoformat(due_date).isoformat()
        except (TypeError, ValueError) as error:
            raise ValueError("Due date must use YYYY-MM-DD format.") from error
    if clear_due_date and due_date is not None:
        raise ValueError("Choose a due date or clear the due date, not both.")
    if title is None and due_date is None and not clear_due_date:
        raise ValueError("Provide a new title or due date.")

    assignments = []
    values = []
    if title is not None:
        assignments.append("title = ?")
        values.append(title)
    if due_date is not None or clear_due_date:
        assignments.append("due_date = ?")
        values.append(None if clear_due_date else due_date)
    values.append(task_id)

    connection = _connect()
    try:
        cursor = connection.execute(
            "UPDATE tasks SET " + ", ".join(assignments) +
            " WHERE id = ? AND status = 'open'",
            values,
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def task_overview(today=None, days=7):
    """Return open tasks grouped as overdue, due today, and due soon."""
    today = today or date.today()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    end_date = today + timedelta(days=max(1, int(days)))
    open_tasks = list_tasks()
    return {
        "overdue": [task for task in open_tasks if task["due_date"] and task["due_date"] < today.isoformat()],
        "today": [task for task in open_tasks if task["due_date"] == today.isoformat()],
        "upcoming": [task for task in open_tasks if today.isoformat() < (task["due_date"] or "") <= end_date.isoformat()],
    }


def complete_task(task_id):
    connection = _connect()
    try:
        cursor = connection.execute(
            "UPDATE tasks SET status = 'completed', "
            "completed_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'open'",
            (task_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()
