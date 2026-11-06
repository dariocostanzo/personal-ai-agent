"""Local RSS, web, and folder ingestion for the daily news digest."""

import email
import hashlib
import html
import json
import math
import os
import re
import sqlite3
from difflib import SequenceMatcher
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email import policy
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from src.agent import agent_state, interests
from src.agent.config import OLLAMA_BASE_URL, OLLAMA_MODEL

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "news.db"
LOCAL_DATA = DB_PATH.parent
MAX_FEED_BYTES = 2_000_000
MAX_ITEMS_PER_SOURCE = 250
MAX_LOCAL_FILE_BYTES = 5_000_000
TOPIC_TAGS = tuple(interests.TOPICS)
_EMBEDDING_AVAILABLE = None


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS news_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('rss', 'website', 'folder', 'newsletter')),
            location TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_checked_at TEXT,
            last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS news_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            published_at TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            embedding TEXT,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(event_key)
        );
        CREATE TABLE IF NOT EXISTS news_item_sources (
            item_id INTEGER NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
            source_id INTEGER NOT NULL REFERENCES news_sources(id) ON DELETE CASCADE,
            source_link TEXT NOT NULL DEFAULT '',
            seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (item_id, source_id, source_link)
        );
        CREATE TABLE IF NOT EXISTS news_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT NOT NULL CHECK (run_type IN ('full', 'incremental')),
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            items_seen INTEGER NOT NULL DEFAULT 0,
            items_added INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            details TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS news_items_published ON news_items(published_at);
    """)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def add_source(name, kind, location):
    name = name.strip() if isinstance(name, str) else ""
    location = location.strip() if isinstance(location, str) else ""
    if kind not in ("rss", "website", "folder", "newsletter"):
        raise ValueError("Source type must be RSS, website, folder, or newsletter.")
    if not name or not location:
        raise ValueError("Source name and location cannot be empty.")
    if kind in ("rss", "website") and urlsplit(location).scheme not in ("http", "https"):
        raise ValueError("Web sources must use an http or https URL.")
    if kind in ("folder", "newsletter"):
        location = str(Path(location).expanduser().resolve())
    try:
        with _connect() as connection:
            cursor = connection.execute(
                "INSERT INTO news_sources (name, kind, location) VALUES (?, ?, ?)",
                (name[:160], kind, location[:2000]),
            )
            return cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise ValueError("This news source is already configured.") from error


def seed_sources_from_environment():
    configured = os.getenv("NEWS_SOURCES", "").strip()
    if not configured:
        return 0
    try:
        entries = json.loads(configured)
    except json.JSONDecodeError as error:
        raise ValueError("NEWS_SOURCES must be a JSON array.") from error
    if not isinstance(entries, list):
        raise ValueError("NEWS_SOURCES must be a JSON array.")
    inserted = 0
    existing = {source["location"] for source in list_sources()}
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Each NEWS_SOURCES entry must be an object.")
        name, kind, location = item.get("name"), item.get("kind"), item.get("location")
        if not isinstance(location, str) or location in existing:
            continue
        add_source(name, kind, location)
        existing.add(location)
        inserted += 1
    return inserted


def list_sources():
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, name, kind, location, enabled, created_at, last_checked_at, last_error "
            "FROM news_sources ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [dict(row) for row in rows]


def set_source_enabled(source_id, enabled):
    if not isinstance(enabled, bool):
        raise ValueError("Enabled state must be true or false.")
    with _connect() as connection:
        cursor = connection.execute(
            "UPDATE news_sources SET enabled = ? WHERE id = ?",
            (int(enabled), source_id),
        )
        return cursor.rowcount > 0


def _canonical_url(link):
    if not link:
        return ""
    parsed = urlsplit(link.strip())
    if parsed.scheme not in ("http", "https"):
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                       parsed.path.rstrip("/") or "/", parsed.query, ""))


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.text = []
        self.in_title = False
        self.hidden_depth = 0

    def handle_starttag(self, tag, _attrs):
        if tag == "title":
            self.in_title = True
        if tag in ("script", "style", "noscript"):
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in ("script", "style", "noscript") and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if not self.hidden_depth:
            self.text.append(data)


def _fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "PersonalAI-Agent/1.0 (+local news digest)"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read(MAX_FEED_BYTES + 1)
        if len(body) > MAX_FEED_BYTES:
            raise ValueError("Source response exceeds the 2 MB limit.")
        return body, response.headers.get_content_charset() or "utf-8"


def _parse_feed(body):
    root = ET.fromstring(body)
    entries = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "item" and element.tag.rsplit("}", 1)[-1] != "entry":
            continue
        fields = {}
        for child in list(element):
            key = child.tag.rsplit("}", 1)[-1].lower()
            value = (child.attrib.get("href") or "".join(child.itertext())
                     if key == "link" else "".join(child.itertext()))
            fields.setdefault(key, html.unescape(value).strip())
        entries.append({
            "title": fields.get("title", "(untitled)"),
            "summary": fields.get("summary") or fields.get("description", ""),
            "link": fields.get("link", ""),
            "published_at": fields.get("published") or fields.get("updated")
                or fields.get("pubdate") or fields.get("date"),
        })
    return entries[:MAX_ITEMS_PER_SOURCE]


def _read_local_source(source):
    root = Path(source["location"]).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Folder not found: {root}")
    entries = []
    extensions = {".txt", ".md", ".eml", ".pdf"}
    for path in sorted(root.rglob("*")):
        if len(entries) >= MAX_ITEMS_PER_SOURCE:
            break
        if (path.is_symlink() or not path.is_file() or path.name.startswith(".")
                or path.suffix.casefold() not in extensions):
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            if resolved.stat().st_size > MAX_LOCAL_FILE_BYTES:
                continue
            if path.suffix.casefold() == ".pdf":
                try:
                    from pypdf import PdfReader
                except ImportError as error:
                    raise RuntimeError(
                        "PDF ingestion needs pypdf; install project requirements."
                    ) from error
                text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages[:40])
            elif path.suffix.casefold() == ".eml":
                message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
                subject = str(message.get("subject", path.stem))
                parts = []
                body = message.get_body(preferencelist=("plain",))
                if body:
                    parts.append(body.get_content())
                text = "\n".join(parts)
                entries.append({"title": subject, "summary": text[:2000],
                                "link": str(path), "published_at": None})
                continue
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                continue
            entries.append({
                "title": lines[0][:300],
                "summary": " ".join(lines[1:])[:2000] or lines[0][:2000],
                "link": str(path),
                "published_at": datetime.fromtimestamp(
                    resolved.stat().st_mtime, timezone.utc
                ).isoformat(),
            })
        except (OSError, ValueError):
            continue
    return entries


def _embedding(text):
    global _EMBEDDING_AVAILABLE
    if _EMBEDDING_AVAILABLE is False:
        return None
    model = os.getenv("OLLAMA_EMBEDDING_MODEL", OLLAMA_MODEL)
    request = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/embed",
        data=json.dumps({"model": model, "input": text[:4000]}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
        vectors = data.get("embeddings", [])
        _EMBEDDING_AVAILABLE = bool(vectors and isinstance(vectors[0], list))
        return vectors[0] if _EMBEDDING_AVAILABLE else None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        _EMBEDDING_AVAILABLE = False
        return None


def _similarity(left, right, right_vector=None):
    if left.get("embedding") and right_vector:
        try:
            a, b = json.loads(left["embedding"]), right_vector
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(y * y for y in b))
            if norm_a and norm_b:
                return dot / (norm_a * norm_b)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    words_a = set(re.findall(r"[a-z0-9]{3,}", (left["title"] + " " + left["summary"]).casefold()))
    words_b = set(re.findall(r"[a-z0-9]{3,}", right["title"] + " " + right["summary"]))
    if not words_a or not words_b:
        return 0.0
    lexical = len(words_a & words_b) / len(words_a | words_b)
    title_match = SequenceMatcher(
        None, left["title"].casefold(), right["title"].casefold()
    ).ratio()
    return max(lexical, title_match)


def _save_entry(connection, source_id, entry):
    title = re.sub(r"\s+", " ", entry["title"]).strip()[:500] or "(untitled)"
    summary = re.sub(r"\s+", " ", entry["summary"]).strip()[:4000]
    link = _canonical_url(entry["link"])
    vector = _embedding(title + "\n" + summary)
    fingerprint = hashlib.sha256((title.casefold() + "\n" + link).encode()).hexdigest()
    rows = connection.execute(
        "SELECT id, event_key, title, summary, embedding FROM news_items "
        "ORDER BY last_seen_at DESC LIMIT 300"
    ).fetchall()
    candidate = {"title": title, "summary": summary}
    match = next(
        (row for row in rows
         if row["event_key"] == fingerprint
         or _similarity(dict(row), candidate, vector) >= 0.86),
        None,
    )
    tags = interests.classify_topics(title, summary)
    if match:
        item_id = match["id"]
        connection.execute(
            "UPDATE news_items SET last_seen_at = CURRENT_TIMESTAMP, "
            "summary = CASE WHEN length(?) > length(summary) THEN ? ELSE summary END "
            "WHERE id = ?",
            (summary, summary, item_id),
        )
    else:
        cursor = connection.execute(
            "INSERT INTO news_items "
            "(event_key, title, summary, link, published_at, tags, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fingerprint, title, summary, link, entry.get("published_at"),
             json.dumps(tags), json.dumps(vector) if vector else None),
        )
        item_id = cursor.lastrowid
    connection.execute(
        "INSERT OR IGNORE INTO news_item_sources (item_id, source_id, source_link) "
        "VALUES (?, ?, ?)",
        (item_id, source_id, link),
    )
    return item_id, match is None


def run_digest(full=False):
    """Fetch enabled sources and merge duplicate stories into shared digest cards."""
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO news_runs (run_type) VALUES (?)",
            ("full" if full else "incremental",),
        )
        run_id = cursor.lastrowid
        sources = [dict(row) for row in connection.execute(
            "SELECT * FROM news_sources WHERE enabled = 1 ORDER BY id"
        )]
        seen = added = errors = 0
        details = []
        for source in sources:
            try:
                if source["kind"] in ("folder", "newsletter"):
                    entries = _read_local_source(source)
                elif source["kind"] == "rss":
                    body, _charset = _fetch(source["location"])
                    entries = _parse_feed(body)
                else:
                    body, charset = _fetch(source["location"])
                    page = _PageText()
                    page.feed(body.decode(charset, errors="replace"))
                    entries = [{
                        "title": " ".join(page.title).strip() or source["name"],
                        "summary": " ".join(" ".join(page.text).split())[:4000],
                        "link": source["location"], "published_at": None,
                    }]
                for entry in entries[:MAX_ITEMS_PER_SOURCE]:
                    seen += 1
                    _item_id, created = _save_entry(connection, source["id"], entry)
                    added += int(created)
                connection.execute(
                    "UPDATE news_sources SET last_checked_at = CURRENT_TIMESTAMP, last_error = NULL "
                    "WHERE id = ?", (source["id"],)
                )
            except (OSError, ValueError, RuntimeError, ET.ParseError,
                    urllib.error.URLError, TimeoutError) as error:
                errors += 1
                details.append(f"{source['name']}: {error}")
                connection.execute(
                    "UPDATE news_sources SET last_checked_at = CURRENT_TIMESTAMP, last_error = ? "
                    "WHERE id = ?", (str(error)[:500], source["id"])
                )
        connection.execute(
            "UPDATE news_runs SET finished_at = CURRENT_TIMESTAMP, items_seen = ?, "
            "items_added = ?, error_count = ?, details = ? WHERE id = ?",
            (seen, added, errors, "\n".join(details)[:4000], run_id),
        )
    agent_state.add_decision(
        "news_digest", "Full digest" if full else "Incremental digest",
        f"Read {seen} entries from {len(sources)} enabled local sources; grouped duplicates.",
        {"items_added": added, "source_errors": errors},
    )
    return {"run_id": run_id, "items_seen": seen, "items_added": added,
            "error_count": errors, "details": details}


def list_items(topic=None, limit=200):
    with _connect() as connection:
        rows = connection.execute(
            "SELECT n.id, n.title, n.summary, n.link, n.published_at, n.tags, "
            "n.first_seen_at, n.last_seen_at, "
            "GROUP_CONCAT(DISTINCT s.name) AS sources "
            "FROM news_items n LEFT JOIN news_item_sources r ON r.item_id = n.id "
            "LEFT JOIN news_sources s ON s.id = r.source_id "
            "GROUP BY n.id ORDER BY COALESCE(n.published_at, n.first_seen_at) DESC, n.id DESC "
            "LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    items = []
    weights = {
        interest["topic"]: interest["weight"]
        for interest in interests.list_interests()["interests"]
    }
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags"])
        item["sources"] = item["sources"].split(",") if item["sources"] else []
        item["relevance_score"] = round(
            sum(weights.get(tag, 0.5) for tag in item["tags"]) / max(1, len(item["tags"])),
            3,
        )
        if topic and topic not in item["tags"]:
            continue
        items.append(item)
    items.sort(
        key=lambda item: (
            (item["published_at"] or item["first_seen_at"] or "")[:10],
            item["relevance_score"],
            item["published_at"] or item["first_seen_at"] or "",
        ),
        reverse=True,
    )
    return items[:max(1, min(int(limit), 500))]


def feedback(item_id, action):
    if action not in ("relevant", "not_interested"):
        raise ValueError("News feedback must be relevant or not_interested.")
    with _connect() as connection:
        item = connection.execute(
            "SELECT title, summary FROM news_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return False
        topics = interests.record_action(
            "news_relevant" if action == "relevant" else "news_not_interested",
            item["title"] + " " + item["summary"], "news", item_id,
            "Reader marked this story relevant" if action == "relevant"
            else "Reader marked this story not interested",
        )
    agent_state.add_decision(
        "news_feedback", f"News item {item_id}",
        "Updated interest weights from an explicit reader action.",
        {"action": action, "topics": topics},
    )
    return True


def latest_run():
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, run_type, started_at, finished_at, items_seen, items_added, "
            "error_count, details FROM news_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None
