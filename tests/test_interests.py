import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import agent_state, interests


class InterestGraphTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(agent_state, "DB_PATH", Path(temp.name) / "state.db")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_explicit_actions_adjust_weights_once_and_explain_why(self):
        interests.record_action(
            "task_completed", "Study a science and technology paper", "task", 15,
            "Task was explicitly marked complete.",
        )
        interests.record_action(
            "task_completed", "Study a science and technology paper", "task", 15,
            "Task was explicitly marked complete.",
        )
        graph = interests.list_interests()
        science = next(item for item in graph["interests"] if item["topic"] == "science")
        self.assertEqual(science["weight"], 0.54)
        self.assertEqual(len(graph["recent_events"]), 2)
        self.assertIn("explicitly marked", graph["recent_events"][0]["reason"])
        self.assertEqual(len(graph["edges"]), 1)

    def test_interest_weights_are_controlled_and_editable(self):
        interests.set_interest("health", 0.9)
        self.assertEqual(interests.list_interests()["interests"][0]["weight"], 0.9)
        with self.assertRaises(ValueError):
            interests.set_interest("uncontrolled topic", 0.8)
        with self.assertRaises(ValueError):
            interests.set_interest("health", 1.2)


if __name__ == "__main__":
    unittest.main()
