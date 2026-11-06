import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.agent import calendar, goals


class CalendarTests(unittest.TestCase):
    def test_reads_local_events_and_matches_goals(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(goals, "DB_PATH", Path(temp.name) / "goals.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        goal_id = goals.add_goal("Science project", "Finish the research")
        event_date = date(2026, 11, 6)
        path = Path(temp.name) / "events.ics"
        path.write_text(
            "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
            "DTSTART;VALUE=DATE:20261106\nSUMMARY:Science project review\n"
            "LOCATION:Library\nEND:VEVENT\nEND:VCALENDAR\n",
            encoding="utf-8",
        )
        events = calendar.list_events(event_date, days=2, path=path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["summary"], "Science project review")
        self.assertEqual(events[0]["related_goals"], ["Science project"])
        self.assertEqual(goal_id, 1)

    def test_absent_local_calendar_is_empty(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.assertEqual(calendar.list_events(path=Path(temp.name) / "missing.ics"), [])


if __name__ == "__main__":
    unittest.main()
