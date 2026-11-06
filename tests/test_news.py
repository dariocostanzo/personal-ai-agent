import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import agent_state, interests, news


class NewsDigestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(news, "DB_PATH", Path(temp.name) / "news.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(agent_state, "DB_PATH", Path(temp.name) / "agent_state.db")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_feed_parser_reads_rss_items(self):
        parsed = news._parse_feed(b"""<rss><channel><item>
            <title>Science update</title><description>New research</description>
            <link>https://example.test/story</link>
        </item></channel></rss>""")
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["title"], "Science update")
        self.assertEqual(parsed[0]["link"], "https://example.test/story")

    def test_duplicate_stories_merge_sources_and_feedback_updates_interest(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        first = Path(temp.name) / "first"
        second = Path(temp.name) / "second"
        first.mkdir()
        second.mkdir()
        (first / "story.txt").write_text(
            "City science team publishes new climate research\n"
            "The research explains local climate changes.", encoding="utf-8"
        )
        (second / "story.txt").write_text(
            "City science team publishes new climate research\n"
            "More details from the same study.", encoding="utf-8"
        )
        news.add_source("Press review", "folder", str(first))
        news.add_source("Newsletter", "newsletter", str(second))

        with patch.object(news, "_embedding", return_value=None):
            result = news.run_digest()

        items = news.list_items()
        self.assertEqual(result["items_seen"], 2)
        self.assertEqual(result["items_added"], 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(set(items[0]["sources"]), {"Press review", "Newsletter"})
        self.assertIn("science", items[0]["tags"])
        self.assertTrue(news.feedback(items[0]["id"], "not_interested"))
        science = next(item for item in interests.list_interests()["interests"]
                       if item["topic"] == "science")
        self.assertAlmostEqual(science["weight"], 0.32)

    def test_feedback_requires_valid_action_and_existing_item(self):
        with self.assertRaises(ValueError):
            news.feedback(1, "dismiss")
        self.assertFalse(news.feedback(1, "relevant"))


if __name__ == "__main__":
    unittest.main()
