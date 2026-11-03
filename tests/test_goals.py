import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import goals


class TestGoals(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patcher = patch.object(goals, "DB_PATH", Path(self.temp_dir.name) / "goals.db")
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_add_and_list_goals(self):
        goal_id = goals.add_goal("Build a weekly routine", "Make time for movement")
        goal = goals.list_goals()[0]

        self.assertEqual(goal["id"], goal_id)
        self.assertEqual(goal["title"], "Build a weekly routine")
        self.assertEqual(goal["details"], "Make time for movement")
        self.assertEqual(goal["status"], "active")
        self.assertTrue(goal["created_at"])

    def test_complete_and_reopen_goal(self):
        goal_id = goals.add_goal("Read more")

        self.assertTrue(goals.set_goal_status(goal_id, "completed"))
        self.assertEqual(goals.list_goals()[0]["status"], "completed")
        self.assertEqual(goals.list_goals(include_completed=False), [])
        self.assertTrue(goals.set_goal_status(goal_id, "active"))

    def test_validation(self):
        with self.assertRaises(ValueError):
            goals.add_goal("  ")
        with self.assertRaises(ValueError):
            goals.set_goal_status(1, "paused")
        self.assertFalse(goals.set_goal_status(999, "completed"))


if __name__ == "__main__":
    unittest.main()