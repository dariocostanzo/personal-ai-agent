import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date

from src.agent import tasks
from src.agent.ai import (
    OllamaAIProvider,
    _run_task_command,
    _task_command_from_prompt,
)


class TaskStorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(tasks, "DB_PATH", Path(temp.name) / "tasks.db")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_add_and_list_task_with_due_date(self):
        task_id = tasks.add_task("  Pay rent  ", "2026-11-05")
        self.assertEqual(task_id, 1)
        item = tasks.list_tasks()[0]
        self.assertEqual(item["title"], "Pay rent")
        self.assertEqual(item["due_date"], "2026-11-05")
        self.assertEqual(item["status"], "open")

    def test_invalid_tasks_are_rejected(self):
        with self.assertRaises(ValueError):
            tasks.add_task(" ")
        with self.assertRaises(ValueError):
            tasks.add_task("Pay rent", "next Thursday")
        with self.assertRaises(ValueError):
            tasks.add_task("Pay rent", "20261105")

    def test_completion_keeps_task_in_history(self):
        task_id = tasks.add_task("Call dentist")
        self.assertTrue(tasks.complete_task(task_id))
        self.assertFalse(tasks.complete_task(task_id))
        self.assertEqual(tasks.list_tasks(), [])
        history = tasks.list_tasks(include_completed=True)
        self.assertEqual(history[0]["status"], "completed")
        self.assertEqual(history[0]["title"], "Call dentist")

    def test_missing_task_is_not_completed(self):
        self.assertFalse(tasks.complete_task(999))

    def test_search_is_case_insensitive_and_treats_wildcards_literally(self):
        tasks.add_task("Pay rent")
        tasks.add_task("Pay 100% of bill")
        self.assertEqual([t["title"] for t in tasks.search_tasks("RENT")], ["Pay rent"])
        self.assertEqual([t["title"] for t in tasks.search_tasks("100%")], ["Pay 100% of bill"])

    def test_update_task_can_rename_reschedule_and_clear_due_date(self):
        task_id = tasks.add_task("Call dentist", "2026-11-05")
        self.assertTrue(tasks.update_task(task_id, title="Book dentist", due_date="2026-11-06"))
        item = tasks.list_tasks()[0]
        self.assertEqual((item["title"], item["due_date"]), ("Book dentist", "2026-11-06"))
        self.assertTrue(tasks.update_task(task_id, clear_due_date=True))
        self.assertIsNone(tasks.list_tasks()[0]["due_date"])

    def test_update_rejects_invalid_dates_and_completed_tasks(self):
        task_id = tasks.add_task("Call dentist")
        with self.assertRaises(ValueError):
            tasks.update_task(task_id, due_date="2026-02-30")
        tasks.complete_task(task_id)
        self.assertFalse(tasks.update_task(task_id, title="Done"))

    def test_overview_groups_tasks_by_due_date(self):
        tasks.add_task("Late", "2026-11-04")
        tasks.add_task("Today", "2026-11-05")
        tasks.add_task("Soon", "2026-11-10")
        tasks.add_task("Later", "2026-11-20")
        tasks.add_task("No date")
        overview = tasks.task_overview(date(2026, 11, 5))
        self.assertEqual([t["title"] for t in overview["overdue"]], ["Late"])
        self.assertEqual([t["title"] for t in overview["today"]], ["Today"])
        self.assertEqual([t["title"] for t in overview["upcoming"]], ["Soon"])


class TaskCommandTests(unittest.TestCase):
    def test_only_clear_task_commands_match(self):
        self.assertEqual(
            _task_command_from_prompt("Add task: call dentist | due 2026-11-05"),
            ("add", "call dentist", "2026-11-05"),
        )
        self.assertEqual(
            _task_command_from_prompt("Remind me to buy milk."),
            ("remind", "buy milk", None),
        )
        self.assertEqual(_task_command_from_prompt("List my tasks"), ("list",))
        self.assertEqual(
            _task_command_from_prompt("Complete task #4"), ("complete", 4)
        )
        self.assertEqual(
            _task_command_from_prompt("What should I do today?"), ("overview",)
        )
        self.assertEqual(
            _task_command_from_prompt("Find tasks for rent"), ("search", "rent")
        )
        self.assertEqual(
            _task_command_from_prompt("Reschedule task #4 to 2026-11-12"),
            ("reschedule", 4, "2026-11-12"),
        )
        self.assertEqual(
            _task_command_from_prompt("Rename task #4 to Pay the water bill"),
            ("rename", 4, "Pay the water bill"),
        )
        self.assertEqual(
            _task_command_from_prompt("Clear due date for task #4"),
            ("clear_due", 4),
        )
        self.assertIsNone(_task_command_from_prompt("Tell me about tasks in Python"))

    def test_bad_due_date_is_explained_without_creation(self):
        with patch("src.agent.ai.add_task", side_effect=ValueError(
            "Due date must use YYYY-MM-DD format."
        )):
            answer = _run_task_command(("add", "Pay rent", "Friday"))
        self.assertIn("YYYY-MM-DD", answer)

    def test_remind_command_discloses_no_notification_support(self):
        with patch("src.agent.ai.add_task", return_value=7):
            answer = _run_task_command(("remind", "buy milk", None))
        self.assertIn("cannot send notifications yet", answer)

    def test_chat_command_executes_without_calling_ollama(self):
        with patch("src.agent.ai.get_conversation", return_value=[]), \
             patch("src.agent.ai.add_task", return_value=12), \
             patch("src.agent.ai.save_conversation") as save, \
             patch("src.agent.ai.urllib.request.urlopen") as ollama:
            agent = OllamaAIProvider()
            answer = agent.generate_response("Add task: call dentist")

        self.assertIn("Added task #12", answer)
        ollama.assert_not_called()
        save.assert_called_once()
        self.assertEqual(agent.conversation_history[-1]["content"], answer)


if __name__ == "__main__":
    unittest.main()
