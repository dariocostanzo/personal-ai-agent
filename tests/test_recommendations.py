import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import recommendations


class TestRecommendations(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patcher = patch.object(
            recommendations,
            "DB_PATH",
            Path(self.temp_dir.name) / "recommendations.db",
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_record_and_decide_recommendation(self):
        recommendation_id = recommendations.add_recommendation(
            "Review unused subscription", "It has not been used this month", "Monthly expense scan"
        )
        self.assertTrue(recommendations.decide_recommendation(recommendation_id, "accepted"))
        self.assertFalse(recommendations.decide_recommendation(recommendation_id, "declined"))
        item = recommendations.list_recommendations()[0]
        self.assertEqual(item["status"], "accepted")
        self.assertTrue(item["decided_at"])

    def test_invalid_recommendations_are_rejected(self):
        with self.assertRaises(ValueError):
            recommendations.add_recommendation(" ")
        with self.assertRaises(ValueError):
            recommendations.decide_recommendation(1, "executed")


if __name__ == "__main__":
    unittest.main()