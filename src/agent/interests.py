"""Explainable, bounded interest weights learned from explicit user actions."""

import re
from itertools import combinations

from src.agent import agent_state

TOPICS = {
    "technology": {"technology", "software", "ai", "computer", "programming", "startup"},
    "health": {"health", "medical", "fitness", "exercise", "wellness", "medicine"},
    "work": {"work", "career", "business", "company", "management", "job"},
    "finance": {"finance", "money", "bank", "investment", "tax", "economy"},
    "science": {"science", "research", "space", "physics", "biology", "climate"},
    "politics": {"politics", "government", "election", "policy", "law"},
    "culture": {"culture", "art", "music", "film", "book", "food", "travel"},
    "education": {"education", "learning", "school", "university", "course"},
    "environment": {"environment", "energy", "nature", "wildlife", "sustainability"},
    "local": {"local", "community", "neighborhood", "city", "regional"},
}
SIGNALS = {
    "news_relevant": 0.08,
    "news_not_interested": -0.18,
    "task_completed": 0.04,
    "task_ignored": -0.06,
    "email_interaction": 0.025,
    "goal_link": 0.04,
}


def classify_topics(*texts):
    tokens = set()
    for text in texts:
        if isinstance(text, str):
            tokens.update(re.findall(r"[a-z0-9]+", text.casefold()))
    return [
        topic for topic, words in TOPICS.items()
        if tokens.intersection(words)
    ] or ["general"]


def record_action(action, text="", entity_type="", entity_id="", reason=""):
    if action not in SIGNALS:
        raise ValueError("Unknown interest action.")
    delta = SIGNALS[action]
    topics = classify_topics(text)
    recorded = False
    with agent_state.connect() as connection:
        for topic in topics:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO interest_events "
                "(topic, delta, action, entity_type, entity_id, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (topic, delta, action, entity_type, str(entity_id), reason),
            )
            if cursor.rowcount:
                recorded = True
                connection.execute(
                    "INSERT INTO interest_nodes (topic, weight) VALUES (?, ?) "
                    "ON CONFLICT(topic) DO UPDATE SET "
                    "weight = MIN(1, MAX(0, interest_nodes.weight + excluded.weight - 0.5)), "
                    "updated_at = CURRENT_TIMESTAMP",
                    (topic, min(1.0, max(0.0, 0.5 + delta))),
                )
        edge_pairs = combinations(sorted(topics), 2) if recorded else ()
        for source, target in edge_pairs:
            connection.execute(
                "INSERT INTO interest_edges (source_topic, target_topic, strength) "
                "VALUES (?, ?, 0.08) ON CONFLICT(source_topic, target_topic) "
                "DO UPDATE SET strength = MIN(1, interest_edges.strength + 0.04), "
                "updated_at = CURRENT_TIMESTAMP",
                (source, target),
            )
    agent_state.add_decision(
        "interest_update", action.replace("_", " "),
        reason or "Interest weights updated from explicit user behavior.",
        {"topics": topics, "delta": delta},
    )
    return topics


def list_interests():
    with agent_state.connect() as connection:
        rows = connection.execute(
            "SELECT topic, weight, source, updated_at FROM interest_nodes "
            "ORDER BY weight DESC, topic"
        ).fetchall()
        events = connection.execute(
            "SELECT topic, action, delta, reason, created_at FROM interest_events "
            "ORDER BY id DESC LIMIT 100"
        ).fetchall()
        edges = connection.execute(
            "SELECT source_topic, target_topic, strength, updated_at "
            "FROM interest_edges ORDER BY strength DESC, source_topic, target_topic"
        ).fetchall()
    return {"interests": [dict(row) for row in rows],
            "recent_events": [dict(row) for row in events],
            "edges": [dict(row) for row in edges]}


def set_interest(topic, weight):
    if not isinstance(topic, str) or topic not in set(TOPICS) | {"general"}:
        raise ValueError("Choose one of the controlled interest topics.")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise ValueError("Interest weight must be a number between 0 and 1.")
    if not 0 <= weight <= 1:
        raise ValueError("Interest weight must be a number between 0 and 1.")
    with agent_state.connect() as connection:
        connection.execute(
            "INSERT INTO interest_nodes (topic, weight, source) VALUES (?, ?, 'manual') "
            "ON CONFLICT(topic) DO UPDATE SET weight = excluded.weight, "
            "source = 'manual', updated_at = CURRENT_TIMESTAMP",
            (topic, float(weight)),
        )
    agent_state.add_decision(
        "interest_edited", topic, "Interest weight manually edited",
        {"weight": float(weight)},
    )
