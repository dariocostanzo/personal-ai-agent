import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "sessions.db"


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS session_metadata (
            conversation_id TEXT PRIMARY KEY,
            goal_id INTEGER,
            needs_attention INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return connection


def list_session_metadata():
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT conversation_id, goal_id, needs_attention, updated_at "
            "FROM session_metadata"
        ).fetchall()
        return {row["conversation_id"]: dict(row) for row in rows}
    finally:
        connection.close()


def set_session_goal(conversation_id, goal_id):
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("Conversation ID cannot be empty.")
    if goal_id is not None:
        from src.agent.goals import get_goal
        goal = get_goal(goal_id)
        if not goal:
            raise ValueError("Goal not found.")
    connection = _connect()
    try:
        connection.execute(
            "INSERT INTO session_metadata (conversation_id, goal_id) VALUES (?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET "
            "goal_id = excluded.goal_id, updated_at = CURRENT_TIMESTAMP",
            (conversation_id, goal_id),
        )
        connection.commit()
    finally:
        connection.close()


def set_needs_attention(conversation_id, needs_attention):
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("Conversation ID cannot be empty.")
    if not isinstance(needs_attention, bool):
        raise ValueError("Attention state must be true or false.")
    connection = _connect()
    try:
        connection.execute(
            "INSERT INTO session_metadata (conversation_id, needs_attention) "
            "VALUES (?, ?) ON CONFLICT(conversation_id) DO UPDATE SET "
            "needs_attention = excluded.needs_attention, updated_at = CURRENT_TIMESTAMP",
            (conversation_id, int(needs_attention)),
        )
        connection.commit()
    finally:
        connection.close()