import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "recommendations.db"
MAX_TITLE_LENGTH = 200
MAX_TEXT_LENGTH = 2000


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'declined')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            decided_at TEXT
        )
    """)
    return connection


def add_recommendation(title, rationale="", evidence=""):
    title = title.strip() if isinstance(title, str) else ""
    rationale = rationale.strip() if isinstance(rationale, str) else ""
    evidence = evidence.strip() if isinstance(evidence, str) else ""
    if not title:
        raise ValueError("Recommendation title cannot be empty.")
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Recommendation title must be {MAX_TITLE_LENGTH} characters or fewer.")
    if len(rationale) > MAX_TEXT_LENGTH or len(evidence) > MAX_TEXT_LENGTH:
        raise ValueError(f"Recommendation details must be {MAX_TEXT_LENGTH} characters or fewer.")
    connection = _connect()
    try:
        cursor = connection.execute(
            "INSERT INTO recommendations (title, rationale, evidence) VALUES (?, ?, ?)",
            (title, rationale, evidence),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def list_recommendations():
    connection = _connect()
    try:
        rows = connection.execute(
            "SELECT id, title, rationale, evidence, status, created_at, decided_at "
            "FROM recommendations ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def decide_recommendation(recommendation_id, decision):
    if decision not in ("accepted", "declined"):
        raise ValueError("Decision must be accepted or declined.")
    connection = _connect()
    try:
        cursor = connection.execute(
            "UPDATE recommendations SET status = ?, decided_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'pending'",
            (decision, recommendation_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()