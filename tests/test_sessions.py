import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import sessions
from src.agent import goals


class TestSessionMetadata(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patcher = patch.object(sessions, "DB_PATH", Path(self.temp_dir.name) / "sessions.db")
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_attention_metadata_is_upserted(self):
        sessions.set_needs_attention("chat-1", True)
        sessions.set_needs_attention("chat-1", False)

        metadata = sessions.list_session_metadata()["chat-1"]
        self.assertEqual(metadata["needs_attention"], 0)
        self.assertIsNone(metadata["goal_id"])

    def test_invalid_attention_value_is_rejected(self):
        with self.assertRaises(ValueError):
            sessions.set_needs_attention("chat-1", "true")

    def test_session_can_be_assigned_to_a_goal(self):
        with patch.object(goals, "DB_PATH", Path(self.temp_dir.name) / "goals.db"):
            goal_id = goals.add_goal("Build a routine")
            sessions.set_session_goal("chat-2", goal_id)

        self.assertEqual(sessions.list_session_metadata()["chat-2"]["goal_id"], goal_id)


if __name__ == "__main__":
    unittest.main()