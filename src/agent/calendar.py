"""Read-only, local iCalendar (.ics) awareness."""

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from src.agent import config as _config

CALENDAR_PATH = Path(os.getenv(
    "AGENT_CALENDAR_ICS",
    Path(__file__).resolve().parents[2] / "data" / "calendar.ics",
)).expanduser()


def _unfold(content):
    return re.sub(r"\r?\n[ \t]", "", content)


def _date(value):
    value = value.split(":", 1)[-1].strip()
    if re.fullmatch(r"\d{8}", value):
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    if re.fullmatch(r"\d{8}T\d{6}Z?", value):
        return datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S").date()
    return None


def list_events(start=None, days=30, path=None):
    source = Path(path or CALENDAR_PATH).expanduser()
    if not source.exists():
        return []
    start = start or date.today()
    if isinstance(start, str):
        start = date.fromisoformat(start)
    end = start + timedelta(days=max(1, int(days)))
    content = _unfold(source.read_text(encoding="utf-8", errors="replace"))
    events = []
    from src.agent.goals import list_goals
    goal_candidates = list_goals(include_completed=False)
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", content, re.S | re.I):
        fields = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.split(";", 1)[0].upper()] = value.strip()
        event_date = _date(fields.get("DTSTART", ""))
        if not event_date or not start <= event_date < end:
            continue
        summary = fields.get("SUMMARY", "(untitled event)")
        normalized_summary = summary.casefold()
        related_goals = [
            goal["title"] for goal in goal_candidates
            if any(word in normalized_summary
                   for word in (goal["title"] + " " + goal["details"]).casefold().split()
                   if len(word) > 4)
        ][:3]
        events.append({
            "date": event_date.isoformat(),
            "summary": summary,
            "location": fields.get("LOCATION", ""),
            "related_goals": related_goals,
        })
    return sorted(events, key=lambda event: (event["date"], event["summary"].casefold()))
