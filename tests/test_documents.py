import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent import documents
from src.agent.ai import (
    OllamaAIProvider,
    _document_command_from_prompt,
    _run_document_command,
)


class DocumentSearchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "documents"
        patcher = patch.object(documents, "DOCUMENTS_DIR", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_searches_supported_files_and_ranks_matching_terms(self):
        self.root.mkdir(parents=True)
        (self.root / "warranty.md").write_text(
            "Fridge warranty lasts five years. Keep the receipt.", encoding="utf-8"
        )
        (self.root / "notes.txt").write_text(
            "The fridge warranty receipt is in the kitchen folder.", encoding="utf-8"
        )

        results = documents.search_documents("fridge warranty")

        self.assertEqual([item["path"] for item in results], ["notes.txt", "warranty.md"])
        self.assertIn("fridge warranty", results[0]["snippet"].casefold())

    def test_ignores_hidden_unsupported_and_oversized_files(self):
        self.root.mkdir(parents=True)
        (self.root / ".private.md").write_text("secret keyword", encoding="utf-8")
        (self.root / "archive.pdf").write_text("keyword", encoding="utf-8")
        (self.root / "large.txt").write_text("keyword and too much content", encoding="utf-8")
        with patch.object(documents, "MAX_FILE_BYTES", 10):
            self.assertEqual(documents.search_documents("keyword"), [])

    def test_rejects_empty_or_generic_search(self):
        with self.assertRaises(ValueError):
            documents.search_documents(" ")
        with self.assertRaises(ValueError):
            documents.search_documents("find documents about my")


class DocumentCommandTests(unittest.TestCase):
    def test_only_explicit_document_search_is_routed(self):
        self.assertEqual(
            _document_command_from_prompt("Find documents about fridge warranty"),
            ("search", "fridge warranty"),
        )
        self.assertIsNone(_document_command_from_prompt("Tell me about document databases"))

    def test_document_search_chat_command_does_not_call_ollama(self):
        with patch("src.agent.ai.get_conversation", return_value=[]), \
             patch("src.agent.ai.search_documents", return_value=[{
                 "path": "manual.md", "snippet": "Warranty lasts five years.",
             }]), \
             patch("src.agent.ai.save_conversation") as save, \
             patch("src.agent.ai.urllib.request.urlopen") as ollama:
            agent = OllamaAIProvider()
            answer = agent.generate_response("Search my documents for warranty")

        self.assertIn("manual.md", answer)
        self.assertIn("five years", answer)
        ollama.assert_not_called()
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
