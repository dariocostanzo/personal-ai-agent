"""SQLite state shared by agent capabilities, feedback, and transparency views."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "agent_state.db"


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS interest_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL UNIQUE,
            weight REAL NOT NULL DEFAULT 0.5 CHECK (weight >= 0 AND weight <= 1),
            source TEXT NOT NULL DEFAULT 'learned'
                CHECK (source IN ('learned', 'manual')),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS interest_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            delta REAL NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(action, entity_type, entity_id, topic)
        );
        CREATE TABLE IF NOT EXISTS interest_edges (
            source_topic TEXT NOT NULL,
            target_topic TEXT NOT NULL,
            strength REAL NOT NULL DEFAULT 0.1
                CHECK (strength >= 0 AND strength <= 1),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (source_topic, target_topic),
            CHECK (source_topic < target_topic)
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            subject TEXT NOT NULL,
            reason TEXT NOT NULL,
            context TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'rejected')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS model_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capability TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            locality TEXT NOT NULL CHECK (locality IN ('local', 'cloud')),
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost REAL NOT NULL DEFAULT 0,
            privacy_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS guardian_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('healthy', 'attention')),
            details TEXT NOT NULL,
            checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS guardian_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS agent_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    return connection


def add_decision(action, subject, reason, context=None):
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO decisions (action, subject, reason, context) "
            "VALUES (?, ?, ?, ?)",
            (action, subject, reason, json.dumps(context or {}, ensure_ascii=False)),
        )
        return cursor.lastrowid


def list_decisions(limit=100):
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, action, subject, reason, context, created_at "
            "FROM decisions ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["context"] = json.loads(item["context"])
        result.append(item)
    return result


def record_usage(capability, provider, model, locality, input_tokens,
                 output_tokens, estimated_cost=0, privacy_note=""):
    with connect() as connection:
        connection.execute(
            "INSERT INTO model_usage "
            "(capability, provider, model, locality, input_tokens, output_tokens, "
            "estimated_cost, privacy_note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (capability, provider, model, locality, max(0, int(input_tokens)),
             max(0, int(output_tokens)), max(0.0, float(estimated_cost)), privacy_note),
        )


def usage_summary():
    with connect() as connection:
        rows = connection.execute(
            "SELECT locality, SUM(input_tokens) AS input_tokens, "
            "SUM(output_tokens) AS output_tokens, SUM(estimated_cost) AS cost "
            "FROM model_usage GROUP BY locality"
        ).fetchall()
    totals = {
        "local": {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0},
        "cloud": {"input_tokens": 0, "output_tokens": 0, "estimated_cost": 0.0},
    }
    for row in rows:
        totals[row["locality"]] = {
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "estimated_cost": row["cost"] or 0.0,
        }
    return totals


def add_guardian_check(name, status, details):
    with connect() as connection:
        connection.execute(
            "INSERT INTO guardian_checks (name, status, details) VALUES (?, ?, ?)",
            (name, status, details),
        )


def list_guardian_checks(limit=100):
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, name, status, details, checked_at FROM guardian_checks "
            "ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_guardian_checks():
    with connect() as connection:
        rows = connection.execute("""
            SELECT check_result.id, check_result.name, check_result.status,
                   check_result.details, check_result.checked_at
            FROM guardian_checks AS check_result
            JOIN (
                SELECT name, MAX(id) AS id
                FROM guardian_checks
                GROUP BY name
            ) AS latest ON latest.id = check_result.id
            ORDER BY check_result.name
        """).fetchall()
    return [dict(row) for row in rows]


def add_proposal(kind, title, details="", payload=None):
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO proposals (kind, title, details, payload) VALUES (?, ?, ?, ?)",
            (kind, title, details, json.dumps(payload or {}, ensure_ascii=False)),
        )
        return cursor.lastrowid


def list_proposals():
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, kind, title, details, payload, status, created_at, reviewed_at "
            "FROM proposals ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, id DESC"
        ).fetchall()
    proposals = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        proposals.append(item)
    return proposals


def get_proposal(proposal_id):
    with connect() as connection:
        row = connection.execute(
            "SELECT id, kind, title, details, payload, status, created_at, reviewed_at "
            "FROM proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["payload"] = json.loads(item["payload"])
    return item


def review_proposal(proposal_id, decision, title=None, details=None, payload=None):
    if decision not in ("accepted", "rejected"):
        raise ValueError("Proposal decision must be accepted or rejected.")
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE proposals SET status = ?, title = COALESCE(?, title), "
            "details = COALESCE(?, details), payload = COALESCE(?, payload), "
            "reviewed_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND status = 'pending'",
            (decision, title, details,
             json.dumps(payload, ensure_ascii=False) if payload is not None else None,
             proposal_id),
        )
        return cursor.rowcount > 0
