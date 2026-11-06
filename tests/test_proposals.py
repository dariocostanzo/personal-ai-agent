import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import agent_state, goals, interests, news, proposals, providers


class ProposalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(agent_state, "DB_PATH", Path(temp.name) / "state.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(news, "DB_PATH", Path(temp.name) / "news.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = Path(temp.name) / "feed"
        self.folder.mkdir()

    def test_news_source_is_only_added_after_explicit_acceptance(self):
        proposal_id = proposals.propose(
            "news_source", "Add local press review", "Useful local source",
            {"name": "Press review", "kind": "folder", "location": str(self.folder)},
        )
        self.assertEqual(news.list_sources(), [])
        self.assertTrue(proposals.review(proposal_id, "accepted"))
        self.assertEqual(news.list_sources()[0]["name"], "Press review")
        self.assertEqual(proposals.list_proposals()[0]["status"], "accepted")

    def test_rejected_proposal_has_no_effect(self):
        proposal_id = proposals.propose(
            "guardian_check", "Check local service", payload={"url": "http://localhost:9000"}
        )
        self.assertTrue(proposals.review(proposal_id, "rejected"))
        self.assertEqual(proposals.list_proposals()[0]["status"], "rejected")

    def test_model_suggestions_are_added_only_to_review_queue(self):
        model_response = json.dumps([{
            "kind": "assistant_prompt",
            "title": "Clarify recommendations",
            "details": "Ask a brief follow-up when preferences are unclear.",
            "payload": {"prompt": "Ask a brief follow-up when preferences are unclear."},
        }])
        with patch.object(providers, "complete", return_value=model_response), \
                patch.object(goals, "list_goals", return_value=[]), \
                patch.object(interests, "list_interests", return_value={"interests": []}), \
                patch.object(news, "list_sources", return_value=[]), \
                patch.object(agent_state, "latest_guardian_checks", return_value=[]):
            suggestions = proposals.suggest()

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["status"], "pending")
        self.assertEqual(proposals.list_proposals()[0]["status"], "pending")

    def test_invalid_model_suggestions_are_rejected_without_partial_writes(self):
        model_response = json.dumps([
            {"kind": "assistant_prompt", "title": "Valid", "payload": {"prompt": "A prompt"}},
            {"kind": "unsupported", "title": "Invalid", "payload": {}},
        ])
        with patch.object(providers, "complete", return_value=model_response), \
                patch.object(goals, "list_goals", return_value=[]), \
                patch.object(interests, "list_interests", return_value={"interests": []}), \
                patch.object(news, "list_sources", return_value=[]), \
                patch.object(agent_state, "latest_guardian_checks", return_value=[]):
            with self.assertRaises(ValueError):
                proposals.suggest()

        self.assertEqual(proposals.list_proposals(), [])


if __name__ == "__main__":
    unittest.main()
