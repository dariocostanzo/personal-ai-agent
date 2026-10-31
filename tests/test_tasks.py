import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
