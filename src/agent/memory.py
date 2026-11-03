import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "memory.db"


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return connection


def save_memory(content):
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO memories (content) VALUES (?)",
            (content,)
        )
        return cursor.lastrowid


def get_memories():
    with get_connection() as connection:
        return connection.execute(
            "SELECT id, content, created_at FROM memories ORDER BY id"
        ).fetchall()


def search_memories(query):
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with get_connection() as connection:
        return connection.execute(
            "SELECT id, content, created_at FROM memories WHERE content LIKE ? ESCAPE '\\' ORDER BY id",
            (f"%{escaped}%",)
        ).fetchall()


def update_memory(memory_id, content):
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE memories SET content = ? WHERE id = ?",
            (content, memory_id)
        )
        return cursor.rowcount > 0


def delete_memory(memory_id):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,)
        )
        return cursor.rowcount > 0
