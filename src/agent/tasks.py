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
            goal_id INTEGER,
            status TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'completed', 'ignored')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            ignored_at TEXT
        )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
    if "goal_id" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN goal_id INTEGER")
    if "ignored_at" not in columns:
        connection.execute("ALTER TABLE tasks ADD COLUMN ignored_at TEXT")
    schema = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tasks'"
    ).fetchone()[0]
    if "'ignored'" not in schema:
        connection.execute("ALTER TABLE tasks RENAME TO tasks_before_ignore")
        connection.execute("""
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                due_date TEXT,
                goal_id INTEGER,
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'completed', 'ignored')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                ignored_at TEXT
            )
        """)
        connection.execute(
            "INSERT INTO tasks (id, title, due_date, goal_id, status, created_at, "
            "completed_at, ignored_at) SELECT id, title, due_date, goal_id, status, "
            "created_at, completed_at, ignored_at FROM tasks_before_ignore"
        )
        connection.execute("DROP TABLE tasks_before_ignore")
    return connection


def _validate_goal_id(goal_id):
    if goal_id is None:
        return None
    if isinstance(goal_id, bool) or not isinstance(goal_id, (int, str)):
        raise ValueError("Goal ID must be a whole number.")
    try:
        goal_id = int(goal_id)
    except ValueError as error:
        raise ValueError("Goal ID must be a whole number.") from error
    from src.agent.goals import get_goal
    goal = get_goal(goal_id)
    if not goal or goal["status"] != "active":
        raise ValueError("Choose an active goal.")
    return goal_id


def add_task(title, due_date=None, goal_id=None):
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
    goal_id = _validate_goal_id(goal_id)

    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO tasks (title, due_date, goal_id) VALUES (?, ?, ?)",
            (title, due_date, goal_id),
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
                "SELECT id, title, due_date, goal_id, status, created_at, completed_at, ignored_at "
                "FROM tasks ORDER BY status, due_date IS NULL, due_date, id"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id, title, due_date, goal_id, status, created_at, completed_at, ignored_at "
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
            "SELECT id, title, due_date, goal_id, status, created_at, completed_at, ignored_at "
            "FROM tasks WHERE title LIKE ? ESCAPE '\\' " + status_filter +
            " ORDER BY due_date IS NULL, due_date, id",
            (f"%{escaped}%",),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def update_task(task_id, title=None, due_date=None, clear_due_date=False,
                goal_id=None, clear_goal=False):
    """Update an open task. None leaves a field unchanged; clear flags clear fields."""
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
    if clear_goal and goal_id is not None:
        raise ValueError("Choose a goal or clear the goal, not both.")
    if goal_id is not None:
        goal_id = _validate_goal_id(goal_id)
    if title is None and due_date is None and not clear_due_date and goal_id is None and not clear_goal:
        raise ValueError("Provide a new title or due date.")

    assignments = []
    values = []
    if title is not None:
        assignments.append("title = ?")
        values.append(title)
    if due_date is not None or clear_due_date:
        assignments.append("due_date = ?")
        values.append(None if clear_due_date else due_date)
    if goal_id is not None or clear_goal:
        assignments.append("goal_id = ?")
        values.append(None if clear_goal else goal_id)
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
    task = None
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT title FROM tasks WHERE id = ? AND status = 'open'", (task_id,)
        ).fetchone()
        task = row["title"] if row else None
        cursor = connection.execute(
            "UPDATE tasks SET status = 'completed', "
            "completed_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'open'",
            (task_id,),
        )
        connection.commit()
        changed = cursor.rowcount > 0
    finally:
        connection.close()
    if changed and task is not None:
        from src.agent.interests import record_action
        record_action("task_completed", task, "task", task_id,
                      "Task was explicitly marked complete.")
    return changed


def ignore_task(task_id):
    connection = _connect()
    try:
        row = connection.execute(
            "SELECT title FROM tasks WHERE id = ? AND status = 'open'", (task_id,)
        ).fetchone()
        title = row["title"] if row else None
        cursor = connection.execute(
            "UPDATE tasks SET status = 'ignored', ignored_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'open'",
            (task_id,),
        )
        connection.commit()
        changed = cursor.rowcount > 0
    finally:
        connection.close()
    if changed and title is not None:
        from src.agent.interests import record_action
        record_action("task_ignored", title, "task", task_id,
                      "Task was explicitly marked ignored.")
    return changed
